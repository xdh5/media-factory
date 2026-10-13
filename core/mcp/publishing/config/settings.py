"""统一发布 MCP 路径配置。"""

from pathlib import Path

MCP_ID = "publishing"
PROJECT_ROOT = Path(__file__).resolve().parents[4]
CACHE_ROOT = PROJECT_ROOT / "cache" / MCP_ID
