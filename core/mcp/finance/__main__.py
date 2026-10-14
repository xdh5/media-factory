"""财经 MCP 启动入口：python -m core.mcp.finance。"""

from .server import mcp

if __name__ == "__main__":
    mcp.run(transport="stdio")
