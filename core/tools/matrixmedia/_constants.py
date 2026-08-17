"""MatrixMedia CLI 工具常量。"""

import os
from pathlib import Path

MATRIXMEDIA_EXECUTABLE_ENV = "MATRIXMEDIA_CLI_PATH"
_TOOL_ROOT = Path(__file__).resolve().parent
_PROJECT_ROOT = _TOOL_ROOT.parents[2]
DEFAULT_MATRIXMEDIA_EXECUTABLE = str(
    Path.home() / "Documents" / "ai-video-maker" / "integrations" / "MatrixMedia"
)
PROJECT_DATABASE_PATH = _PROJECT_ROOT / "data" / "media_factory.sqlite3"
MATRIXMEDIA_USER_DATA_ROOT = Path(
    os.getenv("APPDATA", str(Path.home() / "AppData" / "Roaming"))
) / "matrix-video"
MATRIXMEDIA_RUNTIME_LAYOUTS = [
    ("app/main.js", "electron.exe"),
    ("dist/electron/main.js", "node_modules/electron/dist/electron.exe"),
    ("dist/electron/main.js", "node_modules/.bin/electron"),
]

PUBLISH_PLATFORMS = ["dy", "sph", "blbl", "bjh", "tt", "ks", "xhs", "fqsp"]
QUERY_PLATFORMS = [*PUBLISH_PLATFORMS, "juejin"]
LOGIN_PLATFORMS = ["dy", "sph"]
PLATFORM_NAMES = {
    "dy": "抖音",
    "sph": "视频号",
    "blbl": "哔哩哔哩",
    "bjh": "百家号",
    "tt": "头条",
    "ks": "快手",
    "xhs": "小红书",
    "fqsp": "番茄视频",
    "juejin": "掘金",
}
PLATFORM_IDS_BY_NAME = {name: identifier for identifier, name in PLATFORM_NAMES.items()}
HISTORY_STATUSES = ["success", "failed", "publishing", "scheduled", "expired"]

QUERY_TIMEOUT_SECONDS = 180
PUBLISH_TIMEOUT_SECONDS = 2400
LOGIN_TIMEOUT_SECONDS = 900

EXIT_CODE_MESSAGES = {
    1: "MatrixMedia CLI 发生未捕获异常",
    2: "MatrixMedia CLI 参数错误",
    3: "MatrixMedia CLI 任务失败，常见原因是未登录、会话过期或上传失败",
    4: "视频号链接添加失败，视频已转存草稿，需要人工检查",
}
