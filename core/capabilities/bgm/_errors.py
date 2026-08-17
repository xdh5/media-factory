"""BGM 选择错误定义。

错误带 code / message / details，to_dict() 输出 JSON 友好结构，
上层（agent 工具/API）捕获后可直接序列化返回：
    {"error": {"code": "BGM_NOT_FOUND", "message": "...", "details": {...}}}
"""

from __future__ import annotations

from ._constants import SUPPORTED_MOODS, BGM_LIBRARY

__all__ = [
    "BGMSelectError",
    "InvalidParameterError",
    "BGMNotFoundError",
    "BGMIDNotFoundError",
    "BGMFileNotFoundError",
]


class BGMSelectError(Exception):
    """BGM 选择错误基类。子类通过 code 声明错误码。"""

    code = "BGM_SELECT_ERROR"

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


class InvalidParameterError(BGMSelectError):
    """参数非法（mood/id 缺失、冲突或取值无效）。"""

    code = "INVALID_PARAMETER"

    def __init__(self, parameter: str, message: str):
        self.parameter = parameter
        super().__init__(message, {"parameter": parameter})


class BGMNotFoundError(BGMSelectError):
    """mood 在曲库里匹配不到任何 BGM。

    details 里列出所有可用的 mood 和每首曲的信息，
    方便 Agent 直接做参数修正。
    """

    code = "BGM_NOT_FOUND"

    def __init__(self, *, mood: str):
        super().__init__(
            message=(
                f"没有匹配 mood='{mood}' 的背景音乐。"
                f"可用 mood：{SUPPORTED_MOODS}。"
                "请从以上枚举中选择最接近的音乐情绪。"
            ),
            details={
                "requested": {"mood": mood},
                "supported_moods": SUPPORTED_MOODS,
                "available_bgm": [
                    {
                        "id": b["id"],
                        "name": b["name"],
                        "moods": b["moods"],
                    }
                    for b in BGM_LIBRARY
                ],
            },
        )


class BGMIDNotFoundError(BGMSelectError):
    """id 在曲库里不存在。"""

    code = "BGM_ID_NOT_FOUND"

    def __init__(self, *, bgm_id: str):
        available_ids = [bgm["id"] for bgm in BGM_LIBRARY]
        super().__init__(
            message=(
                f"没有 id='{bgm_id}' 的背景音乐。"
                f"可用 ID：{available_ids}。"
                "请使用其中一个 ID，或改用 mood 匹配。"
            ),
            details={
                "requested_id": bgm_id,
                "available_ids": available_ids,
            },
        )


class BGMFileNotFoundError(BGMSelectError):
    """BGM 记录存在，但对应的静态音频文件缺失。"""

    code = "BGM_FILE_NOT_FOUND"

    def __init__(self, *, bgm_id: str, path: str):
        super().__init__(
            message=(
                f"BGM id='{bgm_id}' 存在，但音频文件 '{path}' 不存在。"
                "请检查 static 资源是否已随镜像完整打包。"
            ),
            details={"id": bgm_id, "path": path},
        )
