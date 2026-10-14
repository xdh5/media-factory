"""动漫拼接 MCP 常量。"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
OUTPUT_ROOT = PROJECT_ROOT / "cache" / "output" / "anime"
MCP_ID = "anime"

# 单段最长 3 小时。总时长按这个上限向上取整后均分。
MAX_PART_SECONDS = 3 * 60 * 60

SERVER_INSTRUCTIONS = (
    "动漫视频拼接 MCP。用户按顺序给出抖音、快手或其他已支持平台的分享链接后，"
    "调用 anime_start_compile，再用返回的 task_path 调用 anime_poll_task，直到 done=true。"
    "必须保持用户给出的链接顺序。没有计划发布日期，禁止询问日期，禁止改写标题、描述和话题。"
    "单段最长 3 小时：不超过 3 小时输出一段；超过 3 小时且不超过 6 小时均分成两段；"
    "超过 6 小时且不超过 9 小时均分成三段；更长则按每 3 小时向上取整继续均分，每段都不超过 3 小时。"
    "每段的标题、描述、话题只照搬该段所含来源的解析结果。产物写入本地 cache/output/anime/，不上传、不发布。"
    "耗时步骤必须 start 后轮询，禁止重复 start，禁止绕过 MCP 自行下载或拼接。"
)
