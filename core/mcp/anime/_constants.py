"""动漫拼接 MCP 常量。"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
OUTPUT_ROOT = PROJECT_ROOT / "cache" / "output" / "anime"
MCP_ID = "anime"

# 单段最长 3 小时。总时长按这个上限向上取整后均分。
MAX_PART_SECONDS = 3 * 60 * 60

SERVER_INSTRUCTIONS = (
    "用户明确要求制作并发布时，可用 anime_start_transcribe_intro 转写成片前60秒，"
    "生成独立YouTube发布文案，再 anime_start_publish_youtube 发布到用户指定账号组。"
    "原标题描述的原样保留规则适用于来源存档；独立YouTube文案可按用户要求撰写。"
    "没有发布授权时只生产；发布工具逐段去重并写回数据库，不要求动漫计划发布日期。"
    "用户给作者主页和作品名时，调用 anime_start_discover 获取作品，宿主自主找剧。"
    "先看标题描述、明确集数、发布时间和时长；不清楚再 anime_start_inspect 比较片段口播；"
    "封面识别是最后兜底，必须先取证片段且说明仍不明确的原因。"
    "长时长和开头相同都不能单独证明是完整合集，需核对覆盖范围及结尾。"
    "用 anime_start_compile_series 执行无重复覆盖的选定顺序；单个现成合集直接保留原文件，不拼接不切分。"
    "部分合集可与未覆盖分集拼接；范围重叠、同名版本、缺集或顺序无法确定时不得猜测。"
    "不将截至当前更新说成全剧完结；扫描到上限时扩大范围，最多1000条，仍有限制必须报告。"
    "动漫视频拼接 MCP。用户按顺序给出抖音、快手或其他已支持平台的分享链接后，"
    "调用 anime_start_compile，再用返回的 task_path 调用 anime_poll_task，直到 done=true。"
    "必须保持用户给出的链接顺序。没有计划发布日期，禁止询问日期，禁止改写标题、描述和话题。"
    "需要拼接时单段最长 3 小时：不超过 3 小时输出一段；超过 3 小时且不超过 6 小时均分成两段；"
    "超过 6 小时且不超过 9 小时均分成三段；更长则按每 3 小时向上取整继续均分，每段都不超过 3 小时。"
    "每段的标题、描述、话题只照搬该段所含来源的解析结果。产物写入本地 cache/output/anime/，不上传、不发布。"
    "耗时步骤必须 start 后轮询，禁止重复 start，禁止绕过 MCP 自行下载或拼接。"
)
