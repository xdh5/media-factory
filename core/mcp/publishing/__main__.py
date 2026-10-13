"""统一发布 MCP stdio 启动入口。"""

from .server import mcp


if __name__ == "__main__":
    mcp.run(transport="stdio")
