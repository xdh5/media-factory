"""两个视频工作流共用的千问、R2 与日志方法。"""

from __future__ import annotations

import json
import mimetypes
import os
from pathlib import Path

import boto3

from ._dates import resolve_publish_date
from core.tools.qwen_text import generate_text
from core.tools.qwen_vision import analyze_image
from core.tools.r2_storage import upload_public_file
from core.tools.cloudflare_data import list_production_outputs, list_publication_records


PROJECT_ROOT = Path(__file__).resolve().parents[2]
LANGUAGE_PUBLISH_TARGETS = ("youtube", "tiktok", "instagram", "facebook")


def daily_production_preflight(
    business_line: str,
    publish_date: str = "",
    default_days_ahead: int = 0,
) -> dict:
    """按计划发布日期查询成片和发布记录，决定是否生产及需要补发的平台。"""
    publish_date = resolve_publish_date(publish_date, default_days_ahead)
    outputs = list_production_outputs(
        publish_date=publish_date,
        business_line=business_line,
    )
    publications = list_publication_records(
        business_line=business_line,
        publish_date=publish_date,
    )
    published_platforms = {
        str(item.get("platform") or "").strip()
        for item in publications
        if str(item.get("platform") or "").strip()
    }
    pending_targets = [
        target for target in LANGUAGE_PUBLISH_TARGETS
        if target not in published_platforms
    ] if business_line == "language_learning" else []
    github_outputs = [
        item for item in outputs
        if item.get("source") == "github_workflow" and item.get("r2_url")
    ]
    existing_run_id = str(github_outputs[0].get("run_id") or "") if github_outputs else ""
    should_generate = not outputs and not publications
    should_resume_publish = (
        business_line == "language_learning"
        and not should_generate
        and bool(existing_run_id)
        and bool(pending_targets)
    )
    return {
        "publish_date": publish_date,
        "business_line": business_line,
        "should_generate": should_generate,
        "should_resume_publish": should_resume_publish,
        "existing_run_id": existing_run_id,
        "pending_targets": pending_targets,
        "output_count": len(outputs),
        "publication_count": len(publications),
        "published_platforms": sorted(published_platforms),
        "skip_reason": (
            "该计划发布日期没有可复用的 GitHub R2 成片"
            if should_generate
            else f"该计划发布日期已有 {len(outputs)} 条成片记录、{len(publications)} 条发布记录"
        ),
    }


def restore_finance_image_library(library_line: str) -> Path:
    """恢复指定财经图库；本地已有文件时跳过 R2。"""
    from core.tools.generate_image._restore_library import restore_image_library

    library = restore_image_library(library_line)
    print(f"财经图库已就绪：line={library_line} path={library}", flush=True)
    return library


def qwen(system_prompt: str, user_prompt: str, *, json_output: bool = False, max_tokens: int = 8192) -> dict:
    result = generate_text(
        system_prompt,
        user_prompt,
        temperature=0.7,
        max_tokens=max_tokens,
        json_output=json_output,
    )
    print(
        f"千问文本完成：model={result['model']}，"
        f"prompt_tokens={result['usage']['prompt_tokens']}，"
        f"completion_tokens={result['usage']['completion_tokens']}"
    )
    return result


def qwen_vision(image_path: str | Path, system_prompt: str, user_prompt: str) -> dict:
    result = analyze_image(
        image_path,
        system_prompt,
        user_prompt,
        max_image_width=1280,
        max_tokens=1600,
        json_output=True,
    )
    print(
        f"千问视觉完成：model={result['model']}，"
        f"prompt_tokens={result['usage']['prompt_tokens']}，"
        f"completion_tokens={result['usage']['completion_tokens']}"
    )
    return json_text(result)


def json_text(result: dict) -> dict:
    raw = str(result.get("text") or "").strip().removeprefix("```json").removesuffix("```").strip()
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("千问必须返回 JSON 对象")
    return payload


def upload_run_files(workflow: str, run_id: str, paths: list[str | Path], manifest: dict) -> dict:
    """把成片与主题图上传 R2，只做交付，不触发任何平台发布。"""
    uploaded = []
    for value in paths:
        path = Path(value).resolve()
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        stored = upload_public_file(path, f"runs/{workflow}/{run_id}/{path.name}", content_type=content_type)
        uploaded.append({**stored, "source_path": str(path), "source_name": path.name})
    output_dir = Path(str(manifest["output_dir"])).resolve()
    remote_manifest_path = output_dir / "r2-manifest.json"
    remote_manifest = {**manifest, "r2_files": uploaded, "platform_publish": False}
    remote_manifest_path.write_text(json.dumps(remote_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    remote_manifest_upload = upload_public_file(
        remote_manifest_path,
        f"runs/{workflow}/{run_id}/r2-manifest.json",
        content_type="application/json; charset=utf-8",
    )
    return {"files": uploaded, "manifest": remote_manifest_upload}


def upload_diagnostic_files(workflow: str, run_id: str, paths: list[str | Path], manifest: dict) -> dict:
    """把失败诊断文件上传到单独的一日清理目录。"""
    uploaded = []
    prefix = f"diagnostics/{workflow}/{run_id}"
    for value in paths:
        path = Path(value).resolve()
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        stored = upload_public_file(path, f"{prefix}/{path.name}", content_type=content_type)
        uploaded.append({**stored, "source_path": str(path), "source_name": path.name})
    diagnostic_manifest = {**manifest, "expires_after_days": 1, "r2_files": uploaded}
    manifest_path = Path(paths[0]).resolve().parent / "failed-subject-sheets-r2.json"
    manifest_path.write_text(json.dumps(diagnostic_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    stored_manifest = upload_public_file(
        manifest_path,
        f"{prefix}/failed-subject-sheets.json",
        content_type="application/json; charset=utf-8",
    )
    return {"files": uploaded, "manifest": stored_manifest}


def write_summary(title: str, rows: list[tuple[str, str]]) -> None:
    summary_path = os.getenv("GITHUB_STEP_SUMMARY", "").strip()
    if not summary_path:
        return
    lines = [f"## {title}", ""]
    lines.extend(f"- {label}：{value}" for label, value in rows)
    with Path(summary_path).open("a", encoding="utf-8") as stream:
        stream.write("\n".join(lines) + "\n")
