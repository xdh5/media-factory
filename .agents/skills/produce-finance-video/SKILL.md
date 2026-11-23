---
name: produce-finance-video
description: 使用财经库定稿制作财经、理财或情感短视频。
---

# 制作财经视频

1. 确认北京时间计划发布日期，缺失或有歧义时询问。用 `finance_get_config` 查配置，查库存或缺片用 `finance_get_inventory`。
   封面使用采集定稿阶段由宿主整体生图、上传 R2 并登记的成图，包含长短标题和适应内容的风景；生产只下载使用，不重新生成或代码叠字。缺少封面时先完成采集技能的封面步骤。
   为 GitHub 预制分镜图时，先调用 `finance_manage_storyboard_images(aweme_id)` 获取参考图、生图指令和 `image_requests`。宿主使用生图工具，将参考图作为图像输入，按返回指令逐镜生成并保存到各项 `output_path`；完成全部图片后，按镜头顺序向同一工具提交 `image_paths`。图片上传 R2 并登记，运行器按稿件和分镜版本下载。
2. 用 `finance_start_production` 启动生产，日内两篇分别传 `content_part=1`、`2`。默认 `generate_images=false` 搜索实拍；需要生图时传 `true`。用 `finance_get_task` 通过 workflow_id 查询准备结果，同一流程恢复原素材模式。
3. `stage=ready_to_search` 时调用 `finance_continue_production(workflow_id)`；正文和分镜均读取稿库定稿，不再现场生成。
4. `stage=awaiting_images` 时，读取 MCP 返回的参考图、生图指令和 `image_requests`。宿主使用生图工具，将参考图作为图像输入，按返回指令逐镜生成并保存到各项 `output_path`。全部完成后调用 `finance_continue_production(workflow_id)`；另存位置时按镜头顺序传入 `image_paths`。MCP 和 workflow 不调用生图模型。
5. workflow 优先使用 generated-images/shot-001.png 等已有图片，没有图片的镜头搜索视频。每张图片从缓慢放大、缓慢缩小、从上向下、从下向上四种运镜中随机选一种，连续镜头不使用同一种动画，随素材清单保存。镜头交由统一合成器按指纹缓存、并行渲染，随后完成中文字幕、音乐、合成及 R2 上传。用 `finance_get_task(workflow_id=...)` 查询流程；只有 `stage=completed` 才代表整条流程完成。
6. 交付本地成片、清单、标题、标签及 R2 地址。失败恢复使用原 workflow_id 和稿库分镜。

末句使用生产包内预制的大鹅片尾（视频、云逸配音与字幕），不再调用末句 TTS、不重复生成片尾字幕。正文配音拼接预制原始片尾音频，正文画面拼接预制片尾画面后统一混入 BGM；生图任务仅包含正文镜头。资源位于 `workflows/finance/resources/goose-outro-prepared.mp4`、`goose-outro-narration.wav` 和 `goose-outro-prepared.json`，随安装包与 GitHub Actions 生产镜像分发。结束语、音色、语速或字幕样式变更时重新制作这组预制资源。

分镜图在北京时间过了计划发布日期、全部目标已有发布或到时预约回执后，由 Cloudflare 每小时清理；未预约或未到期保留。参考图、封面和成片不在清理范围。

横竖封面作为独立发布图片交付。视频不插入首帧封面，直接从第一幕开始；横竖版均不参与视频画面的拼接。
