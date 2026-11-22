"""财经分镜生图的宿主参考资源。"""

from tools.resources import package_resource_path


def storyboard_reference_path():
    return package_resource_path("media_factory_mcp", "finance", "resources", "storyboard-style-reference.png")


def read_storyboard_reference() -> bytes:
    """读取财经分镜的拟人大鹅角色与动物漫画风格参考图。"""
    return storyboard_reference_path().read_bytes()


def image_generation_reference() -> dict:
    return {
        "resource_uri": "finance://storyboard/style-reference",
        "reference_image_path": str(storyboard_reference_path()),
        "instructions": package_resource_path("media_factory_mcp", "finance", "prompts", "storyboard-images.md").read_text(encoding="utf-8"),
    }
