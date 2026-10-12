"""语言学习 MCP 启动入口：`python -m core.mcp.language_learning`。"""

from .server import mcp


if __name__ == "__main__":
    mcp.run(transport="stdio")
