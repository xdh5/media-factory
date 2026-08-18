"""MatrixMedia 集成入口。发布必须调用 MatrixMedia MCP，不要在这里包一层 CLI。"""

from .layout import derive_partition, describe_matrixmedia_layout, get_mcp_entry, get_matrixmedia_dir

__all__ = [
    "derive_partition",
    "describe_matrixmedia_layout",
    "get_mcp_entry",
    "get_matrixmedia_dir",
]
