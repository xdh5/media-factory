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

from download_video._extractor import parse_share_text

from .._constants import OUTPUT_ROOT, PROJECT_ROOT, SEGMENTATION_DURATION, SEGMENTATION_EPISODES
from .._errors import AnimeError
from .compile import _write_json, normalize_share_texts, part_ranges, split_ranges
from .discover import load_discovery
from .preview import extract_remote_preview, probe_remote_duration
from .youtube import _file_sha256, _part_title, _require_host_thumbnail, load_manifest, transcribe_intros

WORKFLOW = "publish-anime-youtube.yml"


def planned_part_count(sources: list[dict], segmentation: str) -> int:
    """按冻结来源时长给出预计段数；长视频直发按时间线均分。"""
    durations = [float(item["duration_seconds"]) for item in sources]
    if segmentation == SEGMENTATION_DURATION:
        return len(split_ranges(sum(durations)))
    return len(part_ranges(durations))


def validate_copy(titles: list[str], descriptions: list[str], tags: list[str],
                  *, require_completed: bool = True) -> None:
    """执行包只接受一份共用发布文案。"""
    max_title_length = 80 if require_completed else 100
    if len(titles) != 1 or not titles[0].strip() or len(titles[0]) > max_title_length:
        raise AnimeError(f"请提供一个 1 到 {max_title_length} 字符的共用标题")
    if len(descriptions) != 1 or not descriptions[0].strip() or len(descriptions[0]) > 5000:
        raise AnimeError("请提供一个 1 到 5000 字符的共用描述")
    if not all(isinstance(tag, str) and tag.strip() and not tag.startswith("#") for tag in tags):
        raise AnimeError("标签必须为不带 # 的非空文字")
    if len(set(tags)) != len(tags) or sum(len(tag) + 3 for tag in tags) > 420:
        raise AnimeError("标签须去重，总预算不得超过 420 字符")
    if require_completed and "已完结" not in titles[0]:
        raise AnimeError("YouTube 标题关键词必须包含“已完结”")
    if require_completed and "#已完结" not in descriptions[0]:
        raise AnimeError("YouTube 描述底部 hashtag 必须包含 #已完结")
    if require_completed and "已完结" not in {tag.strip().lstrip("#") for tag in tags}:
        raise AnimeError("YouTube 搜索标签必须包含“已完结”")


def prepare_execution(discovery_path: str, work_ids: list[str], selection_reason: str, progress) -> dict:
    """冻结选片顺序，只截取第一来源开头一分钟并转写。"""
    directory, discovery = load_discovery(discovery_path)
    works = {item["aweme_id"]: item for item in discovery["works"]}
    if not work_ids or len(set(work_ids)) != len(work_ids) or any(item not in works for item in work_ids):
        raise AnimeError("请选择发现记录中的不重复作品 ID，按最终播放顺序传入")
    if not selection_reason.strip():
        raise AnimeError("必须说明匹配、顺序、合集覆盖、去重、缺集和完结状态")
    if "已完结" not in selection_reason:
        raise AnimeError("发布执行清单必须明确说明作品已完结；仍在更新或证据不足时不能进入发布流程")
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
            "source_count": len(selected),
            "next_step": "生成含已完结的一套文案，再以此 manifest_path 按预计分段数准备并保存对应封面"}


def prepare_split_execution(share_texts: list[str], series_name: str, selection_reason: str, progress) -> dict:
    """冻结用户直发长视频的来源顺序，只远程读取开头一分钟，由 Action 下载后按时间线拆分。"""
    texts = normalize_share_texts(share_texts)
    name = series_name.strip()
    if not name:
        raise AnimeError("必须提供作品名，用作 YouTube 播放列表和文案依据")
    if not selection_reason.strip():
        raise AnimeError("必须说明来源顺序、拆分依据和完结状态")
    if "已完结" not in selection_reason:
        raise AnimeError("发布执行清单必须明确说明作品已完结")
    output = OUTPUT_ROOT / f"split-{time.time_ns()}"
    output.mkdir(parents=True)
    sources = []
    for index, text in enumerate(texts, 1):
        progress(f"正在解析第 {index}/{len(texts)} 条来源，不下载整部视频")
        resolved = parse_share_text(text)
        if not resolved.video_id:
            raise AnimeError(f"第 {index} 条链接没有解析出视频 ID")
        sources.append({
            "order": index,
            "aweme_id": resolved.video_id,
            "work_url": text,
            "title": resolved.title or "",
            "description": resolved.description or "",
            "topics": list(resolved.topics),
            "platform": resolved.platform_name,
            "duration_seconds": round(probe_remote_duration(resolved), 3),
        })
    _write_json(output / "selection.json", {
        "series_name": name, "profile_url": "", "selection_reason": selection_reason,
        "segmentation": SEGMENTATION_DURATION, "sources": sources,
    })
    progress("只读取第一来源开头一分钟，完整长视频留给 Action 下载")
    preview = output / "preview.mp4"
    probe = extract_remote_preview(sources[0], preview)
    manifest = output / "manifest.json"
    _write_json(manifest, {"preview_only": True, "parts": [{
        "part_index": 1, "video_path": str(preview), "duration_seconds": probe["duration"],
        "title": sources[0].get("title") or "",
    }]})
    total_seconds = sum(float(item["duration_seconds"]) for item in sources)
    ranges = split_ranges(total_seconds)
    result = transcribe_intros(str(manifest), progress)
    return {**result, "preview_only": True, "selection_path": str(output / "selection.json"),
            "series_name": name, "source_count": len(sources),
            "split_plan": {"total_seconds": round(total_seconds, 3), "part_count": len(ranges),
                           "parts": [{"part_index": index, "start_seconds": round(start, 3),
                                      "end_seconds": round(end, 3),
                                      "duration_seconds": round(end - start, 3)}
                                     for index, (start, end) in enumerate(ranges, 1)]},
            "sources": [{key: item[key] for key in ("order", "title", "description", "topics",
                                                    "duration_seconds", "platform")} for item in sources],
            "next_step": "按拆分计划的段数准备封面，写含已完结的一套文案，再调用 anime_dispatch_github_execution"}


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
        raise AnimeError("请使用 anime_start_prepare_execution 或 anime_start_prepare_split_execution 返回的预览清单")
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
    preview_digest = _file_sha256(Path(parts[0]["video_path"]))
    thumbnails = []
    for index in range(1, expected_part_count + 1):
        thumbnail = _require_host_thumbnail(
            directory, index, _part_title(titles[0], index, expected_part_count), preview_digest)
        thumbnails.append({"index": index, "sha256": _file_sha256(thumbnail)})
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
    _write_json(package_file, package)
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
