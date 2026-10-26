"""把财经成片、封面和生产清单上传为可公开访问的媒体文件。"""

from __future__ import annotations

import json
import mimetypes
from pathlib import Path

from core.tools.media_records import commit_production_outputs
from core.tools.media_files import upload_public_file

from ..config.settings import MCP_ID
from ..errors import WorkflowStepError


def upload_finance_assets_to_r2(manifest_path: str | Path) -> dict:
    """上传财经发布资产，并把公网地址写回本地和远端清单。"""
    path = Path(manifest_path).resolve()
    if not path.is_file():
        raise WorkflowStepError(f"财经生产清单不存在：{path}")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkflowStepError(f"读取财经生产清单失败：{path}。{exc}") from exc
    run_id = str(manifest.get("run_id") or "").strip()
    if not run_id:
        raise WorkflowStepError("财经生产清单缺少 run_id")
    content_part = int(manifest.get("content_part") or 1)
    # part 1 沿用历史 R2 路径；part 2 起加 -partN 后缀，避免同日多条互相覆盖。
    r2_dir = run_id if content_part <= 1 else f"{run_id}-part{content_part}"
    video_path = Path(str(manifest.get("video_path") or "")).resolve()
    cover_path = Path(str(manifest.get("cover_path") or "")).resolve()
    asset_fields = (
        "video_path",
        "cover_path",
        "title_path",
        "short_title_path",
        "publish_copy_path",
        "source_hook_path",
        "attribution_comment_path",
    )
    uploaded_assets: dict[str, dict] = {}
    for field in asset_fields:
        value = str(manifest.get(field) or "").strip()
        if not value:
            continue
        asset_path = Path(value).resolve()
        if not asset_path.is_file():
            raise WorkflowStepError(f"财经生产清单中的资产不存在：{field}={asset_path}")
        content_type = mimetypes.guess_type(asset_path.name)[0] or "application/octet-stream"
        revision = str(manifest.get("video_revision") or "").strip()
        asset_dir = f"{r2_dir}/{revision}" if field == "video_path" and revision else r2_dir
        uploaded_assets[field] = upload_public_file(
            asset_path,
            f"runs/{MCP_ID}/{asset_dir}/{asset_path.name}",
            content_type=content_type,
        )
    video = uploaded_assets["video_path"]
    cover = uploaded_assets["cover_path"]
    manifest["video_url"] = video["url"]
    manifest["video_r2_key"] = video["key"]
    manifest["cover_url"] = cover["url"]
    manifest["cover_r2_key"] = cover["key"]
    manifest["r2_uploaded"] = True
    # 成片记录固定写在 local_mcp 这一条上。GitHub 运行器销毁后本地路径会失效，发布端靠 r2_url 拉回。
    production_outputs = commit_production_outputs([{
        "production_id": f"local_mcp:{MCP_ID}:{run_id}:finance:{content_part}",
        "run_id": run_id,
        "publish_date": str(manifest.get("publish_date") or "").strip(),
        "business_line": MCP_ID,
        "content_kind": "finance",
        "content_part": content_part,
        "title": str(manifest.get("title") or "").strip(),
        "hashtags": " ".join(
            f"#{str(tag).strip().lstrip('#')}"
            for tag in manifest.get("hashtags") or []
            if str(tag).strip().lstrip("#")
        ),
        "source": "local_mcp",
        "local_path": str(video_path),
        "r2_url": video["url"],
        "r2_expires_at": None,
    }])
    manifest["production_outputs"] = production_outputs
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    remote = upload_public_file(
        path,
        f"runs/{MCP_ID}/{r2_dir}/manifest.json",
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
        "uploaded": [*uploaded_assets.values(), remote],
        "production_outputs": production_outputs,
    }
