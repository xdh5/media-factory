---
name: finance-video
description: 使用项目 Finance MCP 工作流制作并发布中文财经文生图视频；适用于“做财经视频”“运行 Finance 工作流”“生成理财短视频”等请求。
---

# Finance 视频工作流

## 使用前提

- 只能调用 `media-factory-finance` MCP 中以 `finance_` 开头的工具。
- 稿件确认和发布确认是两个独立门禁，不得合并、推断或跳过。
- 除这两个门禁外，其余步骤连续自动执行，不向用户询问画风、声音、BGM、分镜、字幕、动效或缓存设置。

## 第一阶段：生成稿件

1. 调用 `finance_get_draft_context`，读取最近 30 天话题和两个 Prompt。
2. 使用 Trae 当前模型选择一个不重复的财经或理财话题。
3. 把话题代入 `article_prompt_template`，严格生成正文。
4. 根据 `metadata_prompt` 生成长标题、短标题和四个标签。
5. 调用 `finance_save_draft` 保存稿件。
6. 向用户完整展示话题、正文、长标题、短标题和四个标签，然后停止。只询问用户是否确认稿件，不得继续制作。

用户要求修改时，修改完整稿件后重新调用 `finance_save_draft`，并传入原 `draft_path`。新稿件仍必须再次展示并确认。

## 第二阶段：自动制作视频

仅当用户在当前对话中明确确认所展示稿件后执行：

1. 使用上一阶段返回的 `draft_path` 调用 `finance_prepare_storyboard`，传 `user_confirmed=true`。
2. 使用 Trae 当前模型严格按照返回的 `storyboard_prompt` 生成完整分镜文本，不向用户询问分镜意见。
3. 调用 `finance_finish_video`，传入相同 `draft_path`、完整 `storyboard_text` 和 `user_confirmed=true`。
4. 工具返回 `awaiting_publish_confirmation` 后，向用户展示视频路径、标题和发布文案，然后停止。只询问是否确认发布。

生图、TTS、时间轴、字幕、动效、镜头缓存、封面前插、BGM 混音和成品入库全部由工具自动完成。

## 第三阶段：确认发布

仅当用户在当前对话中明确确认发布当前成品后执行：

1. 使用成品返回的 `manifest_path` 调用 `finance_publish`。
2. 必须传 `publish_confirmed=true`；默认账号组为“心灵鸡汤”。
3. 返回各平台发布结果，不得把部分成功描述为全部成功。

“稿件可以”“继续制作”只授权制作视频，不授权发布；“视频生成好了”也不构成发布授权。
