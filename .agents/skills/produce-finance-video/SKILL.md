---
name: produce-finance-video
description: 使用财经库定稿制作财经、理财或情感短视频。
---

# 制作财经视频

1. 确认北京时间计划发布日期，缺失或有歧义时询问。用 `finance_get_config` 查配置，查库存或缺片用 `finance_get_inventory`。
2. 用 `finance_start_production` 启动完整生产流程，日内两篇分别传 `content_part=1`、`2`。用 `finance_get_task` 通过返回的 workflow_id 查询启动结果。
3. `stage=waiting_storyboard` 时按返回提示写实拍分镜，沿用稿库正文、标题和标签；调用 `finance_continue_production(workflow_id, storyboard_text)`。
4. workflow 自动搜索和下载实拍素材，完成配音、中文字幕、音乐、合成及 R2 上传。用 `finance_get_task(workflow_id=...)` 查询流程；只有 `stage=completed` 才代表整条流程完成。
5. 交付本地成片、清单、标题、标签及 R2 地址。失败恢复使用原 workflow_id 和原分镜。
