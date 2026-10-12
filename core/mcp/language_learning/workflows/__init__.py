"""语言学习 MCP 工作流公开入口。"""

from .common import COMMON_TOOLS
from .direct import DIRECT_TOOLS
from .media import MEDIA_TOOLS
from .packs import PACK_TOOLS
from .publishing import PUBLISHING_TOOLS
from .runtime import RUNTIME_TOOLS

ALL_TOOLS = (
    *COMMON_TOOLS,
    *DIRECT_TOOLS,
    *PACK_TOOLS,
    *MEDIA_TOOLS,
    *PUBLISHING_TOOLS,
    *RUNTIME_TOOLS,
)

__all__ = ["ALL_TOOLS"]
