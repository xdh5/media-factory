"""动漫拼接 MCP 常量。"""

from core.paths import PROJECT_OUTPUT_ROOT, PROJECT_ROOT as PROJECT_ROOT

OUTPUT_ROOT = PROJECT_OUTPUT_ROOT / "anime"

# 按三小时估算段数，只在完整剧集边界均衡分段，保全剧集优先。
MAX_PART_SECONDS = 3 * 60 * 60

# 主页找剧拼接按剧集边界分段；长视频直发按时间线均分，切点可落在来源中间。
SEGMENTATION_EPISODES = "episode-boundaries-v1"
SEGMENTATION_DURATION = "duration-split-v1"

SERVER_INSTRUCTIONS = """用 anime_get_production_config 查询配置和账号组，仅在没有可用组或无法确定时询问。
找剧用 anime_discover_series 核对集序、别称、补发、重复覆盖及完结证据。扫描最多 1000 条；证据不足用 anime_inspect_sources，先转写再取封面。区分暂未找到和确认缺失。
仅制作使用 anime_start_compile，完整合集保留原文件，多来源在剧集边界均衡分段并保留来源文案。
发布前确认用户授权、实际账号授权、全集完结且无缺集。anime_prepare_publication 提供开头转写，宿主写共用 YouTube 文案并按 anime_save_publication_assets 为各段生成含集数的封面。描述加 #已完结 #一口气看完 #完整全集，标签含「已完结」，其他关键词按剧情选用。动漫无需计划发布日期。
用 anime_start_publication 启动，各作品独立播放列表。长链接按时间线均分为最多三小时一段。用 anime_get_task 查 task_path 或 execution_id；Action 以各段视频 ID 和回执齐全为成功，重试复用回执。"""
