---
name: analyze-finance-douyin
description: 复盘财经抖音账号时，读取公开作品的原始指标和 Cloudflare D1 定稿。
---

# 获取财经抖音复盘数据

1. 调用 `finance_start_douyin_analysis`，用返回的 `task_path` 调用 `finance_get_task` 查询至完成。账号需要登录时请用户在 Publisher 重新登录。
2. 读取结果中的 `works`。每条包括作品信息、平台原始 `statistics` 和 `metrics`、定稿匹配状态及已匹配的 `script.editorial`。黄金钩子在 `source_hook`，正文在 `article`。
3. 按用户本次的问题和实际数据决定怎样分析。内容依据 Cloudflare D1 定稿，禁止打开、下载、播放或转写视频。
