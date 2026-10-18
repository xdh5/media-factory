"""GitHub Runner 执行已冻结的动漫清单，无文本模型、转写或生图调用。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import time
import traceback
import threading
from datetime import datetime, timezone
from pathlib import Path

from core.mcp.anime._constants import OUTPUT_ROOT, SEGMENTATION_DURATION, SEGMENTATION_EPISODES
from core.mcp.anime._errors import AnimeError
from core.mcp.anime.services.compile import _probe, _write_json, assemble_videos
from core.mcp.anime.services.github_execution import planned_part_count, validate_copy
from core.mcp.anime.services.youtube import _file_sha256, _part_title, publish_youtube
from core.tools.media_files import download_public_file, upload_public_file
from core.tools.media_files.storage import _client, _settings
from core.tools.publish_media.accounts import resolve_account_group
from download_video import download
from ops.anime.download_checkpoint import CheckpointUploader


def verify_authorization() -> None:
    """只读核验 Action Secret 的 OAuth、频道身份和上传权限，不发布视频。"""
    import requests
    from core.tools.media_records import list_publishing_account_groups
    from core.tools.publish_media.publisher import _publishing

    _publishing()
    from platform_api.account_registry import account_context, verify_account
    from platform_api.youtube.publish_to_youtube import _load_credentials

    database = list_publishing_account_groups(business_line="anime")
    count = 0
    for group in database["groups"]:
        for route in resolve_account_group(group["name"], "anime", ["youtube"]):
            verify_account(route)
            with account_context(route) as account:
                credentials = _load_credentials(route["platform_account_id"], account)
                try:
                    response = requests.get("https://oauth2.googleapis.com/tokeninfo",
                                            params={"access_token": credentials.token}, timeout=30)
                except requests.RequestException:
                    raise AnimeError("YouTube 权限核验网络失败，未执行发布") from None
                if not response.ok:
                    raise AnimeError("YouTube 权限核验失败，未执行发布")
                scopes = set(response.json().get("scope", "").split())
                required = {
                    "https://www.googleapis.com/auth/youtube.upload",
                    "https://www.googleapis.com/auth/youtube.force-ssl",
                }
                if not required.issubset(scopes) and "https://www.googleapis.com/auth/youtube" not in scopes:
                    raise AnimeError("YouTube OAuth 缺少上传或播放列表管理权限")
                count += 1
    if not count:
        raise AnimeError("未配置动漫 YouTube 频道")
    print(f"动漫 YouTube OAuth、频道身份、上传及播放列表权限验证通过，共 {count} 个频道", flush=True)


def execute_package(execution_id: str) -> dict:
    """后台分块保存下载进度，每段拼好后立即持久化并发布。"""
    if not re.fullmatch(r"[a-f0-9]{32}", execution_id):
        raise AnimeError("执行 ID 必须是 32 位十六进制")
    prefix = f"runs/anime/executions/{execution_id}"
    directory = OUTPUT_ROOT / f"github-{execution_id}"
    directory.mkdir(parents=True, exist_ok=True)
    settings = _settings()
    client = _client(settings["R2_ACCOUNT_ID"], settings["R2_ACCESS_KEY_ID"], settings["R2_SECRET_ACCESS_KEY"])

    def exists(key: str) -> bool:
        try:
            client.head_object(Bucket=settings["R2_BUCKET"], Key=key)
            return True
        except client.exceptions.ClientError as exc:
            if str(exc.response["Error"]["Code"]) in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise

    def save_json(name: str, payload: dict) -> None:
        path = directory / name
        _write_json(path, payload)
        upload_public_file(path, f"{prefix}/{name}", content_type="application/json")

    last_progress_upload = 0.0
    def completed_upload_result(manifest, package):
        """全部上传回执已持久化即完成，不等待 YouTube 后台转码。"""
        from core.tools.media_records import commit_publication_records
        parts = manifest.get("parts") or []
        if not parts or len(parts) != int(manifest.get("part_count") or parts[0].get("part_count") or len(parts)):
            return None
        receipts = []
        for part in parts:
            path = directory / f"youtube-receipt-{part['part_index']}.json"
            if not exists(f"{prefix}/{path.name}"):
                return None
            download_public_file(f"{prefix}/{path.name}", path)
            saved = json.loads(path.read_text(encoding="utf-8"))
            uploaded = saved.get("result") or {}
            if (saved.get("channel_id") != package["channel_id"]
                    or saved.get("video_sha256") != part.get("sha256")
                    or not uploaded.get("video_id") or not uploaded.get("video_url")):
                raise AnimeError(f"第 {part['part_index']} 段上传回执与成片或频道不一致")
            receipts.append((part, saved))
        records = []
        for part, saved in receipts:
            run_id = f"anime-{saved['video_sha256']}"
            records.append({"publication_id": run_id, "run_id": run_id, "business_line": "anime",
                            "platform": "youtube", "connector": "youtube", "account_id": package["channel_id"],
                            "content_part": part["part_index"], "title": saved["title"],
                            "publish_mode": "immediate", "publish_at": datetime.now(timezone.utc).isoformat(),
                            "status": "published", "external_id": saved["result"]["video_id"],
                            "external_url": saved["result"]["video_url"]})
        stored = commit_publication_records(records)["records"]
        by_id = {item["external_id"]: item for item in stored}
        return {"account_group": package["account_group"], "completion_basis": "youtube_upload_receipts",
                "processing_verified": False,
                "message": "全部分段上传完成且回执已保存；YouTube 后台转码不阻塞执行成功",
                "published": [{"record": by_id[saved["result"]["video_id"]], "result": saved["result"]}
                              for part, saved in receipts]}

    phase = "初始化"
    current_source = {}
    downloaded = []
    completed_count = 0
    restored_count = 0
    final_manifest_saved = False
    publish_result = None
    parts_persisted = False
    sources = []
    checkpoints = None
    progress_lock = threading.Lock()

    def diagnostic(event: str, **fields) -> None:
        record = {"timestamp": datetime.now(timezone.utc).isoformat(),
                  "event": event, "execution_id": execution_id, "phase": phase,
                  "source": current_source, **fields}
        line = json.dumps(record, ensure_ascii=False, default=str)
        print(line, flush=True)
        with (directory / "execution-diagnostics.log").open("a", encoding="utf-8") as stream:
            stream.write(line + "\n")

    def progress(message: str) -> None:
        nonlocal last_progress_upload
        print(message, flush=True)
        with progress_lock:
            payload = {"execution_id": execution_id, "status": "running", "message": message,
                       "run_url": run_url, "phase": phase, "completed_source_count": completed_count,
                       "checkpoint_source_count": checkpoints.completed_count if checkpoints else 0}
            _write_json(directory / "result.json", payload)
            # 状态最多每分钟上传一次，检查点上传独立在后台执行。
            if time.monotonic() - last_progress_upload >= 60:
                upload_public_file(directory / "result.json", f"{prefix}/result.json", content_type="application/json")
                last_progress_upload = time.monotonic()

    run_url = f"{os.getenv('GITHUB_SERVER_URL', 'https://github.com')}/{os.getenv('GITHUB_REPOSITORY', '')}/actions/runs/{os.getenv('GITHUB_RUN_ID', '')}"
    try:
        download_public_file(f"{prefix}/package.json", directory / "package.json")
        package = json.loads((directory / "package.json").read_text(encoding="utf-8"))
        version = int(package.get("version") or 0)
        if version not in {1, 2, 3} or package.get("execution_id") != execution_id:
            raise AnimeError("执行包版本或执行 ID 不一致")
        content = {key: value for key, value in package.items() if key not in {"execution_id", "thumbnail_key"}}
        if version >= 2:
            content["thumbnails"] = [
                {key: value for key, value in item.items() if key != "key"}
                for item in package.get("thumbnails") or []
            ]
        expected_id = hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:32]
        if expected_id != execution_id:
            raise AnimeError("执行包内容摘要或封面对象路径不一致")
        validate_copy(
            package["titles"], package["descriptions"], package["tags"],
            require_completed=version >= 2)
        if exists(f"{prefix}/result.json"):
            previous_path = directory / "previous-result.json"
            download_public_file(f"{prefix}/result.json", previous_path)
            previous = json.loads(previous_path.read_text(encoding="utf-8"))
            if previous.get("status") == "succeeded" and previous.get("execution_id") == execution_id:
                print("该执行已成功发布，复用结果，不重新下载或上传", flush=True)
                return previous
        sources = package["sources"]
        if not sources or len({item["aweme_id"] for item in sources}) != len(sources):
            raise AnimeError("执行包来源为空或重复")
        segmentation = package.get("segmentation") or SEGMENTATION_EPISODES
        routes = resolve_account_group(package["account_group"], "anime", ["youtube"])
        if len(routes) != 1 or routes[0]["platform_account_id"] != package["channel_id"]:
            raise AnimeError("账号组目标频道发生变化，停止执行并交回 Agent 判断")
        if version == 1:
            if package["thumbnail_key"] != f"{prefix}/thumbnail.jpg":
                raise AnimeError("执行包封面对象路径不一致")
            download_public_file(package["thumbnail_key"], directory / "youtube-thumbnail-1.jpg")
            if _file_sha256(directory / "youtube-thumbnail-1.jpg") != package["thumbnail_sha256"]:
                raise AnimeError("封面摘要与执行包不一致")
        else:
            if not package.get("thumbnails"):
                raise AnimeError("执行包没有分段封面")
            for item in package["thumbnails"]:
                index = int(item["index"])
                expected_key = f"{prefix}/thumbnail-{index}.jpg"
                if item.get("key") != expected_key:
                    raise AnimeError("执行包分段封面对象路径不一致")
                path = directory / f"youtube-thumbnail-{index}.jpg"
                download_public_file(expected_key, path)
                if _file_sha256(path) != item["sha256"]:
                    raise AnimeError("分段封面摘要与执行包不一致")
        _write_json(directory / "youtube-intro-1.json", package["intro"])
        assembled = directory / "manifest.json"
        if exists(f"{prefix}/manifest.json"):
            phase = "恢复最终成片"
            progress("恢复已拼接成片")
            download_public_file(f"{prefix}/manifest.json", assembled)
            manifest = json.loads(assembled.read_text(encoding="utf-8"))
            publish_result = completed_upload_result(manifest, package)
            for part in manifest["parts"]:
                receipt_name = f"youtube-receipt-{part['part_index']}.json"
                if exists(f"{prefix}/{receipt_name}"):
                    receipt = directory / receipt_name
                    download_public_file(f"{prefix}/{receipt_name}", receipt)
                    saved = json.loads(receipt.read_text(encoding="utf-8"))
                    if saved.get("video_sha256") != part.get("sha256"):
                        raise AnimeError("YouTube 回执与成片清单摘要不一致")
                    part["video_path"] = str(directory / Path(part["video_path"]).name)
                    continue
                path = directory / Path(part["video_path"]).name
                download_public_file(f"{prefix}/{path.name}", path)
                if _file_sha256(path) != part["sha256"]:
                    raise AnimeError("恢复成片摘要不一致")
                part["video_path"] = str(path)
            _write_json(assembled, manifest)
            final_manifest_saved = True
        else:
            phase = "恢复下载检查点"
            checkpoints = CheckpointUploader(
                directory, prefix, execution_id, sources, exists, download_public_file, upload_public_file,
                lambda message: print(message, flush=True), segmentation=segmentation)
            restored_count = checkpoints.completed_count
            completed_count = restored_count
            for order, work in enumerate(sources[restored_count:], restored_count + 1):
                phase = "下载来源"
                current_source = {"order": order, "total": len(sources), "expected_id": str(work["aweme_id"]),
                                  "work_url": work["work_url"], "expected_title": work.get("title"),
                                  "expected_duration_seconds": work.get("duration_seconds")}
                diagnostic("开始下载来源")
                progress(f"下载来源 {order}/{len(sources)}")
                path = directory / f"source-{order}.mp4"
                metadata_path = path.with_suffix(".json")
                metadata = download(work["work_url"], path)
                _write_json(metadata_path, metadata)
                diagnostic("下载解析结果", actual_id=str(metadata.get("video_id")),
                           actual_title=metadata.get("title"), local_file=path.name)
                if str(metadata.get("video_id")) != str(work["aweme_id"]):
                    raise AnimeError("下载来源 ID 与执行清单不一致，交回 Agent 判断", {
                        **current_source, "actual_id": str(metadata.get("video_id")),
                        "actual_title": metadata.get("title")})
                phase = "校验来源时长"
                probe = _probe(path)
                expected = float(work["duration_seconds"])
                diagnostic("来源时长校验", actual_duration_seconds=probe["duration"],
                           actual_id=str(metadata.get("video_id")), actual_title=metadata.get("title"))
                if expected <= 0 or abs(probe["duration"] - expected) > max(5, expected * 0.02):
                    raise AnimeError("来源实际时长与执行清单不符，交回 Agent 判断", {
                        **current_source, "actual_duration_seconds": probe["duration"]})
                checkpoints.add({**metadata, "path": path, "duration": probe["duration"], "probe": probe,
                                 "order": order, "share_text": work["work_url"]}, order)
                completed_count = order
            downloaded = checkpoints.final_sources()
            restored_count = checkpoints.completed_count
            current_source = {}
            phase = "拼接最终成片"
            completed_parts: dict[int, dict] = {}
            expected_part_count = planned_part_count(sources, segmentation)
            for index in range(1, expected_part_count + 1):
                receipt_name = f"youtube-receipt-{index}.json"
                if not exists(f"{prefix}/{receipt_name}"):
                    continue
                receipt = directory / receipt_name
                download_public_file(f"{prefix}/{receipt_name}", receipt)
                saved = json.loads(receipt.read_text(encoding="utf-8"))
                if not saved.get("video_sha256") or not (saved.get("result") or {}).get("video_id"):
                    raise AnimeError(f"第 {index} 段 YouTube 回执不完整")
                completed_parts[index] = {"sha256": saved["video_sha256"]}
            if completed_parts:
                parts_persisted = True
                progress(f"已根据 YouTube 回执跳过前 {len(completed_parts)} 段，不读取 R2 成片")

            def publish_ready_part(partial_manifest: dict) -> None:
                """每段上传完成并保存回执后立即处理下一段，不等待 YouTube 转码。"""
                nonlocal phase, publish_result, parts_persisted
                part = partial_manifest["parts"][-1]
                path = Path(part["video_path"])
                part["sha256"] = _file_sha256(path)
                phase = f"上传第 {part['part_index']}/{part['part_count']} 段成片"
                progress(phase)
                upload_public_file(path, f"{prefix}/{path.name}")
                parts_persisted = True
                _write_json(assembled, partial_manifest)
                index = int(part["part_index"])
                count = int(part["part_count"])
                if version == 1 and index > 1:
                    shutil.copy2(directory / "youtube-thumbnail-1.jpg",
                                 directory / f"youtube-thumbnail-{index}.jpg")
                _write_json(directory / f"youtube-thumbnail-{index}.json", {
                    "title": _part_title(package["titles"][0], index, count),
                    "video_sha256": part["sha256"]})
                for ready in partial_manifest["parts"]:
                    name = f"youtube-receipt-{ready['part_index']}.json"
                    receipt = directory / name
                    if not receipt.is_file() and exists(f"{prefix}/{name}"):
                        download_public_file(f"{prefix}/{name}", receipt)
                phase = f"发布第 {part['part_index']}/{part['part_count']} 段到 YouTube"
                publish_result = publish_youtube(
                    str(assembled), package["titles"], package["descriptions"], package["tags"],
                    package["account_group"], progress,
                    receipt_saved=lambda receipt: upload_public_file(
                        receipt, f"{prefix}/{receipt.name}", content_type="application/json"),
                    playlist_title=package.get("series_name") or "",
                    require_completed=version >= 2,
                    verify_processing=False,
                )
                phase = "拼接最终成片"

            if len(sources) == 1 and segmentation != SEGMENTATION_DURATION:
                progress("单个现成合集直接复用原文件")
                source = downloaded[0]
                path = directory / "part-1.mp4"
                shutil.copy2(source["path"], path)
                manifest = {"original_file": True, "parts": [{"part_index": 1, "part_count": 1,
                            "video_path": str(path), "duration_seconds": source["duration"],
                            "title": source.get("title"), "description": source.get("description"),
                            "topics": source.get("topics") or []}]}
                _write_json(assembled, manifest)
            else:
                manifest = assemble_videos(
                    downloaded, directory, progress=progress, part_ready=publish_ready_part,
                    completed_parts=completed_parts, segmentation=segmentation)
            phase = "上传最终成片"
            if not parts_persisted:
                for part in manifest["parts"]:
                    path = Path(part["video_path"])
                    part["sha256"] = _file_sha256(path)
                    upload_public_file(path, f"{prefix}/{path.name}")
            for part in manifest["parts"]:
                if "sha256" not in part:
                    part["sha256"] = _file_sha256(Path(part["video_path"]))
            manifest["selection_reason"] = package["selection_reason"]
            save_json("manifest.json", manifest)
            final_manifest_saved = True
            # 持久化的上传回执齐全即成功；平台转码与 Action 上传完成是两个阶段。
            publish_result = completed_upload_result(manifest, package)
        if publish_result is None:
            phase = "发布 YouTube"
            for part in manifest["parts"]:
                index = int(part["part_index"])
                count = int(part.get("part_count") or len(manifest["parts"]))
                if version == 1 and index > 1:
                    shutil.copy2(directory / "youtube-thumbnail-1.jpg",
                                 directory / f"youtube-thumbnail-{index}.jpg")
                _write_json(directory / f"youtube-thumbnail-{index}.json", {
                    "title": _part_title(package["titles"][0], index, count),
                    "video_sha256": part.get("sha256") or _file_sha256(Path(part["video_path"]))})
                name = f"youtube-receipt-{part['part_index']}.json"
                if exists(f"{prefix}/{name}"):
                    download_public_file(f"{prefix}/{name}", directory / name)
            publish_result = publish_youtube(
                str(assembled), package["titles"], package["descriptions"], package["tags"],
                package["account_group"], progress,
                receipt_saved=lambda receipt: upload_public_file(
                    receipt, f"{prefix}/{receipt.name}", content_type="application/json"),
                playlist_title=package.get("series_name") or "",
                require_completed=version >= 2, verify_processing=False)
            publish_result = completed_upload_result(manifest, package)
            if publish_result is None:
                raise AnimeError("分段上传回执未保存完整，不能登记执行成功")
        result = publish_result
        result.update({"execution_id": execution_id, "status": "succeeded", "run_url": run_url,
                       "selection_reason": package["selection_reason"]})
        save_json("result.json", result)
        summary = os.getenv("GITHUB_STEP_SUMMARY")
        if summary:
            with open(summary, "a", encoding="utf-8") as stream:
                stream.write(f"动漫执行完成：{execution_id}\n\n")
                for item in result["published"]:
                    record = item["record"]
                    stream.write(f"- [{record['title']}]({record['external_url']})\n")
        return result
    except Exception as exc:
        # 只记录可定位问题的字段，不记录 Cookie、请求头或临时下载地址。
        details = getattr(exc, "details", {}) or {}
        safe_details = {key: details[key] for key in (
            "expected_id", "actual_id", "actual_title", "actual_duration_seconds",
            "video_id", "returned_ids", "returned_titles", "status_code",
        ) if key in details}
        failure_phase = phase
        diagnostic("执行失败", error_type=type(exc).__name__, error=str(exc), details=safe_details)
        (directory / "failure-traceback.log").write_text(traceback.format_exc(), encoding="utf-8")
        checkpoint_error = None
        if not final_manifest_saved and checkpoints is not None:
            try:
                phase = "保存失败检查点"
                restored_count = checkpoints.finish()
            except Exception as checkpoint_exc:
                restored_count = checkpoints.completed_count
                checkpoint_error = str(checkpoint_exc)
                (directory / "checkpoint-traceback.log").write_text(traceback.format_exc(), encoding="utf-8")
                diagnostic("检查点保存失败", error_type=type(checkpoint_exc).__name__, error=checkpoint_error)
        failure = {"execution_id": execution_id, "status": "failed", "run_url": run_url,
                                   "error": exc.message if isinstance(exc, AnimeError) else type(exc).__name__,
                                   "phase": failure_phase, "source": current_source, "details": safe_details,
                                   "completed_source_count": completed_count, "checkpoint_source_count": restored_count,
                                   "resume_from_source_order": None if final_manifest_saved else restored_count + 1,
                                   "recovery_mode": "final_manifest" if final_manifest_saved else "download_checkpoint",
                                   "checkpoint_error": checkpoint_error,
                                   "message": "失败进度和已持久化回执保留；不自动替换来源，修复后重跑同一执行 ID"}
        try:
            save_json("result.json", failure)
        except Exception as result_exc:
            diagnostic("失败结果上传失败", error_type=type(result_exc).__name__)
        raise
    finally:
        if checkpoints is not None:
            checkpoints.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="执行 Agent 准备的动漫生产发布包")
    parser.add_argument("--execution-id")
    parser.add_argument("--verify-auth-only", action="store_true", help="只读验证 GitHub Secret 的 YouTube 上传授权")
    arguments = parser.parse_args()
    if arguments.verify_auth_only:
        verify_authorization()
    elif arguments.execution_id:
        execute_package(arguments.execution_id)
    else:
        parser.error("执行发布必须提供 --execution-id")
