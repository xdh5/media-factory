"""两个视频工作流共用的千问、R2 与日志方法。"""

from __future__ import annotations

import json
import mimetypes
import os
import tarfile
from pathlib import Path

import boto3

from core.tools.qwen_text import generate_text
from core.tools.qwen_vision import analyze_image
from core.tools.r2_storage import upload_public_file


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def restore_finance_library() -> Path:
    """从 R2 恢复财经图库；压缩包可由 GitHub Cache 复用。"""
    expected = PROJECT_ROOT / "data" / "image_library" / "finance"
    if expected.is_dir() and any(expected.iterdir()):
        return expected
    required = ["R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET"]
    values = {name: os.getenv(name, "").strip() for name in required}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise RuntimeError(f"恢复财经图库缺少 R2 配置：{', '.join(missing)}")
    archive = PROJECT_ROOT / "cache" / "assets" / "finance-images.tar"
    archive.parent.mkdir(parents=True, exist_ok=True)
    if not archive.is_file() or archive.stat().st_size == 0:
        client = boto3.client(
            "s3",
            endpoint_url=f"https://{values['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
            aws_access_key_id=values["R2_ACCESS_KEY_ID"],
            aws_secret_access_key=values["R2_SECRET_ACCESS_KEY"],
            region_name="auto",
        )
        client.download_file(values["R2_BUCKET"], "assets/finance-images.tar", str(archive))
    with tarfile.open(archive, "r:") as bundle:
        names = [member.name.replace("\\", "/").lstrip("./") for member in bundle.getmembers() if member.name]
        if not names:
            raise RuntimeError("R2 财经图库压缩包为空")
        first = names[0]
        if first.startswith("data/"):
            target = PROJECT_ROOT
        elif first.startswith("image_library/"):
            target = PROJECT_ROOT / "data"
        else:
            target = PROJECT_ROOT / "data" / "image_library"
        target.mkdir(parents=True, exist_ok=True)
        bundle.extractall(target, filter="data")
    if not expected.is_dir() or not any(expected.iterdir()):
        raise RuntimeError(f"财经图库解压后目录不存在或为空：{expected}")
    return expected


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
