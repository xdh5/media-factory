"""把 GitHub Workflow 成片拉回本地，文件名与 R2 对象名保持一致。"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote, urlparse

from core.tools.cloudflare_data import commit_production_outputs, list_production_outputs
from core.tools.generate_final_video import safe_filename
from core.tools.r2_storage import download_public_file

from ._constants import PROJECT_ROOT
from ._errors import InvalidPublishRequestError


def stored_video_filename(record: dict) -> str:
    """本地/R2 成片文件名：优先使用 r2_url 里的对象名，避免与标题字段二次转换不一致。"""
    r2_url = str(record.get("r2_url") or "").strip()
    if r2_url:
        name = unquote(Path(urlparse(r2_url).path).name).strip()
        if name:
            return name
    title = str(record.get("title") or "").strip()
    if not title:
        raise InvalidPublishRequestError("production_outputs 缺少 r2_url 或 title，无法确定本地文件名")
    return f"{safe_filename(title)}.mp4"


def local_video_path(record: dict) -> Path:
    """本地成片路径：output/{业务线}/{run_id}/{R2对象名}。"""
    business_line = str(record.get("business_line") or "").strip()
    run_id = str(record.get("run_id") or "").strip()
    if not business_line or not run_id:
        raise InvalidPublishRequestError("production_outputs 缺少 business_line 或 run_id")
    return (PROJECT_ROOT / "output" / business_line / run_id / stored_video_filename(record)).resolve()


def r2_object_key(record: dict) -> str:
    return f"runs/{record['business_line']}/{record['run_id']}/{stored_video_filename(record)}"


def materialize_github_workflow_output(record: dict) -> dict:
    """从 R2 下载 github_workflow 成片，本地文件名与 R2 对象名一致，并写入 local_mcp 记录。"""
    business_line = str(record.get("business_line") or "").strip()
    run_id = str(record.get("run_id") or "").strip()
    content_kind = str(record.get("content_kind") or "").strip()
    content_part = int(record.get("content_part") or 1)
    title = str(record.get("title") or "").strip()
    if not business_line or not run_id or not content_kind or not title:
        raise InvalidPublishRequestError("production_outputs 缺少 business_line、run_id、content_kind 或 title")

    destination = local_video_path(record)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.is_file():
        download_public_file(r2_object_key(record), destination)

    payload = {
        "production_id": f"local_mcp:{business_line}:{run_id}:{content_kind}:{content_part}",
        "run_id": run_id,
        "publish_date": str(record.get("publish_date") or "").strip(),
        "business_line": business_line,
        "content_kind": content_kind,
        "content_part": content_part,
        "title": title,
        "hashtags": str(record.get("hashtags") or ""),
        "source": "local_mcp",
        "local_path": str(destination),
    }
    r2_url = str(record.get("r2_url") or "").strip()
    if r2_url:
        payload["r2_url"] = r2_url
    saved = commit_production_outputs([payload])["records"][0]
    return {**saved, "local_path": str(destination)}


def ensure_local_publish_items(
    business_line: str,
    publish_date: str,
    *,
    content_kind: str | None = None,
) -> None:
    """若 local_mcp 缺失或本地文件不存在，则从 R2 拉回 github_workflow 成片。"""
    wanted_kind = str(content_kind or "").strip()
    local_rows = list_production_outputs(
        publish_date=publish_date,
        business_line=business_line,
        source="local_mcp",
    )
    if wanted_kind:
        local_rows = [item for item in local_rows if str(item.get("content_kind") or "") == wanted_kind]

    def _is_valid(row: dict) -> bool:
        expected = local_video_path(row)
        current = Path(str(row.get("local_path") or "")).resolve()
        return current.is_file() and current == expected

    if any(_is_valid(row) for row in local_rows):
        return

    github_rows = list_production_outputs(
        publish_date=publish_date,
        business_line=business_line,
        source="github_workflow",
    )
    if wanted_kind:
        github_rows = [item for item in github_rows if str(item.get("content_kind") or "") == wanted_kind]
    for row in github_rows:
        materialize_github_workflow_output(row)


def enrich_local_publish_item(row: dict) -> dict | None:
    """读取 local_mcp 记录及同目录 short-title / publish-copy。"""
    title = str(row.get("title") or "").strip()
    if not title:
        return None
    expected = local_video_path(row)
    local_path = Path(str(row.get("local_path") or "")).resolve()
    if local_path.is_file() and local_path != expected:
        expected.parent.mkdir(parents=True, exist_ok=True)
        local_path.replace(expected)
        commit_production_outputs([{**row, "source": "local_mcp", "local_path": str(expected)}])
        local_path = expected
    elif expected.is_file():
        local_path = expected
        if str(row.get("local_path") or "").strip() != str(expected):
            commit_production_outputs([{**row, "source": "local_mcp", "local_path": str(expected)}])
    elif local_path.is_file():
        pass
    else:
        return None

    output_dir = local_path.parent
    short_title_path = output_dir / "short-title.txt"
    copy_path = output_dir / "publish-copy.txt"
    return {
        **row,
        "local_path": str(local_path),
        "short_title": short_title_path.read_text(encoding="utf-8").strip() if short_title_path.is_file() else "",
        "publish_copy": copy_path.read_text(encoding="utf-8").strip() if copy_path.is_file() else title,
    }
