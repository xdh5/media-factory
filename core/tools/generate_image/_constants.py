"""生图工具常量。"""

from __future__ import annotations

from pathlib import Path

_STATIC_DIR = Path(__file__).resolve().parent / "static"

QWEN_IMAGE_MODEL = "qwen-image-2.0-pro-2026-06-22"
QWEN_IMAGE_ENDPOINT = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
AGENT_IMAGE_TASK_VERSION = 4
AGENT_IMAGE_CONTEXT_NAME = "agent-image-context.json"
AGENT_IMAGE_MANIFEST_NAME = "agent-image-manifest.json"
IMAGE_ASPECT_MAX_PIXEL_ERROR = 1

# 本地图库
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
IMAGE_LIBRARY_PROJECT_ROOT = _PROJECT_ROOT
IMAGE_LIBRARY_DATA_ROOT = _PROJECT_ROOT / "data" / "image_library"
FINANCE_GENERATED_LIBRARY_LINE = "finance_generated"
FINANCE_GENERATED_LIBRARY_ROOT = _PROJECT_ROOT / "data" / "image_library_finance"
IMAGE_LIBRARY_CACHE_ROOT = _PROJECT_ROOT / "cache" / "assets"
IMAGE_LIBRARY_ARCHIVE_KEY_TEMPLATE = "assets/{line}-images.tar"
FINANCE_GENERATED_LIBRARY_ARCHIVE_KEY = "assets/image_library_finance.tar"
IMAGE_LIBRARY_LINE_PATTERN = r"^[a-z][a-z0-9_]{0,63}$"

SUPPORTED_STYLE_IDS = ["painterly", "realistic", "paper"]

VISUAL_STYLE_LIBRARY: list[dict] = [
    {
        "id": "painterly",
        "name": "电影感厚涂油画",
        "description": (
            "宽笔触、厚重颜料堆叠和方向性高光塑造体积；强烈自然的明暗对比、"
            "深色阴影与少量高饱和强调色；保留手绘边缘与画布肌理。"
        ),
        "reference_image_path": str(_STATIC_DIR / "ref_painterly.png"),
    },
    {
        "id": "realistic",
        "name": "写实摄影",
        "description": (
            "照片级真实画面，物体比例与透视准确，材质纹理自然清晰；"
            "自然柔和光线、真实阴影、克制配色与合理景深。"
        ),
        "reference_image_path": str(_STATIC_DIR / "ref_realistic.png"),
    },
    {
        "id": "paper",
        "name": "纸艺折纸",
        "description": (
            "手工折纸与纸雕微缩场景，主体由清晰的低多边形折面构成；"
            "明显的折痕、锐利纸边缘、层叠纸层构建景深。"
        ),
        "reference_image_path": str(_STATIC_DIR / "ref_paper.png"),
    },
]
