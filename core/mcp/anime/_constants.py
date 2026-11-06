"""动漫拼接 MCP 常量。"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
OUTPUT_ROOT = PROJECT_ROOT / "cache" / "output" / "anime"

# 按三小时估算段数，只在完整剧集边界均衡分段，保全剧集优先。
MAX_PART_SECONDS = 3 * 60 * 60

# 主页找剧拼接按剧集边界分段；长视频直发按时间线均分，切点可落在来源中间。
SEGMENTATION_EPISODES = "episode-boundaries-v1"
SEGMENTATION_DURATION = "duration-split-v1"

SERVER_INSTRUCTIONS = (
    "先用 anime_get_production_config 读取配置和默认 YouTube 账号组；只有无可用组或多个候选无法确定时才询问。"
    "主页找剧用 anime_discover_series，复核完整列表中的别名、改名、误标、补发和合集覆盖。"
    "按标题、集号、发布时间、时长核对；证据不足时用 anime_inspect_sources 转写必要片段，仍不能判断才取封面。"
    "报告扫描范围、集序、缺集、重复及完结证据，区分暂未找到与确认缺失。扫描到上限时扩大至最多1000条。"
    "仅制作调用 anime_start_compile，保持链接顺序或传入已核实的有序选片。排除重复覆盖；现成完整合集保留原文件，"
    "多来源按约三小时在完整剧集边界均衡切分。保留来源标题、描述和话题，交付本地成片。"
    "发布前确认作品完结且无缺集。anime_prepare_publication 接收主页选片、长视频链接或完整本地清单，"
    "转写开头一分钟；远程来源由 Action 下载，长视频链接按时间线均分为最多三小时的分段。"
    "宿主用转写写一套 YouTube 标题、描述和标签。标题先写剧名与剧情，再加已完结、一口气看完、完整全集等适用词；"
    "描述底部添加 #已完结 #一口气看完 #完整全集，搜索标签也须包含已完结。超长合集、爽文等须符合内容。"
    "调用 anime_save_publication_assets 取得参考帧和预计分段封面任务，宿主为每段生成含集数的封面并提交。"
    "获得发布授权并完成账号预检后调用 anime_start_publication。按作品归入对应播放列表。动漫无需计划发布日期。"
    "本地任务用 anime_get_task(task_path=...) 轮询；Action 触发后按需用 execution_id 查询。"
    "Action 以全部分段取得视频 ID 并保存回执为成功，后台转码不阻塞完成；重跑同一执行优先恢复回执。"
)
