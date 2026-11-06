---
name: produce-anime-video
description: 按作者主页找动漫、核对集数，或按集序制作动漫成片。发布使用动漫 YouTube 发布技能。
---

# 制作动漫视频

1. 读取 `anime_get_production_config`。主页找剧用 `anime_discover_series`，核对别称、补发、重复、集序和完结证据。存疑用 `anime_inspect_sources`，按标题、集号、时间、转写、封面的顺序取证。扫描触顶可扩大到 1000 条。区分暂未找到和确认缺失。
2. 只查集数时交付核对结果。制作调用 `anime_start_compile`，传有序 `share_texts`，或传 `discovery_path`、有序 `work_ids` 和 `selection_reason`。排除重复覆盖，完整合集保留原文件，多来源按集边界均衡分段。
3. 用 `anime_get_task` 查同一任务，交付成片和清单。
