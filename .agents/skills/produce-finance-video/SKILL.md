---
name: produce-finance-video
description: 使用财经库定稿制作大鹅认知口播长视频及 YouTube Shorts，支持生图和实拍素材。
---

# 制作财经视频

## 准备

- 确认北京时间计划日期，缺失或有歧义时询问。`finance_get_config` 读取生产配置，`finance_get_inventory` 查询库存与缺片。
- 正文、分镜、SSML、发布文案和三版封面均使用稿库定稿；缺项先按 `collect-finance-copy` 补齐。生产不现场改稿、重做封面或代码叠字。
- 按用户要求选择素材模式：生图传 `generate_images=true`，实拍传 `false`；接口默认实拍，不能覆盖用户选择。同一工作流恢复原模式。

## 启动与续跑

调用 `finance_start_production(publish_date, content_part, generate_images)`，日内两篇用分片1、2。保存返回的 `workflow_id`，用 `finance_get_task(workflow_id=...)` 跟进。

| 阶段 | 操作 |
| --- | --- |
| `preparing` | 等待配音准备完成 |
| `ready_to_search` | 调用 `finance_continue_production(workflow_id)` |
| `awaiting_images` | 按下节完成全部图片，再调用续跑工具；另存位置时按镜头顺序传 `image_paths` |
| `ready_to_render` | 调用续跑工具合成 |
| `completed` | 核对产物并交付 |

失败沿用原 `workflow_id` 和稿库分镜恢复；只有 `stage=completed` 才代表整条流程完成。

## 分镜生图

- 读取任务返回的参考图、生图指令与 `image_requests`；宿主把参考图作为图像输入，逐镜生成并保存到对应 `output_path`。MCP 和工作流不调用生图模型。
- 为 GitHub 预制图片时，用 `finance_manage_storyboard_images(aweme_id)` 领取任务，完成后向同一工具按顺序提交 `image_paths`。图片上传 R2，运行器按稿件及分镜版本恢复。
- 生图仅包含正文，末句复用预制片尾。工作流负责图片运镜、字幕、音乐和合成；无需宿主重复实现渲染。

## 交付与核对

- 长视频从第一幕开始，不插入封面。三版封面独立交付：`cover.png`（4:3）、`cover-portrait.png`（3:4）、`cover-widescreen.png`（16:9）。
- `youtube-short.mp4` 按定稿选段截取长片画面和原声，约500字，1080×1920；保留字幕、贴图与运镜，横画面居中，上下为同镜头模糊压暗背景。顶部全程显示完整标题，按 `title_lines` 分一至两行，首行白、次行黄，显示时仅保留顿号；不另做封面、配音或静音首帧，不增加时长拦截。
- `youtube-description.txt` 使用定稿说明和10个专用标签，不生成章节。
- 核对长短片尺寸、实际时长、字幕和片尾完整性，交付本地成片、清单、标题标签及 R2 地址。

仅在修改片尾、排查渲染或资源清理时，阅读 [资源维护](references/resource-maintenance.md)。
