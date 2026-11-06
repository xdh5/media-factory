---
name: produce-anime-video
description: 按作者主页找动漫、核对集数，或按集序制作动漫成片。发布使用动漫 YouTube 发布技能。
---

# 制作动漫视频

1. 用 `anime_get_production_config` 读取配置。
2. 主页找剧用 `anime_discover_series`。核对别称、改名、补发、合集、缺集和完结证据。扫描触顶可扩大到 1000 条；区分暂未找到与确认缺失。存疑用 `anime_inspect_sources`，优先核对标题、集号、时间和转写，封面留作取证。只查集数时到此交付。
3. 用 `anime_start_compile` 制作。直接链接传有序 `share_texts`，主页选片传 `discovery_path`、有序 `work_ids` 和 `selection_reason`。去掉重复覆盖，完整合集保持原文件，多来源在集边界按约三小时均衡分段。
4. 用 `anime_get_task` 查询同一任务至结束，交付成片和清单路径。
