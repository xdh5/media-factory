"""财经 GitHub Action：自动生成稿件并制作成片，不发布平台。

稿件按原稿全文保留：只把作者与品牌替换为财富研习岛，并按语义断行，不做长度压缩。
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
BGM_PATH = "core/tools/generate_bgm/static/easy-lemon-kevin-macleod.mp3"
PRODUCTION_CONFIG = {
    "cover_frame_seconds": 0.03333333333333333,
    "intro": "slide_in_shutter",
    "shot_stickers": ["rec"],
    "matrixmedia_account_group": "心灵鸡汤",
    "bgm_gain": 0.84,
}
MATERIAL_STRATEGY = "image_library"
ARTICLE_MAX_LINE_LENGTH = 36
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
    rows: list[tuple[str, str]] = []
    if not isinstance(replacements, list):
        return rows
    for item in replacements:
        if not isinstance(item, dict):
            continue
        source = _bare(item.get("from"))
        target = _bare(item.get("to"))
        if source:
            rows.append((source, target or _bare(BRAND_NAME)))
    return rows


def _article_validation_error(
    article: str,
    source_text: str,
    source_hook: str,
    replacements: list[tuple[str, str]],
) -> str | None:
    problems: list[str] = []
    article_body = _bare(article)
    hook_body = _bare(source_hook)
    source_body = _bare(source_text)
    if not hook_body or not source_body.startswith(hook_body):
        problems.append("原稿开头与黄金钩子不一致，无法校验")
    if not article_body.startswith(hook_body):
        problems.append("黄金钩子没有原样保留在正文开头（钩子内不得替换品牌）")
    long_lines = []
    for index, line in enumerate(article.splitlines(), 1):
        text = line.strip()
        if len(text) > ARTICLE_MAX_LINE_LENGTH:
            long_lines.append((index, len(text)))
    if long_lines:
        problems.append(
            f"以下行超过{ARTICLE_MAX_LINE_LENGTH}字，必须按语义换行（黄金钩子允许仅插入换行）：{long_lines}"
        )
    mismatched = [item for item in replacements if item[1] != _bare(BRAND_NAME)]
    if mismatched:
        problems.append(f"replacements 只能替换为「{BRAND_NAME}」：{mismatched}")
    expected_body = source_body[len(hook_body):]
    for source_brand, target_brand in replacements:
        expected_body = expected_body.replace(source_brand, target_brand)
    if expected_body != article_body[len(hook_body):]:
        problems.append(
            "正文与「原稿只替换作者和品牌、其余逐字保留」不一致："
            "不得压缩、扩写、改写或重排原稿内容，也不得漏报替换项"
        )
    return "；".join(problems) or None


def _restore_source_hook(article: str, source_hook: str) -> str:
    """恢复数据库黄金钩子的原字，只保留模型正文的后续内容。"""
    hook = str(source_hook or "").strip()
    current = str(article or "").strip()
    normalized_hook = re.sub(r"\s+", "", hook)
    normalized_current = re.sub(r"\s+", "", current)
    if normalized_current.startswith(normalized_hook):
        return current
    marker = normalized_hook[:8]
    offset = normalized_current.find(marker)
    suffix = normalized_current[offset + len(marker):] if offset >= 0 else normalized_current
    hook_lines = [hook[index:index + 20] for index in range(0, len(hook), 20)]
    return "\n".join(hook_lines) + ("\n" + suffix if suffix else "")


def _prepare_article(source_text: str, source_hook: str) -> str:
    """保留原稿全文，只替换作者与品牌并按语义断行；程序逐字复核。"""
    json_rule = (
        "\n\n只输出 JSON："
        "{\"article\":\"断行后的完整正文\","
        "\"replacements\":[{\"from\":\"原稿里被替换掉的作者或品牌原文\",\"to\":\"" + BRAND_NAME + "\"}]}。"
        "replacements 必须完整列出你做过的每一处替换；"
        "程序会按去掉空白和标点后的口径复核："
        f"「原稿开头黄金钩子之外的部分」在执行完 replacements 后必须与正文逐字一致。"
        f"没有可替换内容时 replacements 输出空数组。硬性要求：每一行不得超过{ARTICLE_MAX_LINE_LENGTH}个字符。"
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
                f"必须原样保留在开头的黄金钩子：{source_hook}\n\n"
                "修订规则：正文必须逐字保留原稿的全部内容与顺序，只允许替换作者和品牌"
                f"为「{BRAND_NAME}」、以及在语义处插入换行；"
                "不得删减、扩写、改写或重排任何一句话。\n\n"
                f"数据库原稿（正文的唯一来源）：\n{source_text}\n\n"
                f"上一版输出（必须在此基础上定向修订）：\n{previous_payload}"
            )
        payload = json_text(qwen(
            "你是中文短视频编辑，必须输出有效 JSON，不要输出 Markdown。"
            f"正文必须逐字保留原稿全部内容，只替换作者和品牌为「{BRAND_NAME}」并按语义断行。",
            prompt,
            json_output=True,
            max_tokens=12000,
        ))
        previous_payload = json.dumps(payload, ensure_ascii=False)
        article = _restore_source_hook(str(payload.get("article") or ""), source_hook)
        replacements = _normalize_replacements(payload.get("replacements"))
        last_error = _article_validation_error(article, source_text, source_hook, replacements)
        print(f"财经正文第 {attempt + 1} 次：{len(_bare(article))} 个字符；{last_error or '校验通过'}", flush=True)
        if last_error is None:
            return article
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
        article = _prepare_article(source_text, source_hook)
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
