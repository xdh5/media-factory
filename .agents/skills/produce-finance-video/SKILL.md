---
name: produce-finance-video
description: 使用财经库定稿制作财经、理财或情感短视频。
---

# 制作财经视频

1. 确认北京时间计划发布日期，缺失或有歧义时询问。用 `finance_get_config` 查配置，查库存或缺片用 `finance_get_inventory`。
2. 用 `finance_start_production` 启动生产，日内两篇分别传 `content_part=1`、`2`。默认 `generate_images=false` 搜索实拍；需要生图时传 `true`。用 `finance_get_task` 通过 workflow_id 查询准备结果，同一流程恢复原素材模式。
3. `stage=ready_to_search` 时调用 `finance_continue_production(workflow_id)`；正文和分镜均读取稿库定稿，不再现场生成。
4. `stage=awaiting_images` 时，读取 MCP 返回的参考图和生图指令。宿主用参考图作为图像输入，按 image_requests 的画面描述生成暖色手绘卡通图片，逐镜保存到 output_path，调用 `finance_continue_production(workflow_id)`；另存位置时按镜头顺序传 image_paths。MCP 和 workflow 不调用生图模型。
5. workflow 完成素材处理、中文字幕、音乐、合成及 R2 上传。用 `finance_get_task(workflow_id=...)` 查询流程；只有 `stage=completed` 才代表整条流程完成。
6. 交付本地成片、清单、标题、标签及 R2 地址。失败恢复使用原 workflow_id 和稿库分镜。
