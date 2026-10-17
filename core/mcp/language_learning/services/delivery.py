"""语言学习成片交付清单与 R2 产物登记。"""

from __future__ import annotations

import json
import re
from pathlib import Path

from core.tools.media_files import upload_public_file
from core.tools.media_records import commit_production_outputs
from core.tools.topic_dedup import commit as commit_topic

from ..config import (
    MINIMUM_NEW_WORDS,
    PUBLISH_MANIFEST_FILE_NAME,
    TOPIC_DEDUPLICATION_DAYS,
    WORD_HISTORY_DAYS,
    WORKFLOW_ID,
    QUIZ_TITLE_SUFFIXES,
    video_content_kind,
    video_production_id,
)
from ..errors import PublishError
from .vocabulary import build_database_word_entries


def build_video_title(
    mode: str,
    topic: str = "",
    words: list[dict] | None = None,
    *,
    part: int | None = None,
    part_count: int | None = None,
) -> str:
    """成品标题：中文用主题句加分段，韩语用该段里的中文词。"""
    if mode == "en-zh":
        english_topic = str(topic or "").strip() or "Vocabulary"
        if not re.fullmatch(r"[A-Za-z][A-Za-z '&-]*", english_topic):
            english_topic = "Vocabulary"
        title = f"10 Essential {english_topic.title()} Words in Chinese"
        if part is not None and part_count is not None and part_count > 1:
            return f"{title} {part}/{part_count}"
        return title
    rows = list(words or [])
    selected = rows[0] if rows else {}
    word = str(selected.get("chinese") or selected.get("english") or "单词").strip()
    title = f"韩语｜{word}的韩语怎么说？"
    if part is not None and part_count is not None and part_count > 1:
        return f"{title} {part}/{part_count}"
    return title


def _normalized_tags(tags: list[str]) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        name = str(tag or "").strip().lstrip("#")
        key = name.casefold()
        if name and key not in seen:
            seen.add(key)
            names.append(name)
    return names


def _hashtags(tags: list[str]) -> str:
    return " ".join(f"#{name}" for name in _normalized_tags(tags))


def _video_parts(video: dict, fallback_title: str, *, empty_error: str) -> list[dict]:
    parts = []
    for index, part in enumerate(video.get("video_parts") or [], 1):
        path = Path(part["output_path"]).resolve()
        if not path.is_file():
            raise PublishError(f"待发布视频不存在：{path}")
        parts.append({
            "content_part": int(part.get("part") or index),
            "output_path": str(path),
            "title": str(part.get("title") or fallback_title),
            "word_start": part.get("word_start"),
            "word_end": part.get("word_end"),
            "duration": part.get("duration"),
        })
    if not parts:
        raise PublishError(empty_error)
    return parts


def _mode_config(publish_config: dict[str, dict], mode: str) -> dict:
    config = publish_config.get(mode) if isinstance(publish_config, dict) else None
    if not isinstance(config, dict):
        raise PublishError(f"publish_config 缺少 {mode} 配置")
    return config


def _video_format(payload: dict) -> str:
    return str(payload.get("video_format") or "standard").strip() or "standard"


def _item_key(item: dict) -> str:
    return f"{item.get('learning_mode') or ''}:{_video_format(item)}"


def strip_quiz_title_suffix(title: str) -> str:
    """问答版与原版使用同一套标题，去掉历史上加过的 guess / 看图猜词后缀。"""
    text = str(title or "").strip()
    changed = True
    while changed:
        changed = False
        for marker in QUIZ_TITLE_SUFFIXES:
            if text.endswith(marker):
                text = text[: -len(marker)].rstrip()
                changed = True
    return text


def _titled(base: str, video_format: str, mode: str = "en-zh") -> str:
    del video_format, mode
    return strip_quiz_title_suffix(base)


def attach_publish_manifest(video_result: dict, words_by_mode: dict, publish_config: dict[str, dict]) -> dict:
    """给成片补上交付清单；这里只记录内容元数据，不包含平台和账号路由。"""
    topic = str(video_result.get("topic") or "").strip()
    topic_english = str(words_by_mode.get("_topic_english") or topic).strip()
    delivery_items = []
    for video in video_result.get("videos") or []:
        mode = str(video.get("learning_mode") or "")
        video_format = _video_format(video)
        if mode == "en-zh":
            zh_config = _mode_config(publish_config, "en-zh")
            title = _titled(build_video_title("en-zh", topic_english), video_format, "en-zh")
            delivery_items.append({
                "learning_mode": "en-zh",
                "video_format": video_format,
                "title": title,
                "tags": list(zh_config.get("tags") or []),
                "short_title": _titled(
                    str(zh_config.get("short_title") or f"中文{topic or '单词'}怎么说"),
                    video_format,
                    "en-zh",
                ),
                "videos": _video_parts(video, title, empty_error="en-zh 没有可发布的视频文件"),
            })
            continue
        if mode == "en-ko":
            ko_config = _mode_config(publish_config, "en-ko")
            title = _titled(
                build_video_title("en-ko", topic, words_by_mode.get("en-ko") or []),
                video_format,
                "en-ko",
            )
            short_title = _titled(
                str(ko_config.get("short_title") or "韩语单词怎么说"),
                video_format,
                "en-ko",
            )
            delivery_items.append({
                "learning_mode": "en-ko",
                "video_format": video_format,
                "title": title,
                "tags": list(ko_config.get("tags") or []),
                "short_title": short_title,
                "videos": _video_parts(video, title, empty_error="en-ko 没有可发布的视频文件"),
            })
    if not delivery_items:
        return {**video_result, "status": "done"}
    output_dir = Path(video_result["output_dir"]).resolve()
    manifest_path = output_dir / PUBLISH_MANIFEST_FILE_NAME
    kept_items = []
    new_keys = {
        f"{video.get('learning_mode') or ''}:{_video_format(video)}"
        for video in (video_result.get("videos") or [])
    }
    if manifest_path.is_file():
        try:
            previous = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            previous = {}
        for item in previous.get("items") or []:
            if _item_key(item) in new_keys:
                replacement = next(row for row in delivery_items if _item_key(row) == _item_key(item))
                merged = {int(video.get("content_part") or index): video for index, video in enumerate(item.get("videos") or [], 1)}
                merged.update({int(video["content_part"]): video for video in replacement["videos"]})
                replacement["videos"] = [merged[part] for part in sorted(merged)]
                continue
            kept_items.append(item)
    items = [*kept_items, *delivery_items]
    status = "produced"
    manifest = {
        "status": status,
        "topic": topic,
        "run_id": video_result.get("run_id"),
        "publish_date": video_result.get("publish_date"),
        "production_source": video_result.get("production_source", "local_mcp"),
        "cache_dir": video_result.get("cache_dir"),
        "output_dir": str(output_dir),
        "items": items,
        "database_commit": {
            "workflow": WORKFLOW_ID,
            "publication_id": f"{WORKFLOW_ID}:{video_result.get('run_id')}",
            "run_id": video_result.get("run_id"),
            "topic": topic,
            "days": TOPIC_DEDUPLICATION_DAYS,
            "history_days": WORD_HISTORY_DAYS,
            "minimum_new_words": MINIMUM_NEW_WORDS,
            "entries": build_database_word_entries(words_by_mode),
        },
    }
    if manifest["production_source"] == "local_mcp":
        manifest["database_commit_result"] = _commit_manifest_database(manifest)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        **video_result,
        "status": status,
        "manifest_path": str(manifest_path),
        "delivery_items": delivery_items,
    }


def _load_manifest(manifest_path: str | Path) -> dict:
    path = Path(manifest_path).resolve()
    if not path.is_file():
        raise PublishError(f"发布清单不存在：{path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PublishError(f"读取发布清单失败：{path}。{error}") from error
    if not isinstance(payload, dict) or not payload.get("items"):
        raise PublishError(f"发布清单无效：{path}")
    return payload


def upload_publish_assets_to_r2(
    manifest_path: str | Path,
    subject_sheet_path: str | Path | None = None,
    learning_modes: list[str] | None = None,
) -> dict:
    """上传语言成片、可选主题图和发布清单，并把公网地址写回本地清单。"""
    path = Path(manifest_path).resolve()
    manifest = _load_manifest(path)
    run_id = str(manifest.get("run_id") or "").strip()
    if not run_id:
        raise PublishError("发布清单缺少 run_id，无法生成 R2 对象路径")
    uploaded: list[dict] = []
    output_records = []
    production_source = str(manifest.get("production_source") or "local_mcp").strip()
    selected_modes = {str(value).strip() for value in (learning_modes or []) if str(value).strip()}
    for item in manifest.get("items") or []:
        mode = str(item.get("learning_mode") or "unknown").strip() or "unknown"
        if selected_modes and mode not in selected_modes:
            continue
        video_format = _video_format(item)
        content_kind = video_content_kind(mode, video_format)
        for index, video in enumerate(item.get("videos") or [], 1):
            index = int(video.get("content_part") or index)
            if video.get("video_url"):
                uploaded.append({"kind": "video", "source_name": Path(str(video.get("r2_key") or "")).name, "learning_mode": mode, "video_format": video_format, "url": video["video_url"], "key": video["r2_key"]})
                continue
            video_path = Path(str(video.get("output_path") or "")).resolve()
            stored = upload_public_file(
                video_path,
                f"runs/{WORKFLOW_ID}/{run_id}/{content_kind}/{index:02d}-{video_path.name}",
                content_type="video/mp4",
            )
            video["video_url"] = stored["url"]
            video["r2_key"] = stored["key"]
            uploaded.append({"kind": "video", "source_name": video_path.name, "learning_mode": mode, "video_format": video_format, **stored})
            output_records.append({
                    "production_id": video_production_id(production_source, run_id, mode, video_format, index),
                    "run_id": run_id,
                    "publish_date": str(manifest.get("publish_date") or "").strip(),
                    "business_line": WORKFLOW_ID,
                    "content_kind": content_kind,
                    "content_part": index,
                    "title": str(video.get("title") or item.get("title") or "").strip(),
                    "hashtags": _hashtags(list(item.get("tags") or [])),
                    "source": production_source,
                    "local_path": str(video_path) if production_source == "local_mcp" else None,
                    "r2_url": stored["url"],
                    "r2_expires_at": None,
                })
    if subject_sheet_path:
        sheet_path = Path(subject_sheet_path).resolve()
        suffix = sheet_path.suffix.lower()
        content_type = "image/png" if suffix == ".png" else "image/jpeg"
        stored = upload_public_file(
            sheet_path,
            f"runs/{WORKFLOW_ID}/{run_id}/subject-sheet{suffix or '.png'}",
            content_type=content_type,
        )
        manifest["subject_sheet_url"] = stored["url"]
        manifest["subject_sheet_r2_key"] = stored["key"]
        uploaded.append({"kind": "subject_sheet", "source_name": sheet_path.name, **stored})
    manifest["r2_uploaded"] = True
    manifest["production_outputs"] = commit_production_outputs(output_records) if output_records else []
    if production_source == "github_workflow":
        manifest["database_commit_result"] = _commit_manifest_database(manifest)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    stored_manifest = upload_public_file(
        path,
        f"runs/{WORKFLOW_ID}/{run_id}/publish-manifest.json",
        content_type="application/json",
    )
    manifest["manifest_url"] = stored_manifest["url"]
    manifest["manifest_r2_key"] = stored_manifest["key"]
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    stored_manifest = upload_public_file(
        path,
        stored_manifest["key"],
        content_type="application/json",
    )
    uploaded.append({"kind": "manifest", "source_name": PUBLISH_MANIFEST_FILE_NAME, **stored_manifest})
    delivery_manifest = {
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "topic": str(manifest.get("topic") or ""),
        "publish_date": str(manifest.get("publish_date") or ""),
        "r2_files": [
            {
                "source_name": str(item.get("source_name") or ""),
                "key": item.get("key"),
                "url": item.get("url"),
                "kind": item.get("kind"),
            }
            for item in uploaded
        ],
    }
    delivery_path = path.parent / "r2-manifest.json"
    delivery_path.write_text(json.dumps(delivery_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    stored_delivery = upload_public_file(
        delivery_path,
        f"runs/{WORKFLOW_ID}/{run_id}/r2-manifest.json",
        content_type="application/json",
    )
    return {
        "manifest_path": str(path),
        "manifest_url": stored_delivery["url"],
        "subject_sheet_url": manifest.get("subject_sheet_url"),
        "uploaded": [*uploaded, {"kind": "delivery_manifest", **stored_delivery}],
        "production_outputs": manifest["production_outputs"],
    }


def _commit_manifest_database(manifest: dict) -> dict:
    """成片产出成功后，幂等写入正式话题和十个单词。"""
    payload = manifest.get("database_commit")
    if not isinstance(payload, dict):
        raise PublishError("发布清单缺少 database_commit，无法写入正式内容历史")
    return commit_topic(
        str(payload.get("workflow") or ""),
        str(payload.get("topic") or ""),
        str(payload.get("publication_id") or ""),
        days=int(payload.get("days") or TOPIC_DEDUPLICATION_DAYS),
        entries=list(payload.get("entries") or []),
        history_days=int(payload.get("history_days") or WORD_HISTORY_DAYS),
        minimum_new_words=int(payload.get("minimum_new_words") or MINIMUM_NEW_WORDS),
    )
