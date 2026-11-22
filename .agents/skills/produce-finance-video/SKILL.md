---
name: produce-finance-video
description: 使用财经库定稿制作财经、理财或情感短视频。
---

# 制作财经视频

1. 确认北京时间计划发布日期，缺失或有歧义时询问。用 `finance_get_config` 查配置，查库存或缺片用 `finance_get_inventory`。
   为 GitHub 预制分镜图时，先调用 `finance_manage_storyboard_images(aweme_id)` 获取参考图、生图指令和 `image_requests`。宿主使用生图工具，将参考图作为图像输入，按返回指令逐镜生成并保存到各项 `output_path`；完成全部图片后，按镜头顺序向同一工具提交 `image_paths`。图片上传 R2 并登记，运行器按稿件和分镜版本下载。
2. 用 `finance_start_production` 启动生产，日内两篇分别传 `content_part=1`、`2`。默认 `generate_images=false` 搜索实拍；需要生图时传 `true`。用 `finance_get_task` 通过 workflow_id 查询准备结果，同一流程恢复原素材模式。
3. `stage=ready_to_search` 时调用 `finance_continue_production(workflow_id)`；正文和分镜均读取稿库定稿，不再现场生成。
4. `stage=awaiting_images` 时，读取 MCP 返回的参考图、生图指令和 `image_requests`。宿主使用生图工具，将参考图作为图像输入，按返回指令逐镜生成并保存到各项 `output_path`。全部完成后调用 `finance_continue_production(workflow_id)`；另存位置时按镜头顺序传入 `image_paths`。MCP 和 workflow 不调用生图模型。
5. workflow 优先使用 generated-images/shot-001.png 等已有图片，没有图片的镜头搜索视频。每张图片从五种小幅缩放、平移效果中随机选一种，随素材清单保存。随后完成中文字幕、音乐、合成及 R2 上传。用 `finance_get_task(workflow_id=...)` 查询流程；只有 `stage=completed` 才代表整条流程完成。
6. 交付本地成片、清单、标题、标签及 R2 地址。失败恢复使用原 workflow_id 和稿库分镜。

分镜图在北京时间过了计划发布日期、全部目标已有发布或到时预约回执后，由 Cloudflare 每小时清理；未预约或未到期保留。参考图、封面和成片不在清理范围。
