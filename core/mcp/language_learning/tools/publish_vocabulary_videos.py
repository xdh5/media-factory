"""语言学习成片发布：中文发 YouTube，韩语由 MatrixMedia 发布到「韩语」。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import unquote, urlparse

from core.tools.r2_storage import download_public_file, upload_public_file
from core.tools.topic_dedup import commit as commit_topic

from .._constants import (
    CHINESE_YOUTUBE_CHANNEL_ID,
    MINIMUM_NEW_WORDS,
    PUBLISH_MANIFEST_FILE_NAME,
    TOPIC_DEDUPLICATION_DAYS,
    WORD_HISTORY_DAYS,
    WORKFLOW_ID,
    YOUTUBE_LANGUAGE_BY_MODE,
    YOUTUBE_LANGUAGE_LEARNING_CATEGORY_ID,
)
from .._errors import ConfirmationRequiredError, PublishError
from .vocabulary_history import build_database_word_entries


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


def prepare_r2_publish_manifest(
    r2_manifest_url: str,
    run_id: str,
    cache_root: str | Path,
) -> str:
    """把 GitHub Action 的 R2 交付清单还原成本地可发布清单和视频。"""
    normalized_run_id = str(run_id or "").strip()
    expected_prefix = f"runs/{WORKFLOW_ID}/{normalized_run_id}/"
    parsed_url = urlparse(str(r2_manifest_url or "").strip())
    object_key = unquote(parsed_url.path.lstrip("/"))
    if parsed_url.scheme not in {"http", "https"} or object_key != f"{expected_prefix}r2-manifest.json":
        raise PublishError(
            "manifest_path 必须是本地发布清单，或与 run_id 对应的 R2 r2-manifest.json 公网地址",
            {"run_id": normalized_run_id, "manifest_path": str(r2_manifest_url)},
        )

    destination = Path(cache_root).resolve() / "r2-publish"
    r2_manifest_path = destination / "r2-manifest.json"
    download_public_file(object_key, r2_manifest_path)
    try:
        r2_manifest = json.loads(r2_manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PublishError(f"读取 R2 交付清单失败：{error}") from error
    if str(r2_manifest.get("run_id") or "") != normalized_run_id:
        raise PublishError(
            "R2 交付清单的 run_id 与发布请求不一致",
            {"expected": normalized_run_id, "actual": r2_manifest.get("run_id")},
        )

    r2_files = list(r2_manifest.get("r2_files") or [])
    publish_file = next(
        (item for item in r2_files if str(item.get("source_name") or "") == PUBLISH_MANIFEST_FILE_NAME),
        None,
    )
    if not isinstance(publish_file, dict):
        raise PublishError("R2 交付清单缺少 publish-manifest.json")
    publish_key = str(publish_file.get("key") or "")
    if not publish_key.startswith(expected_prefix):
        raise PublishError("R2 发布清单对象路径与 run_id 不一致")

    publish_manifest_path = destination / PUBLISH_MANIFEST_FILE_NAME
    download_public_file(publish_key, publish_manifest_path)
    manifest = _load_manifest(publish_manifest_path)
    if str(manifest.get("run_id") or "") != normalized_run_id:
        raise PublishError("发布清单的 run_id 与请求不一致")

    files_by_name = {
        str(item.get("source_name") or ""): item
        for item in r2_files
        if str(item.get("source_name") or "")
    }
    videos_dir = destination / "videos"
    for item in manifest.get("items") or []:
        for video in item.get("videos") or []:
            source_name = Path(str(video.get("output_path") or "")).name
            remote = files_by_name.get(source_name)
            if not isinstance(remote, dict):
                raise PublishError(f"R2 交付清单缺少待发布视频：{source_name}")
            video_key = str(remote.get("key") or "")
            if not video_key.startswith(expected_prefix):
                raise PublishError(f"R2 视频对象路径与 run_id 不一致：{source_name}")
            local_video = videos_dir / source_name
            download_public_file(video_key, local_video)
            video["output_path"] = str(local_video)
            video["video_url"] = str(remote.get("url") or "")
            video["r2_key"] = video_key
    publish_manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return str(publish_manifest_path)


def upload_publish_assets_to_r2(
    manifest_path: str | Path,
    subject_sheet_path: str | Path | None = None,
) -> dict:
    """上传语言成片、可选主题图和发布清单，并把公网地址写回本地清单。"""
    path = Path(manifest_path).resolve()
    manifest = _load_manifest(path)
    run_id = str(manifest.get("run_id") or "").strip()
    if not run_id:
        raise PublishError("发布清单缺少 run_id，无法生成 R2 对象路径")
    uploaded: list[dict] = []
    for item in manifest.get("items") or []:
        mode = str(item.get("learning_mode") or "unknown").strip() or "unknown"
        for index, video in enumerate(item.get("videos") or [], 1):
            video_path = Path(str(video.get("output_path") or "")).resolve()
            stored = upload_public_file(
                video_path,
                f"runs/{WORKFLOW_ID}/{run_id}/{mode}/{index:02d}-{video_path.name}",
                content_type="video/mp4",
            )
            video["video_url"] = stored["url"]
            video["r2_key"] = stored["key"]
            uploaded.append({"kind": "video", "learning_mode": mode, **stored})
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
        uploaded.append({"kind": "subject_sheet", **stored})
    manifest["r2_uploaded"] = True
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
    uploaded.append({"kind": "manifest", **stored_manifest})
    return {
        "manifest_path": str(path),
        "manifest_url": stored_manifest["url"],
        "subject_sheet_url": manifest.get("subject_sheet_url"),
        "uploaded": uploaded,
    }


def _youtube_channels(group_name: str, youtube_account: str) -> list[dict]:
    from core.tools.publish_to_youtube import list_youtube_accounts

    account = str(youtube_account or WORKFLOW_ID).strip() or WORKFLOW_ID
    accounts = list_youtube_accounts(account=account)
    if accounts:
        return accounts
    raise PublishError(
        f"YouTube 账号未配置。请在 .env 填写 {account.upper()}_YOUTUBE_CHANNEL_ID、"
        f"{account.upper()}_YOUTUBE_REFRESH_TOKEN、YOUTUBE_OAUTH_CLIENT_ID、"
        f"YOUTUBE_OAUTH_CLIENT_SECRET",
        {"account": account, "account_group": group_name, "channel_id": CHINESE_YOUTUBE_CHANNEL_ID},
    )


def _tiktok_accounts(group_name: str, tiktok_account: str) -> list[dict]:
    from core.tools.publish_to_tiktok import list_tiktok_accounts

    account = str(tiktok_account or WORKFLOW_ID).strip() or WORKFLOW_ID
    accounts = list_tiktok_accounts(account=account)
    if accounts:
        return accounts
    raise PublishError(
        f"TikTok 账号未配置。请在 .env 填写 {account.upper()}_TIKTOK_ACCOUNT_ID、ZERNIO_API_KEY",
        {"account": account, "account_group": group_name},
    )


def _should_publish_youtube(manifest: dict) -> bool:
    """YouTube 已成功时不重复上传。"""
    if manifest.get("youtube_published") is True:
        return False
    return str(manifest.get("status") or "") not in {"awaiting_matrixmedia", "published"}


def _should_publish_tiktok(manifest: dict) -> bool:
    """TikTok 已成功时不重复提交。"""
    return not (
        manifest.get("tiktok_published") is True
        or manifest.get("tiktok_draft_delivered") is True
    )


def _commit_manifest_database(manifest: dict) -> dict:
    """用户通过 MCP 触发发布后，幂等写入正式话题和十个单词。"""
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


def _publish_chinese_youtube(item: dict, publish_at: str | None = None) -> dict:
    youtube_account = str(item.get("youtube_account") or WORKFLOW_ID)
    channels = _youtube_channels(item["account_group"], youtube_account)
    tags = _normalized_tags(item["tags"])
    language = YOUTUBE_LANGUAGE_BY_MODE["en-zh"]
    results = []
    from core.tools.publish_to_youtube import YouTubeToolError, publish_to_youtube

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
                    publish_at=publish_at,
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
    return {
        "learning_mode": item["learning_mode"],
        "account_group": item["account_group"],
        "channel": "youtube",
        "youtube_published": all(
            row["success"] for row in results if row.get("channel") == "youtube"
        ),
        "success": all(row["success"] for row in results) if results else False,
        "results": results,
    }


def _publish_chinese_tiktok(item: dict) -> dict:
    from core.tools.publish_to_tiktok import TikTokToolError, publish_to_tiktok

    tiktok_account = str(item.get("tiktok_account") or item.get("youtube_account") or WORKFLOW_ID)
    accounts = _tiktok_accounts(item["account_group"], tiktok_account)
    results = []
    for video in item["videos"]:
        title = str(video.get("title") or item["title"])
        content = _description(title, item["tags"])
        video_url = str(video.get("video_url") or "").strip()
        for account in accounts:
            try:
                upload = publish_to_tiktok(
                    account["account_id"],
                    video_url,
                    content,
                    account=tiktok_account,
                )
                results.append({"channel": "tiktok", "account": account, "video": video, "success": True, "result": upload})
            except TikTokToolError as error:
                results.append({
                    "channel": "tiktok",
                    "account": account,
                    "video": video,
                    "success": False,
                    "error": error.to_dict()["error"],
                })
    all_succeeded = all(row["success"] for row in results) if results else False
    direct_published = all_succeeded and all(
        str((row.get("result") or {}).get("status") or "") == "published"
        for row in results
    )
    draft_delivered = all_succeeded and any(
        str((row.get("result") or {}).get("status") or "") == "draft_delivered"
        for row in results
    )
    return {
        "learning_mode": item["learning_mode"],
        "account_group": item["account_group"],
        "channel": "tiktok",
        "tiktok_published": direct_published,
        "tiktok_draft_delivered": draft_delivered,
        "success": all_succeeded,
        "results": results,
    }


def publish_vocabulary_videos(
    manifest_path: str | Path,
    publish_confirmed: bool,
    *,
    targets: list[str] | None = None,
    publish_at: str | None = None,
) -> dict:
    """通过语言学习 MCP 把中文视频发布到 YouTube 或 TikTok。"""
    if publish_confirmed is not True:
        raise ConfirmationRequiredError("必须先让用户看过成片并获得明确确认后再发布")
    manifest = _load_manifest(manifest_path)
    database = _commit_manifest_database(manifest)
    selected_targets = {str(item).strip().casefold() for item in (targets or ["youtube", "tiktok"])}
    unknown_targets = selected_targets - {"youtube", "tiktok"}
    if unknown_targets:
        raise PublishError(f"不支持的官方发布目标：{sorted(unknown_targets)}")
    include_youtube = "youtube" in selected_targets and _should_publish_youtube(manifest)
    include_tiktok = "tiktok" in selected_targets and _should_publish_tiktok(manifest)
    published = []
    matrixmedia_items = []
    for item in manifest["items"]:
        channel = str(item.get("channel") or "")
        mode = str(item.get("learning_mode") or "")
        if mode == "en-zh" and channel == "youtube":
            if include_youtube:
                published.append(_publish_chinese_youtube(item, publish_at=publish_at))
            if include_tiktok:
                published.append(_publish_chinese_tiktok(item))
            continue
        if mode == "en-ko" and channel == "matrixmedia":
            matrixmedia_items.append(item)
            continue
        raise PublishError(f"不支持的发布目标：{mode} / {channel}")
    if not published:
        raise PublishError("发布清单里没有待发的中文视频。仅有韩语时不要调用本工具，确认后直接用矩媒 MCP 发布")
    chinese_success = all(item["success"] for item in published)
    youtube_ok = include_youtube and all(
        item.get("youtube_published") for item in published if item.get("channel") == "youtube"
    )
    if "youtube" in selected_targets and youtube_ok:
        manifest["youtube_published"] = True
    tiktok_ok = include_tiktok and all(
        item.get("tiktok_published") for item in published if item.get("channel") == "tiktok"
    )
    if "tiktok" in selected_targets and tiktok_ok:
        manifest["tiktok_published"] = True
    tiktok_draft_ok = include_tiktok and all(
        item.get("tiktok_published") or item.get("tiktok_draft_delivered")
        for item in published
        if item.get("channel") == "tiktok"
    )
    if "tiktok" in selected_targets and tiktok_draft_ok and not tiktok_ok:
        manifest["tiktok_draft_delivered"] = True
    manifest["status"] = "published" if chinese_success and not matrixmedia_items else (
        "awaiting_matrixmedia" if chinese_success else "publish_failed"
    )
    Path(manifest_path).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "success": chinese_success,
        "manifest_path": str(Path(manifest_path).resolve()),
        "topic": manifest.get("topic"),
        "run_id": manifest.get("run_id"),
        "database": database,
        "published": published,
        "matrixmedia_items": matrixmedia_items,
    }
