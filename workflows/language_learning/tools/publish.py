"""语言学习成片发布：标题标签沿用 ai-video-maker，中文发 YouTube「学中文」。"""

from __future__ import annotations

import json
import re
from pathlib import Path

from core.tools.youtube import YouTubeToolError, list_youtube_accounts, publish_youtube_video

from .._constants import (
    CHINESE_PUBLISH_ACCOUNT_GROUP,
    CHINESE_PUBLISH_TAGS,
    PUBLISH_MANIFEST_FILE_NAME,
    YOUTUBE_LANGUAGE_BY_MODE,
    YOUTUBE_LANGUAGE_LEARNING_CATEGORY_ID,
)
from .._errors import ConfirmationRequiredError, PublishError


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
        if part is not None and part_count is not None:
            return f"{title} {part}/{part_count}"
        return title
    rows = list(words or [])
    selected = rows[0] if rows else {}
    word = str(selected.get("chinese") or selected.get("english") or "单词").strip()
    return f"韩语｜{word}的韩语怎么说？"


def _publish_metadata(topic_english: str = "") -> dict:
    return {
        "title": build_video_title("en-zh", topic_english),
        "tags": list(CHINESE_PUBLISH_TAGS),
    }


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


def _description(title: str, tags: list[str]) -> str:
    hashtags = _hashtags(tags)
    return f"{title}\n\n{hashtags}" if hashtags else title


def attach_publish_manifest(video_result: dict, words_by_mode: dict) -> dict:
    """给中文视频补上 YouTube 发布标题和标签，并停在发布确认。"""
    topic = str(video_result.get("topic") or "").strip()
    topic_english = str(words_by_mode.get("_topic_english") or topic).strip()
    items = []
    for video in video_result.get("videos") or []:
        if str(video.get("learning_mode") or "") != "en-zh":
            continue
        metadata = _publish_metadata(topic_english)
        metadata["short_title"] = f"中文{topic or '单词'}怎么说"
        parts = []
        for part in video.get("video_parts") or []:
            path = Path(part["output_path"]).resolve()
            if not path.is_file():
                raise PublishError(f"待发布视频不存在：{path}")
            parts.append({
                "output_path": str(path),
                "title": str(part.get("title") or metadata["title"]),
                "word_start": part.get("word_start"),
                "word_end": part.get("word_end"),
                "duration": part.get("duration"),
            })
        if not parts:
            raise PublishError("en-zh 没有可发布的视频文件")
        items.append({
            "learning_mode": "en-zh",
            "account_group": CHINESE_PUBLISH_ACCOUNT_GROUP,
            "channel": "youtube",
            "title": metadata["title"],
            "tags": metadata["tags"],
            "short_title": metadata["short_title"],
            "videos": parts,
        })
    if not items:
        return {**video_result, "status": "done"}
    output_dir = Path(video_result["output_dir"]).resolve()
    manifest_path = output_dir / PUBLISH_MANIFEST_FILE_NAME
    manifest = {
        "status": "awaiting_publish_confirmation",
        "confirmation_required": "publish",
        "topic": topic,
        "run_id": video_result.get("run_id"),
        "cache_dir": video_result.get("cache_dir"),
        "output_dir": str(output_dir),
        "items": items,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        **video_result,
        "status": "awaiting_publish_confirmation",
        "confirmation_required": "publish",
        "manifest_path": str(manifest_path),
        "publish_items": items,
    }


def _load_manifest(manifest_path: str | Path) -> dict:
    path = Path(manifest_path).resolve()
    if not path.is_file():
        raise PublishError(f"发布清单不存在：{path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PublishError(f"读取发布清单失败：{path}。{exc}") from exc
    if not isinstance(payload, dict) or not payload.get("items"):
        raise PublishError(f"发布清单无效：{path}")
    return payload


def _youtube_channels(group_name: str) -> list[dict]:
    accounts = [item for item in list_youtube_accounts() if str(item.get("channel_title") or "").strip() == group_name]
    if not accounts:
        raise PublishError(
            f"YouTube 账号组不存在：{group_name}。请先授权或迁移频道标题为“{group_name}”的 YouTube 账号",
            {"account_group": group_name},
        )
    return accounts


def _publish_chinese_youtube(item: dict) -> dict:
    channels = _youtube_channels(item["account_group"])
    tags = _normalized_tags(item["tags"])
    language = YOUTUBE_LANGUAGE_BY_MODE["en-zh"]
    results = []
    for video in item["videos"]:
        title = str(video.get("title") or item["title"])
        description = _description(title, item["tags"])
        for account in channels:
            try:
                upload = publish_youtube_video(
                    account["channel_id"],
                    video["output_path"],
                    title,
                    description=description,
                    tags=tags,
                    category_id=YOUTUBE_LANGUAGE_LEARNING_CATEGORY_ID,
                    privacy_status="public",
                    language=language,
                )
                results.append({"account": account, "video": video, "success": True, "result": upload})
            except YouTubeToolError as exc:
                results.append({"account": account, "video": video, "success": False, "error": exc.to_dict()["error"]})
    return {
        "learning_mode": item["learning_mode"],
        "account_group": item["account_group"],
        "channel": "youtube",
        "success": all(row["success"] for row in results) if results else False,
        "results": results,
    }


def publish_vocabulary_videos(manifest_path: str | Path, publish_confirmed: bool) -> dict:
    """用户确认后，把中文视频发到 YouTube「学中文」。"""
    if publish_confirmed is not True:
        raise ConfirmationRequiredError("必须先获得用户对本次语言学习成品发布的明确确认")
    manifest = _load_manifest(manifest_path)
    published = []
    for item in manifest["items"]:
        if item.get("learning_mode") != "en-zh" or item.get("channel") != "youtube":
            raise PublishError(f"不支持的发布目标：{item.get('learning_mode')} / {item.get('channel')}")
        published.append(_publish_chinese_youtube(item))
    success = all(item["success"] for item in published)
    manifest["status"] = "published" if success else "publish_failed"
    Path(manifest_path).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "success": success,
        "manifest_path": str(Path(manifest_path).resolve()),
        "topic": manifest.get("topic"),
        "run_id": manifest.get("run_id"),
        "published": published,
    }
