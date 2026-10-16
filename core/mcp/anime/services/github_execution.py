"""宿主准备执行清单和封面，通过 GitHub Actions 执行耗时生产发布。"""

from __future__ import annotations

import hashlib
import configparser
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import requests

from .._constants import PROJECT_ROOT
from .._errors import AnimeError
from .compile import _write_json
from .discover import load_discovery
from .preview import extract_remote_preview
from .youtube import _file_sha256, _require_host_thumbnail, load_manifest, transcribe_intros

WORKFLOW = "publish-anime-youtube.yml"


def validate_copy(titles: list[str], descriptions: list[str], tags: list[str]) -> None:
    """执行包只接受一份共用发布文案。"""
    if len(titles) != 1 or not titles[0].strip() or len(titles[0]) > 100:
        raise AnimeError("请提供一个 1 到 100 字符的共用标题")
    if len(descriptions) != 1 or not descriptions[0].strip() or len(descriptions[0]) > 5000:
        raise AnimeError("请提供一个 1 到 5000 字符的共用描述")
    if not all(isinstance(tag, str) and tag.strip() and not tag.startswith("#") for tag in tags):
        raise AnimeError("标签必须为不带 # 的非空文字")
    if len(set(tags)) != len(tags) or sum(len(tag) + 3 for tag in tags) > 420:
        raise AnimeError("标签须去重，总预算不得超过 420 字符")


def prepare_execution(discovery_path: str, work_ids: list[str], selection_reason: str, progress) -> dict:
    """冻结选片顺序，只截取第一来源开头一分钟并转写。"""
    directory, discovery = load_discovery(discovery_path)
    works = {item["aweme_id"]: item for item in discovery["works"]}
    if not work_ids or len(set(work_ids)) != len(work_ids) or any(item not in works for item in work_ids):
        raise AnimeError("请选择发现记录中的不重复作品 ID，按最终播放顺序传入")
    if not selection_reason.strip():
        raise AnimeError("必须说明匹配、顺序、合集覆盖、去重、缺集和完结状态")
    selected = [works[item] for item in work_ids]
    if any(float(item.get("duration_seconds") or 0) <= 0 for item in selected):
        raise AnimeError("来源缺少有效时长，无法冻结执行清单")
    output = directory / f"execution-{time.time_ns()}"
    output.mkdir()
    _write_json(output / "selection.json", {
        "series_name": discovery["series_name"], "profile_url": discovery["profile_url"],
        "selection_reason": selection_reason, "sources": selected,
    })
    progress("只读取第一来源开头一分钟，其他完整来源留给 Action 下载")
    preview = output / "preview.mp4"
    probe = extract_remote_preview(selected[0], preview)
    manifest = output / "manifest.json"
    _write_json(manifest, {"preview_only": True, "parts": [{
        "part_index": 1, "video_path": str(preview), "duration_seconds": probe["duration"],
        "title": selected[0].get("title") or "",
    }]})
    result = transcribe_intros(str(manifest), progress)
    return {**result, "preview_only": True, "selection_path": str(output / "selection.json"),
            "source_count": len(selected), "next_step": "生成一套文案，再以此 manifest_path 准备并保存一张共用封面"}


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
        raise AnimeError("请使用 anime_start_prepare_execution 返回的预览清单")
    selection = json.loads((directory / "selection.json").read_text(encoding="utf-8"))
    intro = directory / "youtube-intro-1.json"
    if not intro.is_file():
        raise AnimeError("请先完成第一来源开头转写")
    from .accounts import production_config
    account_group = production_config(account_group)["account_group"]
    routes = resolve_account_group(account_group, "anime", ["youtube"])
    if len(routes) != 1:
        raise AnimeError("目标账号组必须对应一个 YouTube 频道")
    thumbnail = _require_host_thumbnail(directory, 1, titles[0], _file_sha256(Path(parts[0]["video_path"])))
    package = {"version": 1, **selection, "titles": titles, "descriptions": descriptions, "tags": tags,
               "account_group": account_group, "channel_id": routes[0]["platform_account_id"],
               "intro": json.loads(intro.read_text(encoding="utf-8")), "thumbnail_sha256": _file_sha256(thumbnail)}
    execution_id = hashlib.sha256(json.dumps(package, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:32]
    prefix = f"runs/anime/executions/{execution_id}"
    package.update({"execution_id": execution_id, "thumbnail_key": f"{prefix}/thumbnail.jpg"})
    package_file = directory / "execution-package.json"
    _write_json(package_file, package)
    repository = _repository()
    _github_request("GET", f"repos/{repository}/actions/workflows/{WORKFLOW}")
    upload_public_file(thumbnail, package["thumbnail_key"], content_type="image/jpeg")
    key = f"{prefix}/package.json"
    upload_public_file(package_file, key, content_type="application/json")
    _github_request("POST", f"repos/{repository}/actions/workflows/{WORKFLOW}/dispatches",
                    {"ref": "main", "inputs": {"execution_id": execution_id}})
    result = {"status": "dispatched", "execution_id": execution_id, "package_key": key,
              "workflow_url": f"https://github.com/{repository}/actions/workflows/{WORKFLOW}",
              "result_key": f"{prefix}/result.json", "message": "Action 已启动，尚未代表发布成功；可按执行 ID 查看运行和结果"}
    _write_json(directory / "github-dispatch.json", result)
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
