"""上传生产清单并同步本地和远端的清单地址。"""

import json
from pathlib import Path

from .storage import upload_public_file


def upload_public_manifest(path: str | Path, manifest: dict, key: str) -> dict:
    """上传清单，将自身公网地址写回内容后同步到同一对象。"""
    path = Path(path)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    stored = upload_public_file(path, key, content_type="application/json")
    manifest["manifest_url"] = stored["url"]
    manifest["manifest_r2_key"] = stored["key"]
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return upload_public_file(path, stored["key"], content_type="application/json")
