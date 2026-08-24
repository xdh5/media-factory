"""统一发布 MCP 常量。"""

from pathlib import Path

MCP_ID = "publishing"
PROJECT_ROOT = Path(__file__).resolve().parents[3]
CACHE_ROOT = PROJECT_ROOT / "cache" / MCP_ID
