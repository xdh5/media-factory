"""MatrixMedia 集成路径与 MCP 约定。"""

from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[3]

# 源码落在 integrations，不在 Docker 镜像里跑 Electron。
MATRIXMEDIA_DIR = _PROJECT_ROOT / "integrations" / "MatrixMedia"
MATRIXMEDIA_MCP_ENTRY = MATRIXMEDIA_DIR / "mcp" / "dist" / "index.js"
MATRIXMEDIA_MCP_SOURCE = MATRIXMEDIA_DIR / "mcp" / "src" / "index.ts"

# Electron 把 app.name 固定为 matrix-video，GUI / CLI / MCP 共用同一 userData。
ELECTRON_APP_NAME = "matrix-video"
WINDOWS_USERDATA_DIR = Path.home() / "AppData" / "Roaming" / ELECTRON_APP_NAME
DOCUMENTS_DATA_DIR = Path.home() / "Documents" / "MatrixMedia" / "data"

# MCP publish_video 的平台码；partition 为 persist:{phone}{中文名}。
PLATFORM_CN = {
    "dy": "抖音",
    "ks": "快手",
    "blbl": "哔哩哔哩",
    "bjh": "百家号",
    "tt": "头条",
    "sph": "视频号",
}
MCP_VIDEO_PLATFORMS = tuple(PLATFORM_CN.keys())
MCP_SERVER_NAME = "matrixmedia"
MCP_TOOLS = ("list_accounts", "list_history", "login", "login_status", "publish_video", "publish_article")
