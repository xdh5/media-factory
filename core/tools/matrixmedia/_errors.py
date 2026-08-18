"""MatrixMedia 集成错误定义。"""

from __future__ import annotations

from ._constants import MATRIXMEDIA_DIR, MATRIXMEDIA_MCP_ENTRY


class MatrixMediaError(Exception):
    """MatrixMedia 集成错误基类。"""

    code = "MATRIXMEDIA_ERROR"

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


class MatrixMediaNotFoundError(MatrixMediaError):
    code = "MATRIXMEDIA_NOT_FOUND"

    def __init__(self):
        super().__init__(
            f"未找到 MatrixMedia 源码目录 {MATRIXMEDIA_DIR}。请确认已放入 integrations/MatrixMedia。",
            {"matrixmedia_dir": str(MATRIXMEDIA_DIR)},
        )


class MatrixMediaMcpNotBuiltError(MatrixMediaError):
    code = "MATRIXMEDIA_MCP_NOT_BUILT"

    def __init__(self):
        super().__init__(
            "MatrixMedia MCP 尚未构建。请在本机 Windows 上进入 integrations/MatrixMedia/mcp 执行 npm install && npm run build，"
            "生成 mcp/dist/index.js 后再接入 Cursor MCP。不要在 Docker 里构建或运行。",
            {"mcp_entry": str(MATRIXMEDIA_MCP_ENTRY)},
        )


class MatrixMediaHostError(MatrixMediaError):
    code = "MATRIXMEDIA_HOST_REQUIRED"

    def __init__(self):
        super().__init__(
            "MatrixMedia 必须在 Windows 本机运行，不能放进 Linux Docker。"
            "它依赖 Electron 图形登录，并把 cookie 写在本机 %APPDATA%\\matrix-video。",
            {"os_requirement": "windows-host"},
        )
