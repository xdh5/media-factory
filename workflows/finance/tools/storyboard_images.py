"""财经分镜图的 R2 入库、跨运行器下载和成片关联。"""

import hashlib
from pathlib import Path

from tools.database.client import _request
from tools.r2_files import download_file, upload_file


def storyboard_hash(storyboard: str) -> str:
    return hashlib.sha256(storyboard.encode("utf-8")).hexdigest()


def save_storyboard_images(aweme_id: str, storyboard: str, images: dict[str, str]) -> dict:
    """上传到稿件及分镜版本的专用目录，将远端定位信息写入数据库。"""
    digest = storyboard_hash(storyboard)
    existing = _request("GET", "/v1/finance-storyboard-images", query={"aweme_id": aweme_id, "storyboard_hash": digest})["records"]
    stored_images = existing[0]["images"] if existing else {}
    records = {}
    for shot_id, path in images.items():
        source = Path(path).resolve()
        image_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        if shot_id in stored_images and stored_images[shot_id].get("sha256") == image_hash:
            records[shot_id] = stored_images[shot_id]
            continue
        stored = upload_file(source, f"finance/storyboard-images/{aweme_id}/{digest}/{shot_id}{source.suffix.lower()}",
                             content_type={".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}.get(source.suffix.lower(), "image/png"))
        records[shot_id] = {"key": stored["key"], "url": stored["url"], "size": stored["size"], "sha256": image_hash}
    _request("POST", "/v1/finance-storyboard-images", body={
        "aweme_id": aweme_id, "storyboard_hash": digest, "images": records})
    print(f"[分镜图入库] 稿件 {aweme_id}：{len(records)} 张，已保存 R2 定位信息", flush=True)
    return {"aweme_id": aweme_id, "storyboard_hash": digest, "images": records}


def restore_storyboard_images(aweme_id: str, storyboard: str, image_root: Path) -> dict[str, str]:
    """Runner 根据数据库中的 R2 key 下载图片，不读取宿主机器路径。"""
    result = _request("GET", "/v1/finance-storyboard-images", query={
        "aweme_id": aweme_id, "storyboard_hash": storyboard_hash(storyboard)})
    images = {}
    for row in result["records"]:
        for shot_id, asset in row["images"].items():
            target = image_root / f"{shot_id}{Path(asset['key']).suffix}"
            download_file(asset["key"], target)
            images[shot_id] = str(target)
    if images:
        print(f"[分镜图下载] 稿件 {aweme_id}：已从 R2 下载 {len(images)} 张", flush=True)
    return images


def bind_storyboard_images(draft: dict) -> None:
    _request("POST", "/v1/finance-storyboard-images/bind", body={
        "aweme_id": draft["source_aweme_id"], "storyboard_hash": storyboard_hash(draft["storyboard"]),
        "production_id": f"local_mcp:finance:{draft['run_id']}:finance:{draft['content_part']}",
        "publish_date": draft["publish_date"],
    })
