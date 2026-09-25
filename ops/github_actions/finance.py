"""财经 GitHub Action：自动生成稿件并制作成片，不发布平台。

稿件在三类必做改动（品牌替换、连载指涉改写、错别字修正）之外允许措辞级改写：保留大结构与信息量并按语义断行；黄金钩子保持原样（仅品牌替换与错字修正）。与交互式财经 Skill 的整理规则保持一致。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from core.tools.generate_image import choose_finance_library_line
from ._mcp import MCPCallError, ProjectMCP
from core.tools.cloudflare_data import commit_production_outputs
from ._shared import (
    PROJECT_ROOT,
    json_text,
    qwen,
    resolve_publish_date,
    upload_run_files,
    write_summary,
)


# 语速另有音色绑定：generate_tts_fish.FISH_VOICE_RATES 里 28df7fe4… 固定 "+10%"，
# 只要用这个音色就 +10%（行内显式 rate 优先）。这里的 rate 只是兜底默认值。
TTS_CONFIG = {"voice": "fish:28df7fe4d3ec45f692af03d0a372805b", "rate": "+10%", "trim_trailing_silence": True}
BGM_PATH = "static/bgm/easy-lemon-kevin-macleod.mp3"
PRODUCTION_CONFIG = {
    "cover_frame_seconds": 0.03333333333333333,
    "intro": "slide_in_shutter",
    "shot_stickers": ["rec"],
    "matrixmedia_account_group": "心灵鸡汤",
    "bgm_gain": 0.672,
}
MATERIAL_STRATEGY = "image_library"
ARTICLE_MAX_LINE_LENGTH = 36
# 措辞级改写允许的长度浮动：去空白标点后正文长度 / 原稿长度。
# 低于下限说明压缩或漏了观点；高于上限说明扩写。品牌替换可能带来少量长度差，范围留了余量。
ARTICLE_LENGTH_RATIO_MIN = 0.80
ARTICLE_LENGTH_RATIO_MAX = 1.20
ARTICLE_GENERATION_ATTEMPTS = 5
BRAND_NAME = "财富研习岛"


def _article_prompt(source_text: str, source_hook: str) -> str:
    root = PROJECT_ROOT / ".agents" / "skills" / "finance"
    template = (root / "prompts" / "finance.md").read_text(encoding="utf-8")
    return template.replace("{{source_text}}", source_text).replace("{{source_hook}}", source_hook)


def _extract_source_hook(source_text: str) -> str:
    feedback = ""
    for _ in range(3):
        user_prompt = (
            "识别下面原稿开头完整的黄金钩子。黄金钩子必须从原稿第一个字开始连续复制，"
            "不得改字、改标点、补字或省略中间内容。只输出 {\"source_hook\":\"原文开头钩子\"}。\n\n"
            f"原稿：\n{source_text}"
        )
        if feedback:
            user_prompt += f"\n\n上一次输出校验失败，必须修正：{feedback}"
        result = qwen(
            "你是中文短视频审稿编辑，必须输出有效 JSON，不要输出 Markdown。",
            user_prompt,
            json_output=True,
            max_tokens=500,
        )
        try:
            hook = str(json_text(result).get("source_hook") or "")
        except (json.JSONDecodeError, ValueError) as exc:
            feedback = f"上一次 JSON 不完整或格式错误：{exc}；必须缩短钩子并输出完整 JSON"
            continue
        if hook and source_text.startswith(hook):
            return hook
        feedback = "source_hook 必须从原稿第一个字开始连续复制，且与原稿开头完全一致"
    raise ValueError("千问连续三次识别的黄金钩子都不是数据库原稿的精确开头")


def _bare(text: str) -> str:
    """去掉全部空白与标点，只留字符，用于「除品牌替换外逐字一致」的校验。"""
    return re.sub(r"[\s\W_]+", "", str(text or ""))


def _normalize_replacements(replacements) -> list[tuple[str, str]]:
    """返回 (原稿原文, 替换文本) 的原文层级列表；校验时统一再按 bare 口径比对。"""
    rows: list[tuple[str, str]] = []
    if not isinstance(replacements, list):
        return rows
    for item in replacements:
        if not isinstance(item, dict):
            continue
        source = str(item.get("from") or "").strip()
        target = str(item.get("to") or "").strip() or BRAND_NAME
        if source:
            rows.append((source, target))
    return rows


def _normalize_corrections(corrections) -> list[tuple[str, str]]:
    """错别字修正必须同时给出明确原文和修正文，不允许缺省成品牌名。"""
    rows: list[tuple[str, str]] = []
    if not isinstance(corrections, list):
        return rows
    for item in corrections:
        if not isinstance(item, dict):
            continue
        source = str(item.get("from") or "").strip()
        target = str(item.get("to") or "").strip()
        if source and target and source != target:
            rows.append((source, target))
    return rows


def _replace_raw(text: str, rows: list[tuple[str, str]]) -> str:
    result = str(text or "")
    for source_brand, target_brand in rows:
        result = result.replace(source_brand, target_brand)
    return result


def _article_validation_error(
    article: str,
    source_text: str,
    source_hook: str,
    replacements: list[tuple[str, str]],
    corrections: list[tuple[str, str]],
) -> str | None:
    """措辞级改写口径的程序校验：钩子原样、行长、品牌替换目标、长度比例。

    正文其余部分允许换说法，不再做逐字一致比对；信息完整性由长度比例与提示词约束兜底。
    """
    problems: list[str] = []
    article_body = _bare(article)
    original_hook_body = _bare(source_hook)
    source_body = _bare(source_text)
    if not original_hook_body or not source_body.startswith(original_hook_body):
        problems.append("原稿开头与黄金钩子不一致，无法校验")
    # 黄金钩子不做措辞改写：正文开头必须与「替换后的钩子」逐字一致。
    replaced_hook = _replace_raw(_replace_raw(source_hook, replacements), corrections)
    hook_body = _bare(replaced_hook)
    if not article_body.startswith(hook_body):
        problems.append("正文开头必须是黄金钩子（完成品牌替换后）的原样内容，只允许插入换行，钩子不得改写")
    long_lines = []
    for index, line in enumerate(article.splitlines(), 1):
        text = line.strip()
        if len(text) > ARTICLE_MAX_LINE_LENGTH:
            long_lines.append((index, len(text)))
    if long_lines:
        problems.append(
            f"以下行超过{ARTICLE_MAX_LINE_LENGTH}字，必须按语义换行（黄金钩子允许仅插入换行）：{long_lines}"
        )
    mismatched = [item for item in replacements if _bare(item[1]) != _bare(BRAND_NAME)]
    if mismatched:
        problems.append(f"replacements 只能替换为「{BRAND_NAME}」：{mismatched}")
    if source_body and article_body:
        ratio = len(article_body) / len(source_body)
        if ratio < ARTICLE_LENGTH_RATIO_MIN or ratio > ARTICLE_LENGTH_RATIO_MAX:
            problems.append(
                f"正文长度（去空白标点后 {len(article_body)} 字）是原稿（{len(source_body)} 字）的 {ratio:.2f} 倍，"
                f"超出 {ARTICLE_LENGTH_RATIO_MIN}~{ARTICLE_LENGTH_RATIO_MAX}："
                "措辞级改写只换说法，不得压缩、扩写或漏掉任何观点、数字与例子，请逐句核对信息是否完整保留"
            )
    return "；".join(problems) or None


def _restore_source_hook(
    article: str,
    source_hook: str,
    replacements: list[tuple[str, str]],
    corrections: list[tuple[str, str]],
) -> str:
    """用品牌替换并修正错字后的钩子锚定正文开头，只保留模型正文的后续内容。"""
    original_hook = str(source_hook or "").strip()
    replaced_hook = _replace_raw(_replace_raw(original_hook, replacements), corrections)
    current = str(article or "").strip()
    normalized_current = re.sub(r"\s+", "", current)
    normalized_hook = re.sub(r"\s+", "", replaced_hook)
    if normalized_current.startswith(normalized_hook):
        return current
    # 模型漏替换钩子时，先用替换后钩子的开头定位；定位不到再用原钩子开头，
    # 保证不会把整段原文重复拼在钩子后面。
    marker = normalized_hook[:8]
    if marker not in normalized_current:
        marker = re.sub(r"\s+", "", original_hook)[:8]
    offset = normalized_current.find(marker)
    suffix = normalized_current[offset + len(marker):] if offset >= 0 else normalized_current
    hook_lines = [replaced_hook[index:index + 20] for index in range(0, len(replaced_hook), 20)]
    return "\n".join(hook_lines) + ("\n" + suffix if suffix else "")


def _prepare_article(source_text: str, source_hook: str) -> tuple[str, str]:
    """三类必做改动 + 措辞级改写，程序校验钩子原样、行长与长度比例。

    返回 (正文, 完成品牌替换后的黄金钩子)；后者传给 finance_save_draft 的 source_hook。
    """
    json_rule = (
        "\n\n只输出 JSON："
        "{\"article\":\"断行后的完整正文\","
        "\"replacements\":[{\"from\":\"原稿里被替换掉的作者或品牌原文\",\"to\":\"" + BRAND_NAME + "\"}],"
        "\"corrections\":[{\"from\":\"原稿错字\",\"to\":\"正确文字\"}]}。"
        "replacements 必须完整列出你做过的每一处品牌替换（黄金钩子内部的机构名、权威背书等品牌同样要替换并列出）；"
        "corrections 必须完整列出每项明确错别字或转写同音错字修正；措辞级改写不需要逐条报告，只输出最终正文。"
        "程序会校验：黄金钩子（完成品牌替换后）必须原样出现在正文开头、"
        f"正文长度（去空白标点后）必须在原稿的 {ARTICLE_LENGTH_RATIO_MIN}~{ARTICLE_LENGTH_RATIO_MAX} 倍之间。"
        "改写硬性要求：句子顺序、段落划分与原稿一致，观点、数字、例子一个不少，不得压缩、扩写或重排；"
        "逐句换说法、调整句式和用词，不得整句整段照抄原稿。"
        f"硬性要求：每一行不得超过{ARTICLE_MAX_LINE_LENGTH}个字符。"
    )
    initial_prompt = _article_prompt(source_text, source_hook) + json_rule
    last_error = None
    previous_payload = ""
    for attempt in range(ARTICLE_GENERATION_ATTEMPTS):
        if attempt == 0:
            prompt = initial_prompt
        else:
            prompt = (
                "请直接修订上一版输出，不要从零另写。\n\n"
                f"程序校验结果：{last_error}。\n"
                f"开头黄金钩子（原文）：{source_hook}\n"
                f"黄金钩子内部的机构名、研究名、权威背书等品牌同样替换为「{BRAND_NAME}」，"
                "替换后的钩子必须原样保留在正文开头，钩子不做措辞改写。\n\n"
                "修订规则：执行三类必做改动（品牌替换、连载指涉改写、错别字修正），"
                f"品牌统一为「{BRAND_NAME}」；三类改动之外允许措辞级改写——逐句换说法、调整句式和用词，"
                "但句子顺序、段落划分与原稿一致，观点、数字、例子一个不少，不得压缩、扩写或重排；"
                "每项错字修正必须写入 corrections。每一行不超过36字。\n\n"
                f"数据库原稿（正文的唯一信息来源）：\n{source_text}\n\n"
                f"上一版输出（必须在此基础上定向修订）：\n{previous_payload}"
            )
        payload = json_text(qwen(
            "你是中文短视频编辑，必须输出有效 JSON，不要输出 Markdown。"
            "正文在三类必做改动（品牌替换（含黄金钩子内部）、连载指涉改写、错别字修正）之外允许措辞级改写："
            "逐句换说法、不得逐字照搬原稿，但保留大结构与信息量并按语义断行。",
            prompt,
            json_output=True,
            max_tokens=12000,
        ))
        previous_payload = json.dumps(payload, ensure_ascii=False)
        replacements = _normalize_replacements(payload.get("replacements"))
        corrections = _normalize_corrections(payload.get("corrections"))
        article = _restore_source_hook(
            str(payload.get("article") or ""), source_hook, replacements, corrections
        )
        last_error = _article_validation_error(
            article, source_text, source_hook, replacements, corrections
        )
        print(f"财经正文第 {attempt + 1} 次：{len(_bare(article))} 个字符；{last_error or '校验通过'}", flush=True)
        if last_error is None:
            return article, _replace_raw(
                _replace_raw(source_hook, replacements), corrections
            )
    raise RuntimeError(
        f"财经正文连续 {ARTICLE_GENERATION_ATTEMPTS} 次整理不合格，程序已阻止不合格正文进入后续步骤："
        f"{last_error}"
    )


def _choose_topic(article: str, recent_topics: list[str], requested_topic: str) -> str:
    requested_hint = requested_topic.strip()
    recent_folded = {item.strip().casefold() for item in recent_topics}
    feedback = ""
    for _ in range(3):
        user_prompt = (
            "从下面整理好的正文提炼一个准确、简短的话题，不得改变正文主题。"
            f"用户提供的可选侧重点：{requested_hint or '无'}。"
            f"不得与最近30天话题重复：{json.dumps(recent_topics, ensure_ascii=False)}。\n\n正文：\n{article}"
        )
        if feedback:
            user_prompt += f"\n\n上一次输出校验失败，必须修正：{feedback}"
        result = qwen(
            "你是短视频选题编辑。只返回一个中文话题，不加序号、引号或说明。",
            user_prompt,
            max_tokens=100,
        )
        topic = str(result["text"]).strip().strip("“”\"'")
        if topic and topic.casefold() not in recent_folded:
            return topic
        if not topic:
            feedback = "话题不能为空"
        else:
            feedback = f"话题“{topic}”与最近30天话题重复，必须换一个"
    raise ValueError("千问连续三次生成的话题都为空或与最近30天话题重复")


def _metadata(metadata_prompt: str, article: str, *, feedback: str = "") -> dict:
    user_prompt = (
        f"{metadata_prompt}\n\n正文：\n{article}\n\n"
        "输出 JSON：{\"metadata\":\"长标题|短标题|标签一|标签二|标签三|标签四\","
        "\"cover_lines\":[\"封面第一行\",\"封面第二行\"],"
        "\"cover_highlights\":[\"重点词一\",\"重点词二\"]}。"
        "cover_lines 必须按语义拆成1至3行；"
        "cover_highlights 必须选择1至3个原样出现在长标题中的重点词。\n\n"
        "这是硬性校验，必须在输出前自行逐字符计数：metadata 的第一个字段（长标题）"
        "必须是 12～26 个字符，包含中文、数字、英文和标点在内总数均按 1 个字符计算。"
        "不满足这个范围的 JSON 会被程序拒绝；不要解释，直接改写长标题后再输出。"
    )
    if feedback:
        user_prompt += f"\n\n上一次输出校验失败，必须修正：{feedback}"
    result = qwen(
        "你是短视频标题编辑，必须输出有效 JSON，不要输出 Markdown。",
        user_prompt,
        json_output=True,
        max_tokens=600,
    )
    payload = json_text(result)
    parts = [part.strip() for part in str(payload.get("metadata") or "").split("|")]
    if len(parts) != 6:
        raise ValueError("千问标题标签必须包含 6 个竖线字段")
    title_length = len(parts[0])
    if not 12 <= title_length <= 26:
        raise ValueError(
            f"长标题当前为 {title_length} 个字符，必须改为 12～26 个字符；"
            "只缩短或扩写长标题后重新输出完整 JSON"
        )
    short_title_length = len(parts[1])
    if not 6 <= short_title_length <= 16:
        raise ValueError(
            f"短标题当前为 {short_title_length} 个字符，必须改为 6～16 个字符；"
            "只缩短或扩写短标题后重新输出完整 JSON"
        )
    cover_lines = payload.get("cover_lines")
    if not isinstance(cover_lines, list):
        raise ValueError("千问标题结果缺少 cover_lines 数组")
    cover_highlights = payload.get("cover_highlights")
    if not isinstance(cover_highlights, list) or not cover_highlights:
        raise ValueError("千问标题结果缺少 cover_highlights 数组")
    return {
        "title": parts[0],
        "short_title": parts[1],
        "hashtags": parts[2:],
        "cover_lines": [str(item).strip() for item in cover_lines],
        "cover_highlights": [str(item).strip() for item in cover_highlights],
    }


def _select_images(prepared: dict) -> list[dict]:
    catalog = prepared.get("library_catalog") or []
    tasks = prepared.get("selection_tasks") or []
    compact_catalog = [{"id": row["id"], "caption": row["caption"]} for row in catalog]
    payload = json_text(qwen(
        "你是财经视频图库选图员。必须输出有效 JSON，不要输出 Markdown。",
        "为每个镜头选择语义最贴近的图库图片，同一图片允许重复使用。\n"
        f"镜头：{json.dumps(tasks, ensure_ascii=False)}\n"
        f"图库：{json.dumps(compact_catalog, ensure_ascii=False)}\n"
        "输出 {\"selections\":[{\"image_id\":\"shot-001\",\"library_id\":1}]}，覆盖全部镜头。",
        json_output=True,
        max_tokens=3000,
    ))
    by_id = {int(row["id"]): row for row in catalog}
    selected = payload.get("selections")
    if not isinstance(selected, list):
        raise ValueError("千问选图结果缺少 selections 数组")
    result = []
    for item in selected:
        row = by_id[int(item["library_id"])]
        result.append({"image_id": str(item["image_id"]), "image_path": row["image_path"]})
    if {item["image_id"] for item in result} != {item["image_id"] for item in tasks}:
        raise ValueError("千问选图结果没有完整覆盖全部镜头")
    return result


async def run(requested_topic: str = "", publish_date: str = "") -> dict:
    library_line = choose_finance_library_line()
    image_config = {"source": "local_library", "library_line": library_line}
    publish_date = resolve_publish_date(publish_date)
    async with ProjectMCP("core.mcp.finance", PROJECT_ROOT) as mcp:
        selected = await mcp.call("finance_get_source_script")
        source = selected["source"]
        reservation = selected["reservation"]
        source_text = str(source["transcript"]).strip()
        source_hook = _extract_source_hook(source_text)
        article, source_hook = _prepare_article(source_text, source_hook)
        topics = await mcp.call("finance_get_topics")
        topic = _choose_topic(article, topics.get("recent_topics") or [], requested_topic)
        metadata_prompt = (await mcp.call("finance_get_metadata_prompt"))["metadata_prompt"]
        last_error = None
        for _ in range(3):
            try:
                metadata = _metadata(
                    metadata_prompt,
                    article,
                    feedback=str(last_error) if last_error else "",
                )
                draft = await mcp.call(
                    "finance_save_draft",
                    {
                        "topic": topic,
                        "article": article,
                        "source_aweme_id": str(source["aweme_id"]),
                        "source_reservation_token": str(reservation["reservation_token"]),
                        "source_hook": source_hook,
                        "publish_date": publish_date,
                        **metadata,
                    },
                )
                break
            except (ValueError, MCPCallError) as exc:
                last_error = exc
        else:
            raise RuntimeError(f"财经标题连续三次不合格：{last_error}")
        started = await mcp.call(
            "finance_start_storyboard",
            {
                "draft_path": draft["draft_path"],
                "tts_config": TTS_CONFIG,
                "material_strategy": MATERIAL_STRATEGY,
            },
        )
        print("财经：轮询分镜 TTS", flush=True)
        storyboard_context = await mcp.poll("finance_poll_task", started["task_path"])
        storyboard_prompt = storyboard_context["storyboard_prompt"]
        last_error = None
        for _ in range(3):
            storyboard = qwen(
                "你是严格的视频分镜导演，只输出规定格式的 IMAGE 和 SUB 行。",
                storyboard_prompt,
                max_tokens=12000,
            )["text"]
            try:
                prepared = await mcp.call(
                    "finance_prepare_images",
                    {"draft_path": draft["draft_path"], "storyboard_text": storyboard, "image_config": image_config},
                )
                break
            except MCPCallError as exc:
                last_error = exc
                storyboard_prompt += f"\n\n上一次输出校验失败，必须修正：{exc}"
        else:
            raise RuntimeError(f"财经分镜连续三次不合格：{last_error}")
        selections = _select_images(prepared)
        image_manifest = await mcp.call(
            "finance_submit_images",
            {"context_path": prepared["context_path"], "images": selections},
        )
        production_config = {**PRODUCTION_CONFIG, "bgm_path": BGM_PATH}
        started = await mcp.call(
            "finance_start_finish_video",
            {
                "draft_path": draft["draft_path"],
                "material_manifest_path": image_manifest["manifest_path"],
                "production_config": production_config,
                "storyboard_text": storyboard,
                "production_source": "github_workflow",
            },
        )
        print("财经：轮询成片合成", flush=True)
        manifest = await mcp.poll("finance_poll_task", started["task_path"])
    remote = upload_run_files(
        "finance",
        manifest["run_id"],
        [manifest["video_path"], manifest["cover_path"], manifest["title_path"], manifest["short_title_path"], manifest["publish_copy_path"]],
        manifest,
    )
    uploaded_by_name = {
        str(item.get("source_name") or ""): str(item.get("url") or "")
        for item in remote.get("files") or []
    }
    video_url = uploaded_by_name.get(Path(manifest["video_path"]).name, "")
    if not video_url:
        raise RuntimeError("财经成片已上传，但 R2 返回结果缺少视频地址")
    production_outputs = commit_production_outputs([{
        "production_id": f"github_workflow:finance:{manifest['run_id']}:finance:1",
        "run_id": manifest["run_id"],
        "publish_date": manifest["publish_date"],
        "business_line": "finance",
        "content_kind": "finance",
        "content_part": 1,
        "title": manifest["title"],
        "hashtags": " ".join(f"#{str(tag).lstrip('#')}" for tag in manifest.get("hashtags") or []),
        "source": "github_workflow",
        "local_path": None,
        "r2_url": video_url,
        "r2_expires_at": None,
    }])
    write_summary(
        "财经成片已生成",
        [
            ("话题", topic),
            ("标题", manifest["title"]),
            ("素材策略", MATERIAL_STRATEGY),
            ("图库", library_line),
            ("BGM", Path(BGM_PATH).name),
            ("R2 清单", remote["manifest"]["url"]),
            ("平台发布", "未执行"),
        ],
    )
    return {"manifest": manifest, "r2": remote, "production_outputs": production_outputs}
