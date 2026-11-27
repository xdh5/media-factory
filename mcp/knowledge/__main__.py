"""通过标准 stdio 启动知识服务。"""

from .server import mcp

mcp.run(transport="stdio")
