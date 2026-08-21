"""语言学习成片发布：中文发 YouTube / Meta，韩语由 Agent 用矩媒 MCP 发到「韩语」。"""

from __future__ import annotations

import json
import re
from pathlib import Path

from core.tools.publish_to_meta import MetaToolError, publish_to_meta, upload_public_file
from core.tools.publish_to_youtube import YouTubeToolError, list_youtube_accounts, publish_to_youtube

from .._constants import (
    CHINESE_YOUTUBE_CHANNEL_ID,
    PUBLISH_MANIFEST_FILE_NAME,
    WORKFLOW_ID,
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


def _description(title: str, tags: list[str]) -> str:
    hashtags = _hashtags(tags)
    return f"{title}\n\n{hashtags}" if hashtags else title


def _video_parts(video: dict, fallback_title: str, *, empty_error: str) -> list[dict]:
    parts = []
    for part in video.get("video_parts") or []:
        path = Path(part["output_path"]).resolve()
        if not path.is_file():
            raise PublishError(f"待发布视频不存在：{path}")
        parts.append({
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


def attach_publish_manifest(video_result: dict, words_by_mode: dict, publish_config: dict[str, dict]) -> dict:
    """给成片补上发布清单。发布目标由 SKILL 传入的 publish_config 决定。"""
    topic = str(video_result.get("topic") or "").strip()
    topic_english = str(words_by_mode.get("_topic_english") or topic).strip()
    youtube_items = []
    matrixmedia_items = []
    for video in video_result.get("videos") or []:
        mode = str(video.get("learning_mode") or "")
        if mode == "en-zh":
            zh_config = _mode_config(publish_config, "en-zh")
            title = build_video_title("en-zh", topic_english)
            youtube_items.append({
                "learning_mode": "en-zh",
                "account_group": str(zh_config.get("account_group") or ""),
                "youtube_account": str(zh_config.get("youtube_account") or WORKFLOW_ID),
                "channel": "youtube",
                "title": title,
                "tags": list(zh_config.get("tags") or []),
                "short_title": str(zh_config.get("short_title") or f"中文{topic or '单词'}怎么说"),
                "videos": _video_parts(video, title, empty_error="en-zh 没有可发布的视频文件"),
            })
            continue
        if mode == "en-ko":
            ko_config = _mode_config(publish_config, "en-ko")
            title = build_video_title("en-ko", topic, words_by_mode.get("en-ko") or [])
            matrixmedia_items.append({
                "learning_mode": "en-ko",
                "account_group": str(ko_config.get("account_group") or ""),
                "channel": "matrixmedia",
                "title": title,
                "tags": list(ko_config.get("tags") or []),
                "short_title": str(ko_config.get("short_title") or "韩语单词怎么说"),
                "platforms": list(ko_config.get("platforms") or []),
                "videos": _video_parts(video, title, empty_error="en-ko 没有可发布的视频文件"),
            })
    if not youtube_items and not matrixmedia_items:
        return {**video_result, "status": "done"}
    output_dir = Path(video_result["output_dir"]).resolve()
    manifest_path = output_dir / PUBLISH_MANIFEST_FILE_NAME
    kept_youtube = []
    kept_matrixmedia = []
    new_modes = {
        str(video.get("learning_mode") or "")
        for video in (video_result.get("videos") or [])
    }
    if manifest_path.is_file():
        try:
            previous = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            previous = {}
        for item in previous.get("items") or []:
            mode = str(item.get("learning_mode") or "")
            if mode in new_modes:
                continue
            if mode == "en-zh":
                kept_youtube.append(item)
            elif mode == "en-ko":
                kept_matrixmedia.append(item)
    youtube_items = [*kept_youtube, *youtube_items]
    matrixmedia_items = [*kept_matrixmedia, *matrixmedia_items]
    items = [*youtube_items, *matrixmedia_items]
    status = "awaiting_publish_confirmation"
    manifest = {
        "status": status,
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
        "status": status,
        "confirmation_required": "publish",
        "manifest_path": str(manifest_path),
        "publish_items": youtube_items,
        "matrixmedia_items": matrixmedia_items,
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


def _youtube_channels(group_name: str, youtube_account: str) -> list[dict]:
    account = str(youtube_account or WORKFLOW_ID).strip() or WORKFLOW_ID
    accounts = list_youtube_accounts(account=account)
    if accounts:
        return accounts
    raise PublishError(
        f"YouTube 账号未配置。请在 .env 填写 {account.upper()}_YOUTUBE_CHANNEL_ID、"
        f"{account.upper()}_YOUTUBE_CLIENT_ID、{account.upper()}_YOUTUBE_CLIENT_SECRET、"
        f"{account.upper()}_YOUTUBE_REFRESH_TOKEN",
        {"account": account, "account_group": group_name, "channel_id": CHINESE_YOUTUBE_CHANNEL_ID},
    )


def _should_publish_youtube(manifest: dict) -> bool:
    """YouTube 已成功时只补发 Reels，避免重复上传。"""
    if manifest.get("youtube_published") is True:
        return False
    return str(manifest.get("status") or "") not in {"awaiting_matrixmedia", "published", "awaiting_meta"}


def _meta_platforms(manifest: dict) -> list[str]:
    """按清单里已成功的平台补发，避免 Instagram 重复发。"""
    facebook_ok = bool(manifest.get("meta_facebook_ok"))
    instagram_ok = bool(manifest.get("meta_instagram_ok"))
    if (
        "meta_facebook_ok" not in manifest
        and "meta_instagram_ok" not in manifest
        and manifest.get("youtube_published")
        and str(manifest.get("status") or "") == "publish_failed"
    ):
        instagram_ok = True
    platforms = []
    if not facebook_ok:
        platforms.append("facebook")
    if not instagram_ok:
        platforms.append("instagram")
    return platforms or ["facebook", "instagram"]


def _record_meta_flags(published: list[dict]) -> tuple[bool, bool]:
    facebook_ok = True
    instagram_ok = True
    seen = False
    for item in published:
        for row in item.get("results") or []:
            if row.get("channel") != "meta":
                continue
            seen = True
            platforms = (row.get("result") or {}).get("platforms") or []
            if not platforms:
                facebook_ok = facebook_ok and bool(row.get("success"))
                instagram_ok = instagram_ok and bool(row.get("success"))
                continue
            for platform in platforms:
                name = str(platform.get("platform") or "")
                ok = bool(platform.get("success"))
                if name == "facebook":
                    facebook_ok = facebook_ok and ok
                elif name == "instagram":
                    instagram_ok = instagram_ok and ok
    return (facebook_ok if seen else False, instagram_ok if seen else False)


def _publish_chinese_meta(item: dict, run_id: str, platforms: list[str]) -> list[dict]:
    results = []
    folder = str(run_id or "run").strip() or "run"
    selected = [name for name in platforms if name in ("facebook", "instagram")]
    if not selected:
        return results
    meta_account = str(item.get("youtube_account") or WORKFLOW_ID)
    for index, video in enumerate(item["videos"], 1):
        title = str(video.get("title") or item["title"])
        description = _description(title, item["tags"])
        try:
            hosted = upload_public_file(
                video["output_path"],
                f"language_learning/{folder}/part-{index:02d}.mp4",
            )
            upload = publish_to_meta(
                video["output_path"],
                title,
                description=description,
                video_url=hosted["url"],
                platforms=selected,
                account=meta_account,
            )
            results.append({
                "channel": "meta",
                "video": video,
                "success": all(row.get("success") for row in upload.get("platforms") or []),
                "result": {**upload, "storage": hosted},
            })
        except MetaToolError as error:
            results.append({
                "channel": "meta",
                "video": video,
                "success": False,
                "error": error.to_dict()["error"],
            })
    return results


def _publish_chinese_youtube(item: dict, *, include_youtube: bool, run_id: str, meta_platforms: list[str]) -> dict:
    youtube_account = str(item.get("youtube_account") or WORKFLOW_ID)
    channels = _youtube_channels(item["account_group"], youtube_account) if include_youtube else []
    tags = _normalized_tags(item["tags"])
    language = YOUTUBE_LANGUAGE_BY_MODE["en-zh"]
    results = []
    if include_youtube:
        for video in item["videos"]:
            title = str(video.get("title") or item["title"])
            description = _description(title, item["tags"])
            for account in channels:
                try:
                    upload = publish_to_youtube(
                        account["channel_id"],
                        video["output_path"],
                        title,
                        description=description,
                        tags=tags,
                        category_id=YOUTUBE_LANGUAGE_LEARNING_CATEGORY_ID,
                        privacy_status="public",
                        language=language,
                        account=youtube_account,
                    )
                    results.append({"channel": "youtube", "account": account, "video": video, "success": True, "result": upload})
                except YouTubeToolError as error:
                    results.append({
                        "channel": "youtube",
                        "account": account,
                        "video": video,
                        "success": False,
                        "error": error.to_dict()["error"],
                    })
    results.extend(_publish_chinese_meta(item, run_id, meta_platforms))
    return {
        "learning_mode": item["learning_mode"],
        "account_group": item["account_group"],
        "channel": "youtube+meta" if include_youtube else "meta",
        "youtube_published": include_youtube and all(
            row["success"] for row in results if row.get("channel") == "youtube"
        ),
        "success": all(row["success"] for row in results) if results else False,
        "results": results,
    }


def publish_vocabulary_videos(manifest_path: str | Path, publish_confirmed: bool) -> dict:
    """用户确认后把中文发到 YouTube 与 Facebook/Instagram Reels。韩语仍由 Agent 调矩媒 MCP。"""
    if publish_confirmed is not True:
        raise ConfirmationRequiredError("必须先让用户看过成片并获得明确确认后再发布")
    manifest = _load_manifest(manifest_path)
    include_youtube = _should_publish_youtube(manifest)
    meta_platforms = _meta_platforms(manifest)
    published = []
    matrixmedia_items = []
    for item in manifest["items"]:
        channel = str(item.get("channel") or "")
        mode = str(item.get("learning_mode") or "")
        if mode == "en-zh" and channel == "youtube":
            published.append(_publish_chinese_youtube(
                item,
                include_youtube=include_youtube,
                run_id=str(manifest.get("run_id") or "run"),
                meta_platforms=meta_platforms,
            ))
            continue
        if mode == "en-ko" and channel == "matrixmedia":
            matrixmedia_items.append(item)
            continue
        raise PublishError(f"不支持的发布目标：{mode} / {channel}")
    if not published:
        raise PublishError("发布清单里没有待发的中文视频。仅有韩语时不要调用本工具，确认后直接用矩媒 MCP 发布")
    chinese_success = all(item["success"] for item in published)
    youtube_ok = include_youtube and all(item.get("youtube_published") for item in published)
    if youtube_ok or not include_youtube:
        manifest["youtube_published"] = True
    facebook_ok, instagram_ok = _record_meta_flags(published)
    if "facebook" not in meta_platforms:
        facebook_ok = bool(manifest.get("meta_facebook_ok"))
    if "instagram" not in meta_platforms:
        instagram_ok = True
    manifest["meta_facebook_ok"] = facebook_ok
    manifest["meta_instagram_ok"] = instagram_ok
    manifest["status"] = "published" if chinese_success and not matrixmedia_items else (
        "awaiting_matrixmedia" if chinese_success else "publish_failed"
    )
    Path(manifest_path).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "success": chinese_success,
        "manifest_path": str(Path(manifest_path).resolve()),
        "topic": manifest.get("topic"),
        "run_id": manifest.get("run_id"),
        "published": published,
        "matrixmedia_items": matrixmedia_items,
    }
