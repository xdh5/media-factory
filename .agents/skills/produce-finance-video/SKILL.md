---
name: produce-finance-video
description: 使用财经库定稿制作财经、理财或情感短视频。
---

# 制作财经视频

1. 确认北京时间计划发布日期，缺失或有歧义时询问。用 `finance_get_config` 查配置，查库存或缺片用 `finance_get_inventory`。
2. 用 `finance_start_production` 启动生产，日内两篇分别传 `content_part=1`、`2`。默认 `generate_images=false` 搜索实拍；需要生图时传 `true`。用 `finance_get_task` 通过 workflow_id 查询准备结果，同一流程恢复原素材模式。
3. `stage=ready_to_search` 时调用 `finance_continue_production(workflow_id)`；正文和分镜均读取稿库定稿，不再现场生成。
4. `stage=awaiting_images` 时，读取 MCP 返回的参考图和生图指令。宿主用参考图作为图像输入，按 image_requests 生成暖色二维动物漫画：主人公固定为图中的白色拟人大鹅，配角可以是其他动物，同一期角色外形和服装一致。将原分镜的人类角色转换为动物，保留动作与剧情关系。逐镜保存到 output_path，调用 `finance_continue_production(workflow_id)`；另存位置时按镜头顺序传 image_paths。MCP 和 workflow 不调用生图模型。
5. workflow 优先使用 generated-images/shot-001.png 等已有图片，没有图片的镜头搜索视频。每张图片从五种小幅缩放、平移效果中随机选一种，随素材清单保存。随后完成中文字幕、音乐、合成及 R2 上传。用 `finance_get_task(workflow_id=...)` 查询流程；只有 `stage=completed` 才代表整条流程完成。
6. 交付本地成片、清单、标题、标签及 R2 地址。失败恢复使用原 workflow_id 和稿库分镜。
