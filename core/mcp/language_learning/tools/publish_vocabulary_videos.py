"""语言学习成片发布：中文发官方平台，韩语由 MatrixMedia 发布到「韩语」。"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

from core.tools.r2_storage import download_public_file, upload_public_file
from core.tools.cloudflare_data import commit_production_outputs, commit_publication_records, list_publication_records
from core.tools.topic_dedup import commit as commit_topic

from .._constants import (
    CHINESE_YOUTUBE_CHANNEL_ID,
    MATRIXMEDIA_AI_CREATIVE_STATEMENT,
    MINIMUM_NEW_WORDS,
    PUBLISH_MANIFEST_FILE_NAME,
    TOPIC_DEDUPLICATION_DAYS,
    WORD_HISTORY_DAYS,
    WORKFLOW_ID,
    YOUTUBE_LANGUAGE_BY_MODE,
    YOUTUBE_LANGUAGE_LEARNING_CATEGORY_ID,
    QUIZ_TITLE_SUFFIXES,
    video_content_kind,
    video_production_id,
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


def _description(short_title: str, tags: list[str]) -> str:
    hashtags = _hashtags(tags)
    return "\n\n".join(part for part in (str(short_title or "").strip(), hashtags) if part)


def _korean_description(tags: list[str]) -> str:
    """韩语作品描述只发 hashtag，不含短标题或其它正文。"""
    return _hashtags(tags)


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
    """给成片补上发布清单。发布目标由 SKILL 传入的 publish_config 决定。"""
    topic = str(video_result.get("topic") or "").strip()
    topic_english = str(words_by_mode.get("_topic_english") or topic).strip()
    youtube_items = []
    matrixmedia_items = []
    for video in video_result.get("videos") or []:
        mode = str(video.get("learning_mode") or "")
        video_format = _video_format(video)
        if mode == "en-zh":
            zh_config = _mode_config(publish_config, "en-zh")
            title = _titled(build_video_title("en-zh", topic_english), video_format, "en-zh")
            youtube_items.append({
                "learning_mode": "en-zh",
                "video_format": video_format,
                "account_group": str(zh_config.get("account_group") or ""),
                "youtube_account": str(zh_config.get("youtube_account") or WORKFLOW_ID),
                "channel": "youtube",
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
            matrixmedia_items.append({
                "learning_mode": "en-ko",
                "video_format": video_format,
                "account_group": str(ko_config.get("account_group") or ""),
                "channel": "matrixmedia",
                "creativeStatement": MATRIXMEDIA_AI_CREATIVE_STATEMENT,
                "title": title,
                "tags": list(ko_config.get("tags") or []),
                "short_title": short_title,
                "description": _korean_description(list(ko_config.get("tags") or [])),
                "platforms": list(ko_config.get("platforms") or []),
                "videos": _video_parts(video, title, empty_error="en-ko 没有可发布的视频文件"),
            })
    if not youtube_items and not matrixmedia_items:
        return {**video_result, "status": "done"}
    output_dir = Path(video_result["output_dir"]).resolve()
    manifest_path = output_dir / PUBLISH_MANIFEST_FILE_NAME
    kept_youtube = []
    kept_matrixmedia = []
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
                continue
            mode = str(item.get("learning_mode") or "")
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
    output_records = []
    for item in manifest.get("items") or []:
        mode = str(item.get("learning_mode") or "unknown").strip() or "unknown"
        video_format = _video_format(item)
        content_kind = video_content_kind(mode, video_format)
        for index, video in enumerate(item.get("videos") or [], 1):
            video_path = Path(str(video.get("output_path") or "")).resolve()
            stored = upload_public_file(
                video_path,
                f"runs/{WORKFLOW_ID}/{run_id}/{content_kind}/{index:02d}-{video_path.name}",
                content_type="video/mp4",
            )
            video["video_url"] = stored["url"]
            video["r2_key"] = stored["key"]
            uploaded.append({"kind": "video", "learning_mode": mode, "video_format": video_format, **stored})
            if manifest.get("production_source") == "local_mcp":
                output_records.append({
                    "production_id": video_production_id("local_mcp", run_id, mode, video_format, index),
                    "run_id": run_id,
                    "publish_date": str(manifest.get("publish_date") or "").strip(),
                    "business_line": WORKFLOW_ID,
                    "content_kind": content_kind,
                    "content_part": index,
                    "title": str(video.get("title") or item.get("title") or "").strip(),
                    "hashtags": _hashtags(list(item.get("tags") or [])),
                    "source": "local_mcp",
                    "local_path": str(video_path),
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
        uploaded.append({"kind": "subject_sheet", **stored})
    manifest["r2_uploaded"] = True
    if output_records:
        manifest["production_outputs"] = commit_production_outputs(output_records)
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


def _item_video_rows(item: dict) -> list[tuple[str, int]]:
    return [
        (str(video.get("title") or item.get("title") or "").strip(), index)
        for index, video in enumerate(item.get("videos") or [], 1)
    ]


def _publication_keys(manifest: dict) -> set[tuple[str, str, int]]:
    publish_date = str(manifest.get("publish_date") or "").strip()
    if not publish_date:
        return set()
    return {
        (
            str(item.get("title") or "").strip(),
            str(item.get("platform") or "").strip(),
            int(item.get("content_part") or 1),
        )
        for item in list_publication_records(business_line="language_learning", publish_date=publish_date)
    }


def _recorded_parts(item: dict, platform: str, recorded: set[tuple[str, str, int]]) -> set[int]:
    return {part for title, part in _item_video_rows(item) if title and (title, platform, part) in recorded}


def _item_status(manifest: dict, item: dict) -> dict:
    status = manifest.get("platform_status")
    if not isinstance(status, dict):
        return {}
    current = status.get(_item_key(item))
    return dict(current) if isinstance(current, dict) else {}


def _set_item_status(manifest: dict, item: dict, **updates) -> None:
    status = dict(manifest.get("platform_status") or {})
    key = _item_key(item)
    current = dict(status.get(key) or {})
    current.update(updates)
    status[key] = current
    manifest["platform_status"] = status


def _is_standard_item(item: dict) -> bool:
    return _video_format(item) == "standard"


def _should_publish_youtube(
    manifest: dict,
    item: dict,
    recorded: set[tuple[str, str, int]],
) -> bool:
    """YouTube 已成功时不重复上传；按原版/问答版分别判断。"""
    if _recorded_parts(item, "youtube", recorded) >= {part for _, part in _item_video_rows(item)}:
        return False
    if _item_status(manifest, item).get("youtube") is True:
        return False
    if _is_standard_item(item) and manifest.get("youtube_published") is True:
        return False
    return True


def _should_publish_tiktok(
    manifest: dict,
    item: dict,
    recorded: set[tuple[str, str, int]],
) -> bool:
    """TikTok 已成功时不重复提交；按原版/问答版分别判断。"""
    if _recorded_parts(item, "tiktok", recorded) >= {part for _, part in _item_video_rows(item)}:
        return False
    status = _item_status(manifest, item)
    if status.get("tiktok") is True or status.get("tiktok_scheduled") is True or status.get("tiktok_draft") is True:
        return False
    if _is_standard_item(item) and (
        manifest.get("tiktok_published") is True
        or manifest.get("tiktok_scheduled") is True
        or manifest.get("tiktok_draft_delivered") is True
    ):
        return False
    return True


def _pending_item_parts(
    manifest: dict,
    item: dict,
    platform: str,
    video_parts: list[int] | None,
    recorded: set[tuple[str, str, int]],
) -> set[int]:
    total = {index for index, _ in enumerate(item.get("videos") or [], 1)}
    requested = {int(part) for part in video_parts} if video_parts else set(total)
    requested &= total
    published = {int(part) for part in (_item_status(manifest, item).get(f"{platform}_parts") or [])}
    if _is_standard_item(item):
        published |= {int(part) for part in (manifest.get(f"{platform}_published_parts") or [])}
    published |= _recorded_parts(item, platform, recorded)
    return requested - published


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


def _commit_platform_publications(manifest: dict, published: list[dict]) -> dict:
    """把各平台成功或已预约的结果幂等写入统一发布记录。"""
    database = manifest.get("database_commit") or {}
    publication_id = str(database.get("publication_id") or "").strip()
    run_id = str(database.get("run_id") or manifest.get("run_id") or "").strip()
    records = []
    for batch in published:
        platform = str(batch.get("channel") or "").strip()
        for row in batch.get("results") or []:
            if not row.get("success"):
                continue
            result = row.get("result") if isinstance(row.get("result"), dict) else {}
            if str(result.get("status") or "") == "draft_delivered":
                continue
            requested_at = str(row.get("publish_at") or result.get("publish_at") or "").strip()
            scheduled = bool(requested_at) or bool(result.get("scheduled")) or result.get("status") == "scheduled"
            publish_at = requested_at or datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
            account = row.get("account") if isinstance(row.get("account"), dict) else {}
            video = row.get("video") if isinstance(row.get("video"), dict) else {}
            account_id = str(
                result.get("account_id")
                or result.get("channel_id")
                or account.get("account_id")
                or account.get("page_id")
                or account.get("user_id")
                or account.get("channel_id")
                or ""
            ).strip()
            records.append({
                "publication_id": publication_id,
                "run_id": run_id,
                "business_line": "language_learning",
                "platform": platform,
                "connector": "youtube" if platform == "youtube" else "zernio",
                "account_id": account_id,
                "content_part": int(row.get("part") or 1),
                "title": str(video.get("title") or batch.get("title") or manifest.get("topic") or "").strip(),
                "publish_mode": "scheduled" if scheduled else "immediate",
                "publish_at": publish_at,
                "status": "scheduled" if scheduled else "published",
                "external_id": str(result.get("video_id") or result.get("post_id") or "").strip() or None,
                "external_url": str(result.get("video_url") or result.get("platform_url") or "").strip() or None,
            })
    if not records:
        return {"records": []}
    return commit_publication_records(records)


def _publish_chinese_youtube(item: dict, publish_at: str | None = None) -> dict:
    youtube_account = str(item.get("youtube_account") or WORKFLOW_ID)
    channels = _youtube_channels(item["account_group"], youtube_account)
    tags = _normalized_tags(item["tags"])
    language = YOUTUBE_LANGUAGE_BY_MODE["en-zh"]
    results = []
    from core.tools.publish_to_youtube import YouTubeToolError, publish_to_youtube

    for part, video in enumerate(item["videos"], 1):
        title = str(video.get("title") or item["title"])
        description = _description(item.get("short_title", ""), item["tags"])
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
                results.append({"channel": "youtube", "part": part, "account": account, "video": video, "publish_at": publish_at, "success": True, "result": upload})
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
        "video_format": _video_format(item),
        "account_group": item["account_group"],
        "channel": "youtube",
        "youtube_published": all(
            row["success"] for row in results if row.get("channel") == "youtube"
        ),
        "success": all(row["success"] for row in results) if results else False,
        "results": results,
    }


def _publish_chinese_tiktok(item: dict, publish_at: str | None = None) -> dict:
    from core.tools.publish_to_tiktok import TikTokToolError, publish_to_tiktok

    tiktok_account = str(item.get("tiktok_account") or item.get("youtube_account") or WORKFLOW_ID)
    accounts = _tiktok_accounts(item["account_group"], tiktok_account)
    results = []
    for part, video in enumerate(item["videos"], 1):
        title = str(video.get("title") or item["title"])
        content = _description(item.get("short_title", ""), item["tags"])
        video_url = str(video.get("video_url") or "").strip()
        for account in accounts:
            try:
                upload = publish_to_tiktok(
                    account["account_id"],
                    video_url,
                    content,
                    account=tiktok_account,
                    publish_at=publish_at,
                )
                results.append({"channel": "tiktok", "part": part, "account": account, "video": video, "publish_at": publish_at, "success": True, "result": upload})
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
    scheduled = all_succeeded and all(
        str((row.get("result") or {}).get("status") or "") == "scheduled"
        for row in results
    )
    return {
        "learning_mode": item["learning_mode"],
        "video_format": _video_format(item),
        "account_group": item["account_group"],
        "channel": "tiktok",
        "tiktok_published": direct_published,
        "tiktok_scheduled": scheduled,
        "tiktok_draft_delivered": draft_delivered,
        "success": all_succeeded,
        "results": results,
    }


def _publish_chinese_instagram(
    item: dict,
    video_parts: set[int],
    publish_at: str | None = None,
) -> dict:
    from core.tools.publish_to_instagram import (
        InstagramToolError,
        list_instagram_accounts,
        publish_to_instagram,
    )

    accounts = list_instagram_accounts()
    if not accounts:
        raise PublishError(
            "Zernio 尚未连接 Instagram 专业账号。请先在 Zernio 完成 Instagram OAuth 连接"
        )
    results = []
    for part, video in enumerate(item["videos"], 1):
        if part not in video_parts:
            continue
        title = str(video.get("title") or item["title"])
        caption = _description(item.get("short_title", ""), item["tags"])
        video_url = str(video.get("video_url") or "").strip()
        for account in accounts:
            try:
                upload = publish_to_instagram(
                    account["user_id"],
                    video_url,
                    caption,
                    share_to_feed=True,
                    publish_at=publish_at,
                )
                results.append({
                    "channel": "instagram",
                    "part": part,
                    "account": account,
                    "video": video,
                    "publish_at": publish_at,
                    "success": True,
                    "result": upload,
                })
            except InstagramToolError as error:
                results.append({
                    "channel": "instagram",
                    "part": part,
                    "account": account,
                    "video": video,
                    "success": False,
                    "error": error.to_dict()["error"],
                })
    succeeded_parts = sorted({row["part"] for row in results if row["success"]})
    return {
        "learning_mode": item["learning_mode"],
        "video_format": _video_format(item),
        "account_group": item["account_group"],
        "channel": "instagram",
        "instagram_published_parts": succeeded_parts,
        "success": all(row["success"] for row in results) if results else False,
        "results": results,
    }


def _publish_chinese_facebook(
    item: dict,
    video_parts: set[int],
    publish_at: str | None = None,
) -> dict:
    from core.tools.publish_to_facebook import (
        FacebookToolError,
        list_facebook_accounts,
        publish_to_facebook,
    )

    accounts = list_facebook_accounts()
    if not accounts:
        raise PublishError(
            "Zernio 尚未连接 Facebook Page。请先在 Zernio 完成 Facebook OAuth 连接"
        )
    results = []
    for part, video in enumerate(item["videos"], 1):
        if part not in video_parts:
            continue
        title = str(video.get("title") or item["title"])
        description = _description(item.get("short_title", ""), item["tags"])
        video_url = str(video.get("video_url") or "").strip()
        for account in accounts:
            try:
                upload = publish_to_facebook(
                    account["page_id"],
                    video_url,
                    description,
                    title=title,
                    publish_at=publish_at,
                )
                results.append({
                    "channel": "facebook",
                    "part": part,
                    "account": account,
                    "video": video,
                    "publish_at": publish_at,
                    "success": True,
                    "result": upload,
                })
            except FacebookToolError as error:
                results.append({
                    "channel": "facebook",
                    "part": part,
                    "account": account,
                    "video": video,
                    "success": False,
                    "error": error.to_dict()["error"],
                })
    succeeded_parts = sorted({row["part"] for row in results if row["success"]})
    return {
        "learning_mode": item["learning_mode"],
        "video_format": _video_format(item),
        "account_group": item["account_group"],
        "channel": "facebook",
        "facebook_published_parts": succeeded_parts,
        "success": all(row["success"] for row in results) if results else False,
        "results": results,
    }


def publish_vocabulary_videos(
    manifest_path: str | Path,
    publish_confirmed: bool,
    *,
    targets: list[str] | None = None,
    publish_at: str | None = None,
    publish_at_by_target: dict[str, str | None] | None = None,
    video_parts: list[int] | None = None,
    progress=None,
) -> dict:
    """通过语言学习 MCP 把中文视频发布到 YouTube、TikTok、Instagram 或 Facebook。"""
    if publish_confirmed is not True:
        raise ConfirmationRequiredError("必须先让用户看过成片并获得明确确认后再发布")
    manifest = _load_manifest(manifest_path)
    database = _commit_manifest_database(manifest)
    selected_targets = {str(item).strip().casefold() for item in (targets or ["youtube", "tiktok"])}
    unknown_targets = selected_targets - {"youtube", "tiktok", "instagram", "facebook"}
    if unknown_targets:
        raise PublishError(f"不支持的官方发布目标：{sorted(unknown_targets)}")

    def _publish_time(target: str) -> str | None:
        if isinstance(publish_at_by_target, dict) and target in publish_at_by_target:
            return publish_at_by_target[target]
        return publish_at

    include_youtube = "youtube" in selected_targets
    include_tiktok = "tiktok" in selected_targets
    include_instagram = "instagram" in selected_targets
    include_facebook = "facebook" in selected_targets
    recorded = _publication_keys(manifest)
    published = []
    matrixmedia_items = []
    for item in manifest["items"]:
        channel = str(item.get("channel") or "")
        mode = str(item.get("learning_mode") or "")
        if mode == "en-zh" and channel == "youtube":
            instagram_parts = _pending_item_parts(manifest, item, "instagram", video_parts, recorded)
            facebook_parts = _pending_item_parts(manifest, item, "facebook", video_parts, recorded)
            if include_youtube and _should_publish_youtube(manifest, item, recorded):
                if progress is not None:
                    progress(f"正在发布 YouTube：{item.get('title') or ''}")
                published.append(_publish_chinese_youtube(item, publish_at=_publish_time("youtube")))
            if include_tiktok and _should_publish_tiktok(manifest, item, recorded):
                if progress is not None:
                    progress(f"正在发布 TikTok：{item.get('title') or ''}")
                published.append(_publish_chinese_tiktok(item, _publish_time("tiktok")))
            if include_instagram and instagram_parts:
                published.append(
                    _publish_chinese_instagram(item, instagram_parts, _publish_time("instagram"))
                )
            if include_facebook and facebook_parts:
                published.append(
                    _publish_chinese_facebook(item, facebook_parts, _publish_time("facebook"))
                )
            continue
        if mode == "en-ko" and channel == "matrixmedia":
            matrixmedia_items.append(item)
            continue
        raise PublishError(f"不支持的发布目标：{mode} / {channel}")
    zh_items = [
        item
        for item in manifest["items"]
        if str(item.get("learning_mode") or "") == "en-zh"
        and str(item.get("channel") or "") == "youtube"
    ]
    if not published:
        if not zh_items:
            raise PublishError("发布清单里没有待发的中文视频。仅有韩语时不要调用本工具，确认后直接用矩媒 MCP 发布")
        chinese_success = True
        publication_records = {"records": []}
        completed_targets = sorted(selected_targets)
        manifest["status"] = "published" if not matrixmedia_items else "awaiting_matrixmedia"
        Path(manifest_path).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return {
            "success": True,
            "skipped": True,
            "completed_targets": completed_targets,
            "manifest_path": str(Path(manifest_path).resolve()),
            "topic": manifest.get("topic"),
            "run_id": manifest.get("run_id"),
            "database": database,
            "publication_records": publication_records,
            "published": [],
            "matrixmedia_items": matrixmedia_items,
        }
    chinese_success = all(item["success"] for item in published)
    for batch in published:
        item = next(
            (
                candidate
                for candidate in manifest["items"]
                if str(candidate.get("learning_mode") or "") == str(batch.get("learning_mode") or "")
                and _video_format(candidate) == _video_format(batch)
                and str(candidate.get("channel") or "") == "youtube"
            ),
            None,
        )
        if item is None:
            continue
        channel = str(batch.get("channel") or "")
        if channel == "youtube" and batch.get("youtube_published"):
            _set_item_status(manifest, item, youtube=True)
            if _is_standard_item(item):
                manifest["youtube_published"] = True
        if channel == "tiktok" and batch.get("success"):
            if batch.get("tiktok_published"):
                _set_item_status(manifest, item, tiktok=True)
                if _is_standard_item(item):
                    manifest["tiktok_published"] = True
            elif batch.get("tiktok_scheduled"):
                _set_item_status(manifest, item, tiktok_scheduled=True)
                if _is_standard_item(item):
                    manifest["tiktok_scheduled"] = True
            elif batch.get("tiktok_draft_delivered"):
                _set_item_status(manifest, item, tiktok_draft=True)
                if _is_standard_item(item):
                    manifest["tiktok_draft_delivered"] = True
        if channel == "instagram" and batch.get("success"):
            previous = {int(part) for part in (_item_status(manifest, item).get("instagram_parts") or [])}
            completed = {int(part) for part in (batch.get("instagram_published_parts") or [])}
            parts = sorted(previous | completed)
            _set_item_status(manifest, item, instagram_parts=parts)
            if _is_standard_item(item):
                manifest["instagram_published_parts"] = parts
        if channel == "facebook" and batch.get("success"):
            previous = {int(part) for part in (_item_status(manifest, item).get("facebook_parts") or [])}
            completed = {int(part) for part in (batch.get("facebook_published_parts") or [])}
            parts = sorted(previous | completed)
            _set_item_status(manifest, item, facebook_parts=parts)
            if _is_standard_item(item):
                manifest["facebook_published_parts"] = parts
    publication_records = _commit_platform_publications(manifest, published)
    manifest["status"] = "published" if chinese_success and not matrixmedia_items else (
        "awaiting_matrixmedia" if chinese_success else "publish_failed"
    )
    Path(manifest_path).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    completed_targets = []
    for target in selected_targets:
        batches = [item for item in published if str(item.get("channel") or "") == target]
        if batches:
            if all(item.get("success") for item in batches):
                completed_targets.append(target)
            continue
        if zh_items and all(
            _recorded_parts(item, target, recorded) >= {part for _, part in _item_video_rows(item)}
            for item in zh_items
        ):
            completed_targets.append(target)
    return {
        "success": chinese_success,
        "completed_targets": completed_targets,
        "manifest_path": str(Path(manifest_path).resolve()),
        "topic": manifest.get("topic"),
        "run_id": manifest.get("run_id"),
        "database": database,
        "publication_records": publication_records,
        "published": published,
        "matrixmedia_items": matrixmedia_items,
    }
