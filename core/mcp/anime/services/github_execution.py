"""宿主准备执行清单和封面，通过 GitHub Actions 执行耗时生产发布。"""

from __future__ import annotations

import hashlib
import configparser
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import requests


from .._constants import PROJECT_ROOT, SEGMENTATION_DURATION, SEGMENTATION_EPISODES
from .._errors import AnimeError
from .media_artifacts import file_sha256, write_json, load_manifest
from .segmentation import planned_part_count
from .youtube_assets import require_host_thumbnail
from .youtube_metadata import part_title, validate_copy

WORKFLOW = "publish-anime-youtube.yml"


def _repository() -> str:
    if shutil.which("git"):
        remote = subprocess.run(["git", "remote", "get-url", "origin"], cwd=PROJECT_ROOT,
                                check=True, capture_output=True, text=True).stdout.strip()
    else:
        configuration = configparser.ConfigParser(interpolation=None)
        configuration.read(PROJECT_ROOT / ".git" / "config", encoding="utf-8")
        remote = configuration.get('remote "origin"', "url", fallback="")
    match = re.fullmatch(r"(?:git@github\.com:|https://github\.com/)([^/]+/[^/]+?)(?:\.git)?", remote)
    if not match:
        raise AnimeError("origin 必须是可识别的 GitHub 仓库")
    return match[1]


def _github_request(method: str, endpoint: str, payload: dict | None = None) -> dict:
    """优先使用部署令牌；本机可复用 gh 已有登录，不记录凭据。"""
    token = os.getenv("ANIME_GITHUB_TOKEN") or os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN")
    if token:
        response = requests.request(method, f"https://api.github.com/{endpoint}", json=payload,
                                    headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                                             "X-GitHub-Api-Version": "2022-11-28"}, timeout=30)
        if not response.ok:
            raise AnimeError(f"GitHub 请求失败（HTTP {response.status_code}），请检查仓库 Actions 权限")
        return response.json() if response.content else {}
    if not shutil.which("gh"):
        raise AnimeError("缺少 GitHub 授权：设置 ANIME_GITHUB_TOKEN，或在本机 gh 登录后调用")
    command = ["gh", "api", "--method", method, endpoint]
    if payload is not None:
        command.extend(["--input", "-"])
    result = subprocess.run(command, input=json.dumps(payload) if payload is not None else None,
                            capture_output=True, text=True, encoding="utf-8", timeout=60)
    if result.returncode:
        raise AnimeError("GitHub 请求失败，请检查 gh 登录及目标仓库 Actions 权限")
    return json.loads(result.stdout) if result.stdout.strip() else {}


def dispatch_execution(manifest_path: str, titles: list[str], descriptions: list[str], tags: list[str],
                       account_group: str = "") -> dict:
    """上传不可变执行包并启动 Action；只在用户授权发布后调用。"""
    from core.tools.media_files import upload_public_file
    from core.tools.publish_media.accounts import resolve_account_group

    validate_copy(titles, descriptions, tags)
    directory, parts = load_manifest(manifest_path)
    if not json.loads((directory / "manifest.json").read_text(encoding="utf-8")).get("preview_only"):
        raise AnimeError("请使用 anime_prepare_publication 或 anime_prepare_publication 返回的预览清单")
    selection = json.loads((directory / "selection.json").read_text(encoding="utf-8"))
    intro = directory / "youtube-intro-1.json"
    if not intro.is_file():
        raise AnimeError("请先完成第一来源开头转写")
    from .accounts import production_config
    account_group = production_config(account_group)["account_group"]
    routes = resolve_account_group(account_group, "anime", ["youtube"])
    if len(routes) != 1:
        raise AnimeError("目标账号组必须对应一个 YouTube 频道")
    segmentation = selection.get("segmentation") or SEGMENTATION_EPISODES
    expected_part_count = planned_part_count(selection["sources"], segmentation)
    preview_digest = file_sha256(Path(parts[0]["video_path"]))
    thumbnails = []
    for index in range(1, expected_part_count + 1):
        thumbnail = require_host_thumbnail(
            directory, index, part_title(titles[0], index, expected_part_count), preview_digest)
        thumbnails.append({"index": index, "sha256": file_sha256(thumbnail)})
    package = {"version": 3 if segmentation == SEGMENTATION_DURATION else 2, "segmentation": segmentation,
               **selection, "titles": titles, "descriptions": descriptions, "tags": tags,
               "account_group": account_group, "channel_id": routes[0]["platform_account_id"],
               "intro": json.loads(intro.read_text(encoding="utf-8")), "thumbnails": thumbnails}
    execution_id = hashlib.sha256(json.dumps(package, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:32]
    prefix = f"runs/anime/executions/{execution_id}"
    package.update({"execution_id": execution_id})
    for item in package["thumbnails"]:
        item["key"] = f"{prefix}/thumbnail-{item['index']}.jpg"
    package_file = directory / "execution-package.json"
    write_json(package_file, package)
    repository = _repository()
    _github_request("GET", f"repos/{repository}/actions/workflows/{WORKFLOW}")
    for item in package["thumbnails"]:
        upload_public_file(
            directory / f"youtube-thumbnail-{item['index']}.jpg",
            item["key"], content_type="image/jpeg")
    key = f"{prefix}/package.json"
    upload_public_file(package_file, key, content_type="application/json")
    _github_request("POST", f"repos/{repository}/actions/workflows/{WORKFLOW}/dispatches",
                    {"ref": "main", "inputs": {"execution_id": execution_id}})
    result = {"status": "dispatched", "execution_id": execution_id, "package_key": key,
              "workflow_url": f"https://github.com/{repository}/actions/workflows/{WORKFLOW}",
              "result_key": f"{prefix}/result.json", "message": "Action 已启动，尚未代表发布成功；可按执行 ID 查看运行和结果"}
    write_json(directory / "github-dispatch.json", result)
    return result


def read_execution_result(execution_id: str) -> dict:
    """读取 Action 保存的进度或最终结果，不在宿主等待耗时任务。"""
    from core.tools.media_files.storage import _client, _settings

    if not re.fullmatch(r"[a-f0-9]{32}", execution_id):
        raise AnimeError("执行 ID 格式无效")
    settings = _settings()
    client = _client(settings["R2_ACCOUNT_ID"], settings["R2_ACCESS_KEY_ID"], settings["R2_SECRET_ACCESS_KEY"])
    try:
        response = client.get_object(Bucket=settings["R2_BUCKET"], Key=f"runs/anime/executions/{execution_id}/result.json")
    except client.exceptions.ClientError as exc:
        if str(exc.response["Error"]["Code"]) in {"NoSuchKey", "404"}:
            return {"execution_id": execution_id, "status": "pending", "message": "尚无运行结果，请查看 GitHub Actions"}
        raise
    return json.loads(response["Body"].read())
