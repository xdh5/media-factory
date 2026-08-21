"""生图工具错误定义。"""

from __future__ import annotations

from ._constants import SUPPORTED_STYLE_IDS


class ImageGenerationError(Exception):
    """生图错误基类，可直接转换成 Agent 可理解的结构。"""

    code = "IMAGE_GENERATION_ERROR"

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


class InvalidParameterError(ImageGenerationError):
    code = "INVALID_PARAMETER"

    def __init__(self, parameter: str, message: str):
        super().__init__(message, {"parameter": parameter})


class StyleNotFoundError(ImageGenerationError):
    code = "STYLE_NOT_FOUND"

    def __init__(self, style: str):
        super().__init__(
            f"不支持画风 '{style}'，请从 {SUPPORTED_STYLE_IDS} 中选择，或不传 style。",
            {"requested_style": style, "supported_styles": SUPPORTED_STYLE_IDS},
        )


class ReferenceImageError(ImageGenerationError):
    code = "REFERENCE_IMAGE_ERROR"


class AIConfigurationError(ImageGenerationError):
    code = "AI_CONFIGURATION_ERROR"


class AIGenerationError(ImageGenerationError):
    code = "AI_GENERATION_FAILED"


class AgentImageTaskError(ImageGenerationError):
    code = "AGENT_IMAGE_TASK_ERROR"


class ImageLibraryDatabaseError(ImageGenerationError):
    code = "IMAGE_LIBRARY_DATABASE_ERROR"


class ImageLibraryEmptyError(ImageGenerationError):
    code = "IMAGE_LIBRARY_EMPTY"
