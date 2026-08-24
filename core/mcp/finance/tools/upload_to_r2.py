"""把财经成片、封面和发布清单上传到 Cloudflare R2。"""

from __future__ import annotations

import json
from pathlib import Path

from core.tools.cloudflare_data import commit_production_outputs
from core.tools.r2_storage import upload_public_file

from .._constants import MCP_ID
from .._errors import WorkflowStepError


def upload_finance_assets_to_r2(manifest_path: str | Path) -> dict:
    """上传财经发布资产，并把公网地址写回本地和远端清单。"""
    path = Path(manifest_path).resolve()
    if not path.is_file():
        raise WorkflowStepError(f"财经发布清单不存在：{path}")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkflowStepError(f"读取财经发布清单失败：{path}。{exc}") from exc
    run_id = str(manifest.get("run_id") or "").strip()
    if not run_id:
        raise WorkflowStepError("财经发布清单缺少 run_id")
    video_path = Path(str(manifest.get("video_path") or "")).resolve()
    cover_path = Path(str(manifest.get("cover_path") or "")).resolve()
    video = upload_public_file(
        video_path,
        f"runs/{MCP_ID}/{run_id}/{video_path.name}",
        content_type="video/mp4",
    )
    cover = upload_public_file(
        cover_path,
        f"runs/{MCP_ID}/{run_id}/{cover_path.name}",
        content_type="image/png" if cover_path.suffix.lower() == ".png" else "image/jpeg",
    )
    manifest["video_url"] = video["url"]
    manifest["video_r2_key"] = video["key"]
    manifest["cover_url"] = cover["url"]
    manifest["cover_r2_key"] = cover["key"]
    manifest["r2_uploaded"] = True
    source = str(manifest.get("production_source") or "local_mcp").strip()
    production_outputs = commit_production_outputs([{
        "production_id": f"{source}:{MCP_ID}:{run_id}:finance:1",
        "run_id": run_id,
        "publish_date": str(manifest.get("publish_date") or "").strip(),
        "business_line": MCP_ID,
        "content_kind": "finance",
        "content_part": 1,
        "title": str(manifest.get("title") or "").strip(),
        "source": source,
        "local_path": str(video_path) if source == "local_mcp" else None,
        "r2_url": video["url"],
    }])
    manifest["production_outputs"] = production_outputs
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    remote = upload_public_file(
        path,
        f"runs/{MCP_ID}/{run_id}/manifest.json",
        content_type="application/json",
    )
    manifest["manifest_url"] = remote["url"]
    manifest["manifest_r2_key"] = remote["key"]
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    remote = upload_public_file(path, remote["key"], content_type="application/json")
    return {
        "manifest_path": str(path),
        "manifest_url": remote["url"],
        "video_url": video["url"],
        "cover_url": cover["url"],
        "uploaded": [video, cover, remote],
        "production_outputs": production_outputs,
    }
