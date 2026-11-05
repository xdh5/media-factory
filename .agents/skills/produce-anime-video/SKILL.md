---
name: produce-anime-video
description: 生产动漫视频。通过动漫 MCP 从作者主页自主寻找指定作品、判断集序与合集，或按给定链接顺序拼接。不发布、不选日期。
---

# 动漫工具调用流程

1. 调用 `anime_get_production_config` 读取配置和账号组。
2. 主页找剧使用 `anime_discover_series(profile_url, series_name, limit)`；读取完整扫描结果，识别别称、改名、误标和补发。只检查缺集时到此即可，不制作、不发布。
3. 疑点使用 `anime_inspect_sources(discovery_path, work_ids, window_starts, cover_reason)` 提取片段；先用标题、集号、发布时间和转写核对，封面只作最后取证。报告扫描范围、集序、缺集、重复、合集覆盖和完结证据；暂未找到与确认缺失分开说明。扫描到上限继续扩大，最多1000条，不能把更新至某集当成完结。
4. 仅制作使用 `anime_start_compile`：有序链接传 `share_texts`；主页选片传 `discovery_path`、有序 `work_ids`、`selection_reason`。排除重复覆盖，完整合集保持原文件，多来源在完整剧集边界按约三小时均衡分段。
5. 使用 `anime_get_task(task_path=...)` 等待完成，报告成片与清单路径。

下载与拼接使用动漫 MCP。此流程不需要计划发布日期。
