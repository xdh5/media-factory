---
name: finance-video
description: 使用项目文生图 MCP、财经业务线制作中文财经短视频；适用于“做财经视频”“运行 Finance 工作流”“生成理财短视频”等请求。
---

# Finance 视频工作流

说明文档：`workflows/finance/finance.md`。MCP 入口：`python -m mcp_servers.text2image`。业务线：`finance`。

## 使用前提

- 制作阶段只调用 `media-factory-text2image` 的 `text2image_*` 工具，且 `line` 固定为 `finance`。
- 用户确认发布后改调 MatrixMedia MCP：`list_accounts`、`login`、`login_status`、`publish_video`。账号组固定为「心灵鸡汤」。
- 发现账号未登录时：抖音/视频号调用 `login`，把返回的二维码图片发给用户扫码，再用 `login_status` 等到 `success` 后发布；其它平台请用户在矩媒 GUI 登录。
- 稿件确认后才能制作视频。成品必须先展示给用户看过，用户明确确认后才能发布。
- 发完后向用户展示发布结果，并询问是否删除本次生产文件；只有用户明确确认后才调用 `text2image_clear_run`。
- 除稿件确认、成片确认发布、清缓存确认外，其余步骤连续自动执行，不向用户询问画风、声音、BGM、分镜、字幕、动效或缓存设置。

## 第一阶段：生成稿件

1. 调用 `text2image_get_draft_context`，传入 `line="finance"`，读取最近 30 天话题和两个 Prompt。
2. 使用当前 Agent 的文本模型选择一个不重复的财经或理财话题。
3. 把话题代入 `article_prompt_template`，严格生成正文。
4. 根据 `metadata_prompt` 生成长标题、短标题和四个标签。
5. 调用 `text2image_save_draft`，`line="finance"`，保存稿件。
6. 向用户完整展示话题、正文、长标题、短标题和四个标签，然后停止。只询问用户是否确认稿件，不得继续制作。

用户要求修改时，修改完整稿件后重新调用 `text2image_save_draft`，传入原 `draft_path` 且 `line` 仍为 `finance`。新稿件仍必须再次展示并确认。

## 第二阶段：自动制作视频

仅当用户在当前对话中明确确认所展示稿件后执行：

1. 使用上一阶段返回的 `draft_path` 调用 `text2image_prepare_storyboard`，传 `user_confirmed=true`；该工具立即返回后台任务 `job_id`。
2. 立刻调用 `text2image_wait_task`。`failed` 时根据 `error` 修正；只有 `completed` 才读取 `result`。不要在对话里空等，也不要轮询 `text2image_get_job`。仍 `queued`/`running` 说明本次等待超时，再调一次 `text2image_wait_task`。
3. 使用当前 Agent 的文本模型严格按照 `result.storyboard_prompt` 生成完整分镜文本，不向用户询问分镜意见。
4. 调用 `text2image_prepare_images`，传入相同 `draft_path`、完整 `storyboard_text` 和 `user_confirmed=true`。财经线按分镜从 `image_library` 抽图：同一期 `library_id` 不重复；Python 按历史选用做冷却和长期均分，避免有的图天天出、有的图从不出现。
5. 若返回 `image_source="library"`，或全部任务 `needs_generation=false`：禁止宿主生图，也禁止方舟兜底。立刻调用 `text2image_submit_images`，传入 `context_path`、空的 `images`。不要调用 `text2image_save_images`。封面不由 Agent 生图。
6. 使用 `text2image_wait_task` 等到提交图片任务结束；完成后使用 `result.manifest_path` 调用 `text2image_finish_video`，只传 `draft_path`、`image_manifest_path`、`user_confirmed=true`。不要再传 `storyboard_text`，工具会读取 prepare_images 已保存的分镜。
7. `text2image_finish_video` 会立即返回后台任务 `job_id`。使用 `text2image_wait_task` 等到 `completed`，从 `result` 读取成品；不得因为任务仍在运行就重启 MCP 或绕过工具执行本地脚本。
8. `result.status` 为 `awaiting_publish_confirmation` 后，必须把成片给用户看：展示 `video_path`（打开或给出可播放路径）、标题、短标题、标签和发布文案，然后停止。只询问是否确认发布。未确认不得调用 MatrixMedia。
9. 用户明确确认发布后，调用 MatrixMedia `list_accounts`，筛选 `phone` 等于 `result.matrixmedia_account_group`（「心灵鸡汤」）的视频账号。平台码对照：抖音 `dy`、快手 `ks`、哔哩哔哩 `blbl`、百家号 `bjh`、头条 `tt`、视频号 `sph`；跳过掘金、番茄视频、小红书。未登录的抖音/视频号：调用 `login(platform, phone)`，把返回的二维码图片发给用户扫码，再用 `login_status(login_id)` 等到 `success`；其它平台未登录则请用户在矩媒 GUI 登录后再发。对每个已登录账号依次调用一次 `publish_video`：`file` 必须用 `result.video_path`（标题命名的那份 mp4），`title` 用 `result.title`，`bt2` 用 `result.short_title`，`tags` 把四个标签拼成一个字符串，`phone` 用账号组名「心灵鸡汤」，`platform` 用上表。禁止把成片复制/改名为 `publish.mp4` 或其它英文名再发。一个失败不要中断其余账号，记入结果。
10. 全部调用结束后向用户展示各账号发布结果。然后询问是否删除本次生产文件；用户确认后再调用 `text2image_clear_run`，传入 `line="finance"`、`result.run_id` 和 `confirmed=true`。话题记录保留。未确认不得清缓存。

TTS、时间轴、字幕、动效、镜头缓存、封面前插、BGM 混音和成品入库全部由工具自动完成。封面由 Python 从镜头图抽一张刻标题，不走生图。财经镜头只从图库抽取，Agent 不得生图或改抽图结果。
财经音频策略固定为：旁白倍速 `+20%`、裁句尾静音、完整旁白 `-14 LUFS`、True Peak `-1.5 dB`、LRA `7`，BGM 增益 `0.28`，混合后整体增益 `0.85`，BGM 淡入 `1` 秒、淡出 `2` 秒。Agent 不得自行修改这些值。

“稿件可以”“继续制作”只授权制作视频。发布必须等用户看过成片并再次确认。“可以删”“清缓存”才授权 `text2image_clear_run`。
