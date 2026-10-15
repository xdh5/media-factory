"""GitHub Runner 执行已冻结的动漫清单，无文本模型、转写或生图调用。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
from pathlib import Path

from core.mcp.anime._constants import OUTPUT_ROOT
from core.mcp.anime._errors import AnimeError
from core.mcp.anime.services.compile import _probe, _write_json, assemble_videos
from core.mcp.anime.services.github_execution import validate_copy
from core.mcp.anime.services.youtube import _file_sha256, publish_youtube
from core.tools.media_files import download_public_file, upload_public_file
from core.tools.media_files.storage import _client, _settings
from core.tools.publish_media.accounts import resolve_account_group
from download_video import download


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
                if not scopes.intersection({"https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube"}):
                    raise AnimeError("YouTube OAuth 缺少上传权限")
                count += 1
    if not count:
        raise AnimeError("未配置动漫 YouTube 频道")
    print(f"动漫 YouTube OAuth、频道身份和上传权限验证通过，共 {count} 个频道", flush=True)


def execute_package(execution_id: str) -> dict:
    """来源及成片存入 R2；平台回执在上传后立即持久化，重跑继续核验。"""
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

    def progress(message: str) -> None:
        print(message, flush=True)
        save_json("result.json", {"execution_id": execution_id, "status": "running", "message": message,
                                   "run_url": run_url})

    run_url = f"{os.getenv('GITHUB_SERVER_URL', 'https://github.com')}/{os.getenv('GITHUB_REPOSITORY', '')}/actions/runs/{os.getenv('GITHUB_RUN_ID', '')}"
    try:
        download_public_file(f"{prefix}/package.json", directory / "package.json")
        package = json.loads((directory / "package.json").read_text(encoding="utf-8"))
        if package.get("version") != 1 or package.get("execution_id") != execution_id:
            raise AnimeError("执行包版本或执行 ID 不一致")
        content = {key: value for key, value in package.items() if key not in {"execution_id", "thumbnail_key"}}
        expected_id = hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:32]
        if expected_id != execution_id or package["thumbnail_key"] != f"{prefix}/thumbnail.jpg":
            raise AnimeError("执行包内容摘要或封面对象路径不一致")
        validate_copy(package["titles"], package["descriptions"], package["tags"])
        sources = package["sources"]
        if not sources or len({item["aweme_id"] for item in sources}) != len(sources):
            raise AnimeError("执行包来源为空或重复")
        routes = resolve_account_group(package["account_group"], "anime", ["youtube"])
        if len(routes) != 1 or routes[0]["platform_account_id"] != package["channel_id"]:
            raise AnimeError("账号组目标频道发生变化，停止执行并交回 Agent 判断")
        download_public_file(package["thumbnail_key"], directory / "youtube-thumbnail-1.jpg")
        if _file_sha256(directory / "youtube-thumbnail-1.jpg") != package["thumbnail_sha256"]:
            raise AnimeError("封面摘要与执行包不一致")
        _write_json(directory / "youtube-intro-1.json", package["intro"])
        assembled = directory / "manifest.json"
        if exists(f"{prefix}/manifest.json"):
            progress("恢复已拼接成片")
            download_public_file(f"{prefix}/manifest.json", assembled)
            manifest = json.loads(assembled.read_text(encoding="utf-8"))
            for part in manifest["parts"]:
                path = directory / Path(part["video_path"]).name
                download_public_file(f"{prefix}/{path.name}", path)
                if _file_sha256(path) != part["sha256"]:
                    raise AnimeError("恢复成片摘要不一致")
                part["video_path"] = str(path)
            _write_json(assembled, manifest)
        else:
            downloaded = []
            for order, work in enumerate(sources, 1):
                progress(f"下载或恢复来源 {order}/{len(sources)}")
                path = directory / f"source-{order}.mp4"
                metadata_path = path.with_suffix(".json")
                key = f"{prefix}/{metadata_path.name}"
                if exists(key):
                    download_public_file(key, metadata_path)
                    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                    download_public_file(f"{prefix}/{path.name}", path)
                    if _file_sha256(path) != metadata["sha256"]:
                        raise AnimeError("恢复来源摘要不一致")
                else:
                    metadata = download(work["work_url"], path)
                    if str(metadata["video_id"]) != str(work["aweme_id"]):
                        raise AnimeError("下载来源 ID 与执行清单不一致，交回 Agent 判断")
                    metadata["sha256"] = _file_sha256(path)
                probe = _probe(path)
                expected = float(work["duration_seconds"])
                if expected <= 0 or abs(probe["duration"] - expected) > max(5, expected * 0.02):
                    raise AnimeError("来源实际时长与执行清单不符，交回 Agent 判断")
                if not exists(key):
                    upload_public_file(path, f"{prefix}/{path.name}")
                    save_json(metadata_path.name, metadata)
                downloaded.append({**metadata, "path": path, "duration": probe["duration"], "probe": probe,
                                   "order": order, "share_text": work["work_url"]})
            if len(downloaded) == 1:
                progress("单个现成合集直接复用原文件")
                source = downloaded[0]
                path = directory / "part-1.mp4"
                shutil.copy2(source["path"], path)
                manifest = {"original_file": True, "parts": [{"part_index": 1, "part_count": 1,
                            "video_path": str(path), "duration_seconds": source["duration"],
                            "title": source.get("title"), "description": source.get("description"),
                            "topics": source.get("topics") or []}]}
            else:
                manifest = assemble_videos(downloaded, directory, progress=progress)
            for part in manifest["parts"]:
                path = Path(part["video_path"])
                part["sha256"] = _file_sha256(path)
                upload_public_file(path, f"{prefix}/{path.name}")
            manifest["selection_reason"] = package["selection_reason"]
            save_json("manifest.json", manifest)
        first = manifest["parts"][0]
        _write_json(directory / "youtube-thumbnail-1.json", {
            "title": package["titles"][0], "video_sha256": _file_sha256(Path(first["video_path"]))})
        for part in manifest["parts"]:
            name = f"youtube-receipt-{part['part_index']}.json"
            if exists(f"{prefix}/{name}"):
                download_public_file(f"{prefix}/{name}", directory / name)
        result = publish_youtube(str(assembled), package["titles"], package["descriptions"], package["tags"],
                                 package["account_group"], progress,
                                 receipt_saved=lambda path: upload_public_file(path, f"{prefix}/{path.name}", content_type="application/json"))
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
        save_json("result.json", {"execution_id": execution_id, "status": "failed", "run_url": run_url,
                                   "error": exc.message if isinstance(exc, AnimeError) else type(exc).__name__,
                                   "message": "失败进度和已持久化回执保留；不自动替换来源，修复后重跑同一执行 ID"})
        raise


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
