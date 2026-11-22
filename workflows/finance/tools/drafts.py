"""财经生产稿件领取、读写与计划查询。"""

from __future__ import annotations
from workflows.finance.errors.exceptions import AgentOutputFormatError, DraftNotFoundError, WorkflowStepError
import json, re
from pathlib import Path
from workflows.finance.parameters import (
    ARTICLE_MAX_LINE_LENGTH,
    AUTOMATION_DAILY_OUTPUT_COUNT,
    normalize_publish_date,
    CONTENT_KIND,
    DRAFT_FILE_NAME,
    MCP_ID,
    production_dirs,
    production_run_id,
    DEFAULT_PRODUCTION_CONFIG,
    SOURCE_COLLECTION_CODE,
    SOURCE_RESERVATION_MINUTES,
    TOPIC_DEDUPLICATION_DAYS,
)
from workflows.finance.infrastructure.scripts import list_editorial_drafts
from tools.database.production_records import list_production_outputs
from copy import deepcopy
from workflows.finance.infrastructure.scripts import reserve_source_script
from tools.database.topic_history import list_recent_topics as get_topic
from workflows.finance.errors.mapping import _map_error


def bare_text(text: str) -> str:
    """去掉全部空白与标点，只保留字符，用于跨层文本比对。"""
    return re.sub(r"[\s\W_]+", "", str(text or ""))


def validate_metadata(title: str, short_title: str, hashtags: list[str]) -> dict:
    """归一化长短标题和四个标签，校验各字段的格式。"""
    if not isinstance(hashtags, list) or len(hashtags) != 4:
        raise AgentOutputFormatError("hashtags 必须包含四个标签")
    fields = [str(field).strip().lstrip("#") for field in (title, short_title, *hashtags)]
    if any(not field or "|" in field or len(field.splitlines()) != 1 for field in fields):
        raise AgentOutputFormatError("长标题、短标题和标签必须为不含竖线的单行文字")
    # 在字数校验前去掉模型偶尔生成的尾部句末标点，避免标题标点单独占行。
    fields[0] = fields[0].rstrip("。．.？?！!… \t")
    fields[1] = fields[1].rstrip("。．.？?！!… \t")
    if not 12 <= len(fields[0]) <= 26:
        raise AgentOutputFormatError("中文长标题必须为 12～26 个字符")
    if not 6 <= len(fields[1]) <= 16:
        raise AgentOutputFormatError("中文短标题必须为 6～16 个字符")
    if len(set(fields[2:])) != 4:
        raise AgentOutputFormatError("四个标签必须互不重复")
    return {"title": fields[0], "short_title": fields[1], "hashtags": fields[2:]}


# 连载/前文指涉：本文必须是「财富研习岛」独立成篇的文章，出现这些表述必须由 Agent 改写。
_SERIAL_REFERENCE_PATTERN = re.compile(
    r"第[0-9０-９一二两三四五六七八九十百千]+[集期话]"
    r"|上[一那]?[集期]"
    r"|下[一那]?[集期]"
    r"|这[一那][集期]"
    r"|上[一]?[条个支]视频"
    r"|上回|前情回顾|往期"
)


def load_draft(path: str | Path, label: str) -> tuple[Path, dict]:
    resolved = Path(path).resolve()
    if not resolved.is_file():
        raise DraftNotFoundError(f"{label}不存在：{resolved}", {"path": str(resolved)})
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkflowStepError(f"读取{label}失败：{resolved}。{exc}") from exc
    if not isinstance(payload, dict):
        raise WorkflowStepError(f"{label}必须是 JSON 对象：{resolved}")
    return resolved, payload


def _cover_lines(cover_lines: list[str] | None) -> list[str]:
    if not isinstance(cover_lines, list) or not cover_lines:
        raise WorkflowStepError("cover_lines 必须是 Agent 按语义断好的非空行列表")
    if len(cover_lines) > 3:
        raise WorkflowStepError("cover_lines 最多 3 行")
    lines = [str(item).strip() for item in cover_lines]
    if any(not item for item in lines):
        raise WorkflowStepError("cover_lines 里不能有空行")
    return lines


def _cover_highlights(title: str, cover_highlights: list[str] | None) -> list[str]:
    if not isinstance(cover_highlights, list) or not cover_highlights:
        raise WorkflowStepError("cover_highlights 必须是 Agent 选出的非空封面重点词列表")
    highlights: list[str] = []
    for item in cover_highlights:
        word = str(item).strip()
        if not word:
            raise WorkflowStepError("cover_highlights 里不能有空字符串")
        if word not in title:
            raise WorkflowStepError(
                "cover_highlights 中的每个重点词都必须原样出现在长标题 title 中",
                {"title": title, "highlight": word},
            )
        if word not in highlights:
            highlights.append(word)
    return highlights


def save_draft(
    topic: str,
    article: str,
    storyboard: str,
    title: str,
    short_title: str,
    hashtags: list[str],
    cover_lines: list[str],
    source_aweme_id: str,
    source_reservation_token: str,
    source_hook: str,
    publish_date: str,
    cover_highlights: list[str] | None = None,
    content_part: int = 1,
    db_source_hook: str = "",
) -> dict:
    normalized_topic = str(topic or "").strip()
    normalized_article = str(article or "").strip()
    if not normalized_topic:
        raise WorkflowStepError("topic 不能为空")
    if not normalized_article:
        raise WorkflowStepError("article 不能为空")
    normalized_source_aweme_id = str(source_aweme_id or "").strip()
    normalized_source_token = str(source_reservation_token or "").strip()
    normalized_source_hook = str(source_hook or "").strip()
    # 数据库逐字钩子：mark_used 用它校验 transcript_corrected 的逐字前缀。
    # 处理后的钩子（source_hook）含品牌替换时两者不同；缺省回退为处理后钩子。
    normalized_db_hook = str(db_source_hook or "").strip()
    if not normalized_source_aweme_id.isdigit():
        raise WorkflowStepError("source_aweme_id 必须是有效的抖音作品 ID")
    if not normalized_source_token:
        raise WorkflowStepError("source_reservation_token 不能为空")
    if not normalized_source_hook:
        raise WorkflowStepError("source_hook 不能为空")
    if not re.sub(r"\s+", "", normalized_article).startswith(re.sub(r"\s+", "", normalized_source_hook)):
        raise WorkflowStepError("正文必须以数据库原稿的黄金钩子原样开头，不能增删或改写")
    long_lines = [
        (index, len(line.strip()))
        for index, line in enumerate(normalized_article.splitlines(), 1)
        if len(line.strip()) > ARTICLE_MAX_LINE_LENGTH
    ]
    if long_lines:
        raise WorkflowStepError(
            f"每个镜头的台词不得超过{ARTICLE_MAX_LINE_LENGTH}字，请按语义换行；"
            "黄金钩子也允许仅插入换行，不得改字或标点",
            {"long_lines": long_lines},
        )
    serial_hits = [
        {"line": index, "match": match.group(0)}
        for index, line in enumerate(normalized_article.splitlines(), 1)
        if (match := _SERIAL_REFERENCE_PATTERN.search(line))
    ]
    if serial_hits:
        raise WorkflowStepError(
            "正文不得出现连载/前文指涉：本文是「财富研习岛」作者独立的一篇文章，没有任何前文；"
            "请把命中处改写成不依赖任何前文也能读懂的独立表述，其余内容按措辞级改写规则处理（保留大结构与信息）",
            {"serial_references": serial_hits},
        )
    if not isinstance(hashtags, list):
        raise WorkflowStepError("hashtags 必须是包含四个标签的列表")
    metadata = validate_metadata(title, short_title, hashtags)
    normalized_cover_lines = _cover_lines(cover_lines)
    normalized_cover_highlights = _cover_highlights(metadata["title"], cover_highlights)
    if isinstance(content_part, bool) or not isinstance(content_part, int) or content_part < 1:
        raise WorkflowStepError("content_part 必须是大于等于 1 的整数（同一天第二条传 2）")
    try:
        run_id = production_run_id(publish_date)
    except ValueError as exc:
        raise WorkflowStepError(str(exc)) from exc
    # 话题库记录 ID：part 1 沿用 run-YYYYMMDD 的纯数字；part 2 起追加两位分片号避免撞车。
    record = {
        "id": int(run_id.removeprefix("run-")) if content_part == 1
        else int(f"{run_id.removeprefix('run-')}{content_part:02d}"),
        "topic": normalized_topic,
    }
    cache_root, output_root = production_dirs(run_id, content_part)
    target_draft_path = cache_root / DRAFT_FILE_NAME
    cache_root.mkdir(parents=True, exist_ok=True)
    output_root.mkdir(parents=True, exist_ok=True)
    draft = {
        "version": 1,
        "line": MCP_ID,
        "content_kind": CONTENT_KIND,
        "status": "ready_for_production",
        "topic": record["topic"],
        "run_id": run_id,
        "content_part": content_part,
        "topic_record_id": record["id"],
        "database_status": "pending_production",
        "publish_date": str(publish_date).strip(),
        "source_aweme_id": normalized_source_aweme_id,
        "source_reservation_token": normalized_source_token,
        "source_hook": normalized_source_hook,
        "db_source_hook": normalized_db_hook or normalized_source_hook,
        "source_database_status": "reserved",
        "article": normalized_article,
        "storyboard": storyboard,
        **metadata,
        "cover_lines": normalized_cover_lines,
        "cover_highlights": normalized_cover_highlights,
        "cache_dir": str(cache_root),
        "output_dir": str(output_root),
        "draft_path": str(target_draft_path),
    }
    target_draft_path.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
    return draft


def save_source_usage(draft_path: str | Path, usage: dict) -> dict:
    resolved, draft = load_draft(draft_path, "财经稿件")
    draft["source_database_status"] = "used"
    draft["source_usage"] = usage
    resolved.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
    return draft


def finance_get_production_config() -> dict:
    """返回财经生产唯一标准配置，供 Agent 与 GitHub Runner 共用。"""
    return deepcopy(DEFAULT_PRODUCTION_CONFIG)


def finance_get_source_script() -> dict:
    """从已收集的财经文案中选择并临时占用一条未使用的稿件。"""
    try:
        return reserve_source_script(
            collection_code=SOURCE_COLLECTION_CODE,
            workflow=MCP_ID,
            reservation_minutes=SOURCE_RESERVATION_MINUTES,
        )
    except Exception as exc:
        raise _map_error(exc) from exc


def finance_save_draft(
    topic: str,
    article: str,
    storyboard: str,
    title: str,
    short_title: str,
    hashtags: list[str],
    cover_lines: list[str],
    source_aweme_id: str,
    source_reservation_token: str,
    source_hook: str,
    publish_date: str,
    cover_highlights: list[str] | None = None,
    content_part: int = 1,
    db_source_hook: str = "",
) -> dict:
    """保存完成两类必做改动与措辞级改写的稿件，来源稿件继续保持临时占用。

    同一天制作第二条时传 content_part=2：缓存与产物目录独立（run-YYYYMMDD-part2），
    D1 落库使用 content_part 区分，run_id 仍为 run-YYYYMMDD。
    db_source_hook：数据库原稿开头未经改动的逐字钩子（mark_used 校验用）；
    处理后的 source_hook 含品牌替换时与原稿不同，必须另外传原样钩子。不改错别字或标点。
    """
    try:
        stored = next((row["editorial"] for row in list_editorial_drafts(False)["records"]
                       if row["aweme_id"] == source_aweme_id), None)
        incoming = {"topic": topic, "article": article, "storyboard": storyboard, "title": title, "short_title": short_title,
                    "hashtags": hashtags, "cover_lines": cover_lines, "cover_highlights": cover_highlights,
                    "source_hook": source_hook, "db_source_hook": db_source_hook}
        if stored is None or any(stored.get(key) != value for key, value in incoming.items()):
            raise WorkflowStepError("生产内容必须与稿库定稿一致，请先完成宿主定稿")
        clean_topic = str(topic or "").strip()
        recent = get_topic(MCP_ID, TOPIC_DEDUPLICATION_DAYS)
        if clean_topic.casefold() in {
            str(item.get("topic") or "").strip().casefold() for item in recent
        }:
            raise WorkflowStepError(
                f"话题最近 {TOPIC_DEDUPLICATION_DAYS} 天已经发布：{clean_topic}"
            )
        draft = save_draft(
            topic,
            article,
            storyboard,
            title,
            short_title,
            hashtags,
            cover_lines,
            source_aweme_id,
            source_reservation_token,
            source_hook,
            publish_date,
            cover_highlights,
            content_part,
            db_source_hook,
        )
        return draft
    except Exception as exc:
        raise _map_error(exc) from exc


def finance_get_automation_plan(publish_date: str) -> dict:
    """按计划发布日期返回 GitHub 财经待生产分片；每天目标数量由 workflow 统一维护。"""
    try:
        normalized_date = normalize_publish_date(publish_date)
        records = list_production_outputs(publish_date=normalized_date, business_line=MCP_ID)
        existing_parts = {
            int(item.get("content_part") or 1)
            for item in records
            if 1 <= int(item.get("content_part") or 1) <= AUTOMATION_DAILY_OUTPUT_COUNT
        }
        pending_parts = [
            part
            for part in range(1, AUTOMATION_DAILY_OUTPUT_COUNT + 1)
            if part not in existing_parts
        ]
        return {
            "publish_date": normalized_date,
            "should_generate": bool(pending_parts),
            "output_count": len(records),
            "desired_output_count": AUTOMATION_DAILY_OUTPUT_COUNT,
            "pending_content_parts": pending_parts,
            "skip_reason": "" if pending_parts else f"该计划发布日期已有 {len(existing_parts)} 条财经成片记录，已达到每日目标",
        }
    except Exception as exc:
        raise _map_error(exc) from exc
