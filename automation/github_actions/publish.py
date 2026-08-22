"""阿里云发布机入口：从 R2 清单下载成片并执行平台发布。"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

from core.mcp.language_learning.tools.publish_vocabulary_videos import publish_vocabulary_videos
from core.tools.topic_dedup import commit as commit_topic


DEFAULT_MATRIXMEDIA_PLATFORMS = ("dy", "ks", "blbl", "bjh", "tt", "sph")


def _write_summary(title: str, rows: list[tuple[str, str]]) -> None:
    summary_path = os.getenv("GITHUB_STEP_SUMMARY", "").strip()
    if not summary_path:
        return
    lines = [f"## {title}", "", *(f"- {label}：{value}" for label, value in rows)]
    with Path(summary_path).open("a", encoding="utf-8") as stream:
        stream.write("\n".join(lines) + "\n")


def _require_aliyun_runner() -> None:
    if os.getenv("MEDIA_FACTORY_PUBLISH_HOST", "").strip().casefold() != "aliyun":
        raise RuntimeError("发布只能在阿里云自托管 Runner 执行，当前环境未设置 MEDIA_FACTORY_PUBLISH_HOST=aliyun")
    labels = {item.strip().casefold() for item in os.getenv("RUNNER_LABELS", "").split(",") if item.strip()}
    if labels and not {"publisher", "matrixmedia"}.issubset(labels):
        raise RuntimeError("当前 Runner 缺少 publisher、matrixmedia 标签，拒绝执行发布")


def _read_json_url(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "media-factory-aliyun-publisher/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(f"读取 R2 发布清单失败：{url}。{exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"R2 发布清单不是 JSON 对象：{url}")
    return payload


def _path_key(value: str) -> str:
    return str(value or "").strip().replace("\\", "/").casefold()


def _uploaded_url(remote_manifest: dict, source_path: str) -> str:
    expected = _path_key(source_path)
    expected_name = Path(source_path).name.casefold()
    same_name = []
    for row in remote_manifest.get("r2_files") or []:
        url = str(row.get("url") or "").strip()
        if not url:
            continue
        if _path_key(row.get("source_path")) == expected:
            return url
        if str(row.get("source_name") or "").strip().casefold() == expected_name:
            same_name.append(url)
    unique = list(dict.fromkeys(same_name))
    if len(unique) == 1:
        return unique[0]
    raise RuntimeError(f"R2 清单中找不到唯一成片地址：{source_path}")


def _download_video(url: str, target_dir: Path, index: int) -> Path:
    name = Path(urllib.parse.urlparse(url).path).name or f"video-{index}.mp4"
    target = target_dir / f"{index:03d}-{name}"
    request = urllib.request.Request(url, headers={"User-Agent": "media-factory-aliyun-publisher/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=120) as response, target.open("wb") as stream:
            while chunk := response.read(1024 * 1024):
                stream.write(chunk)
    except Exception as exc:
        raise RuntimeError(f"从 R2 下载成片失败：{url}。{exc}") from exc
    if not target.is_file() or target.stat().st_size == 0:
        raise RuntimeError(f"从 R2 下载的成片为空：{url}")
    return target


def _hashtags(tags: list[str]) -> str:
    return " ".join(f"#{str(tag).strip().lstrip('#')}" for tag in tags if str(tag).strip())


def _publish_matrixmedia_item(item: dict, target_dir: Path, start_index: int = 0) -> list[dict]:
    executable = os.getenv("MATRIXMEDIA_BIN", "/usr/local/bin/matrixmedia").strip()
    account_group = str(item.get("account_group") or "").strip()
    platforms = [str(value).strip() for value in item.get("platforms") or [] if str(value).strip()]
    if not account_group:
        raise RuntimeError("阿里云发布清单缺少 MatrixMedia 账号组")
    if not platforms:
        raise RuntimeError("阿里云发布清单缺少 MatrixMedia 平台列表")
    results = []
    index = start_index
    for video in item.get("videos") or []:
        index += 1
        video_url = str(video.get("video_url") or "").strip()
        if not video_url:
            raise RuntimeError("阿里云发布清单中的 MatrixMedia 视频缺少 R2 video_url")
        local_video = _download_video(video_url, target_dir, index)
        title = str(video.get("title") or item.get("title") or "").strip()
        short_title = str(item.get("short_title") or title).strip()
        tags = _hashtags(list(item.get("tags") or []))
        for platform in platforms:
            command = [
                "xvfb-run", "-a", "env", "LIBGL_ALWAYS_SOFTWARE=1", "MATRIXMEDIA_DISABLE_TELEMETRY=1",
                executable,
                "--no-sandbox",
                "--disable-gpu",
                "--disable-software-rasterizer",
                "--disable-dev-shm-usage",
                "cli", "publish", "-p", platform, "--phone", account_group,
                "-f", str(local_video), "-t", title, "--bt2", short_title,
            ]
            if tags:
                command.extend(["--tags", tags])
            environment = dict(os.environ)
            environment.pop("ELECTRON_RUN_AS_NODE", None)
            environment.pop("DBUS_SESSION_BUS_ADDRESS", None)
            completed = subprocess.run(
                command,
                cwd="/opt/matrixmedia" if Path("/opt/matrixmedia").is_dir() else None,
                env=environment,
                capture_output=True,
                text=True,
                timeout=2700,
                check=False,
            )
            result = {
                "channel": "matrixmedia",
                "platform": platform,
                "account_group": account_group,
                "video": str(local_video),
                "success": completed.returncode == 0,
                "exit_code": completed.returncode,
                "stdout": completed.stdout[-4000:],
                "stderr": completed.stderr[-4000:],
            }
            results.append(result)
            if completed.returncode != 0:
                raise RuntimeError(
                    f"MatrixMedia 发布失败：平台={platform}，账号组={account_group}，"
                    f"退出码={completed.returncode}，错误={completed.stderr[-1000:]}"
                )
    return results


def _language_items(remote_manifest: dict, target_dir: Path) -> tuple[list[dict], Path]:
    publish_manifest = remote_manifest.get("publish_manifest")
    if not isinstance(publish_manifest, dict) or not publish_manifest.get("items"):
        raise RuntimeError("语言学习 R2 清单缺少 publish_manifest.items")
    items = []
    index = 0
    for source_item in publish_manifest["items"]:
        item = dict(source_item)
        videos = []
        for source_video in item.get("videos") or []:
            index += 1
            video = dict(source_video)
            video_url = str(video.get("video_url") or "").strip()
            if not video_url:
                video_url = _uploaded_url(remote_manifest, str(video.get("output_path") or ""))
            video["video_url"] = video_url
            video["output_path"] = str(_download_video(video_url, target_dir, index))
            videos.append(video)
        item["videos"] = videos
        items.append(item)
    local_manifest = {**publish_manifest, "items": items}
    local_path = target_dir / "publish-manifest.json"
    local_path.write_text(json.dumps(local_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return items, local_path


def _publish_language(remote_manifest: dict, target_dir: Path) -> dict:
    items, local_manifest_path = _language_items(remote_manifest, target_dir)
    chinese_items = [item for item in items if item.get("learning_mode") == "en-zh"]
    matrixmedia_items = [item for item in items if item.get("channel") == "matrixmedia"]
    official_result = None
    if chinese_items:
        official_result = publish_vocabulary_videos(local_manifest_path, True)
    matrixmedia_results = []
    for item in matrixmedia_items:
        matrixmedia_results.extend(_publish_matrixmedia_item(item, target_dir, len(matrixmedia_results)))
    return {"official": official_result, "matrixmedia": matrixmedia_results}


def _publish_finance(remote_manifest: dict, target_dir: Path) -> dict:
    video_url = _uploaded_url(remote_manifest, str(remote_manifest.get("video_path") or ""))
    item = {
        "account_group": str(remote_manifest.get("matrixmedia_account_group") or "心灵鸡汤"),
        "platforms": list(remote_manifest.get("publish_platforms") or DEFAULT_MATRIXMEDIA_PLATFORMS),
        "title": str(remote_manifest.get("title") or ""),
        "short_title": str(remote_manifest.get("publish_bt2") or remote_manifest.get("short_title") or ""),
        "tags": list(remote_manifest.get("hashtags") or []),
        "videos": [{
            "title": str(remote_manifest.get("title") or ""),
            "video_url": video_url,
        }],
    }
    return {"matrixmedia": _publish_matrixmedia_item(item, target_dir)}


def _commit_database(remote_manifest: dict, line: str) -> dict:
    """用户点击发布后，先把本次正式话题及可选词表幂等写入 D1。"""
    payload = remote_manifest.get("database_commit")
    if not isinstance(payload, dict):
        publish_manifest = remote_manifest.get("publish_manifest")
        payload = publish_manifest.get("database_commit") if isinstance(publish_manifest, dict) else None
    if not isinstance(payload, dict):
        return {
            "legacy_manifest": True,
            "already_committed": True,
            "message": "旧版清单在生产阶段已经入库，本次兼容跳过重复写入",
        }
    workflow = str(payload.get("workflow") or "").strip()
    if workflow != line:
        raise RuntimeError(f"R2 清单入库生产线不匹配：预期 {line}，实际 {workflow or '空'}")
    return commit_topic(
        workflow,
        str(payload.get("topic") or ""),
        str(payload.get("publication_id") or ""),
        days=int(payload.get("days") or 30),
        entries=list(payload.get("entries") or []),
        history_days=int(payload.get("history_days") or 100),
        minimum_new_words=int(payload.get("minimum_new_words") or 5),
    )


def run(manifest_url: str) -> dict:
    """从 R2 远程清单识别生产线，并统一在阿里云完成发布。"""
    _require_aliyun_runner()
    url = str(manifest_url or "").strip()
    if not url.startswith(("https://", "http://")):
        raise RuntimeError("manifest_url 必须是 R2 的 HTTP(S) 清单地址")
    remote_manifest = _read_json_url(url)
    runner_temp = Path(os.getenv("RUNNER_TEMP", tempfile.gettempdir())).resolve()
    target_dir = Path(tempfile.mkdtemp(prefix="media-factory-publish-", dir=runner_temp))
    if remote_manifest.get("publish_manifest"):
        line = "language_learning"
    elif remote_manifest.get("line") == "finance" or remote_manifest.get("matrixmedia_account_group"):
        line = "finance"
    else:
        raise RuntimeError("无法识别 R2 清单所属生产线")
    database = _commit_database(remote_manifest, line)
    if line == "language_learning":
        result = _publish_language(remote_manifest, target_dir)
    else:
        result = _publish_finance(remote_manifest, target_dir)
    _write_summary(
        "阿里云发布完成",
        [("生产线", line), ("R2 清单", url), ("发布机", os.getenv("RUNNER_NAME", "未知"))],
    )
    return {
        "line": line,
        "manifest_url": url,
        "database": database,
        "result": result,
        "work_dir": str(target_dir),
    }
