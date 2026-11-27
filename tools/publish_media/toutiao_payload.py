"""发布业务生成头条执行请求，执行器只读取已确定的内容和选项。"""

from .toutiao_micro_image import select_toutiao_micro_image


def build_toutiao_publication_payload(manifest: dict, kind: str) -> dict:
    payload = {
        "title": manifest["title"],
        "description": manifest["publish_copy"],
        "tags": " ".join(f"#{tag}" for tag in manifest["hashtags"]),
        "creative_statement": "ai_generated",
        "output_dir": manifest["output_dir"],
        "cover_path": manifest["cover_path"],
        "publish_options": {"quote_ai": True},
    }
    if kind == "micro":
        payload["micro_image_path"] = select_toutiao_micro_image(manifest)
        payload["micro_text"] = manifest["micro_summary"] + "\n\n" + " ".join(
            f"#{tag}#" for tag in manifest["hashtags"])
    elif kind == "article":
        payload.pop("cover_path")
        payload["toutiao_article_path"] = manifest["toutiao_article_path"]
        payload["publish_options"].update(first_publish=True, sync_micro=False)
    else:
        payload.update(video_path=manifest["video_path"], cover_path=manifest["widescreen_cover_path"])
        payload["publish_options"]["generateImageText"] = False
    return payload
