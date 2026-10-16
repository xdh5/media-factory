"""下载失败时合并连续完成的来源，保存可恢复的拼接检查点。"""

from pathlib import Path
import json

from core.mcp.anime._errors import AnimeError
from core.mcp.anime.services.compile import _probe, _write_json, assemble_videos
from core.mcp.anime.services.youtube import _file_sha256


def restore_checkpoint(directory, prefix, execution_id, sources, exists, fetch, progress):
    """恢复已验证来源前缀；后续仅从下一条来源开始下载。"""
    key = f"{prefix}/download-checkpoint.json"
    if not exists(key):
        return [], 0
    manifest_path = directory / "download-checkpoint.json"
    fetch(key, manifest_path)
    checkpoint = json.loads(manifest_path.read_text(encoding="utf-8"))
    count = checkpoint.get("completed_source_count")
    if (checkpoint.get("version") != 1 or checkpoint.get("execution_id") != execution_id
            or type(count) is not int or not 1 <= count <= len(sources)
            or checkpoint.get("source_ids") != [str(item["aweme_id"]) for item in sources[:count]]):
        raise AnimeError("下载检查点与执行清单不一致，停止恢复")
    parts = checkpoint.get("parts")
    if not isinstance(parts, list) or not parts:
        raise AnimeError("下载检查点缺少视频分段")
    recovered = []
    total_duration = 0.0
    for index, part in enumerate(parts, 1):
        name = part["name"]
        if Path(name).name != name or not name.startswith("checkpoint-") or not name.endswith(".mp4"):
            raise AnimeError("下载检查点文件名无效")
        path = directory / name
        progress(f"恢复下载检查点 {index}/{len(parts)}，已完成来源 {count}/{len(sources)}")
        fetch(f"{prefix}/{name}", path)
        if _file_sha256(path) != part["sha256"]:
            raise AnimeError("下载检查点视频摘要不一致")
        probe = _probe(path)
        if abs(probe["duration"] - float(part["duration_seconds"])) > 1:
            raise AnimeError("下载检查点视频时长不一致")
        total_duration += probe["duration"]
        recovered.append({"path": path, "probe": probe, "duration": probe["duration"],
                          "order": index, "title": "已验证来源检查点", "description": "", "topics": []})
    expected = sum(float(item["duration_seconds"]) for item in sources[:count])
    if abs(total_duration - expected) > max(5, expected * 0.02):
        raise AnimeError("下载检查点总时长与已完成来源不符")
    return recovered, count


def persist_checkpoint(directory, prefix, execution_id, sources, downloaded, count, upload, progress):
    """只在失败时上传已完成前缀，视频全部上传成功后才提交检查点索引。"""
    folder = directory / f"checkpoint-{count}"
    progress(f"失败保护：拼接已完成的 {count} 个来源，保存下载检查点")
    manifest = assemble_videos(downloaded, folder, progress=progress)
    parts = []
    for index, part in enumerate(manifest["parts"], 1):
        path = Path(part["video_path"])
        digest = _file_sha256(path)
        name = f"checkpoint-{count}-{index}-{digest[:16]}.mp4"
        upload(path, f"{prefix}/{name}")
        parts.append({"name": name, "sha256": digest, "duration_seconds": part["duration_seconds"]})
    checkpoint = {"version": 1, "execution_id": execution_id, "completed_source_count": count,
                  "next_source_order": count + 1,
                  "source_ids": [str(item["aweme_id"]) for item in sources[:count]], "parts": parts}
    path = directory / "download-checkpoint.json"
    _write_json(path, checkpoint)
    upload(path, f"{prefix}/download-checkpoint.json", content_type="application/json")
    return checkpoint
