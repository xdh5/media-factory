---
name: finance-video
description: 使用项目 Finance MCP 工作流制作中文财经文生图视频；适用于“做财经视频”“运行 Finance 工作流”“生成理财短视频”等请求。
---

# Finance 视频工作流

说明文档：`workflows/finance/finance.md`。MCP 入口：`python -m workflows.finance.index`。

## 使用前提

- 制作阶段只调用 `media-factory-finance` 的 `finance_*` 工具。
- 用户确认发布后改调 MatrixMedia MCP：`list_accounts`、`publish_video`。禁止用本地脚本或 Python 包装代替。账号组固定为「心灵鸡汤」。
- 稿件确认后才能制作视频。成品必须先展示给用户看过，用户明确确认后才能发布。
- 发完后向用户展示发布结果，并询问是否删除本次生产文件；只有用户明确确认后才调用 `finance_clear_run`。
- 除稿件确认、成片确认发布、清缓存确认外，其余步骤连续自动执行，不向用户询问画风、声音、BGM、分镜、字幕、动效或缓存设置。

## 第一阶段：生成稿件

1. 调用 `finance_get_draft_context`，读取最近 30 天话题和两个 Prompt。
2. 使用当前 Agent 的文本模型选择一个不重复的财经或理财话题。
3. 把话题代入 `article_prompt_template`，严格生成正文。
4. 根据 `metadata_prompt` 生成长标题、短标题和四个标签。
5. 调用 `finance_save_draft` 保存稿件。
6. 向用户完整展示话题、正文、长标题、短标题和四个标签，然后停止。只询问用户是否确认稿件，不得继续制作。

用户要求修改时，修改完整稿件后重新调用 `finance_save_draft`，并传入原 `draft_path`。新稿件仍必须再次展示并确认。

## 第二阶段：自动制作视频

仅当用户在当前对话中明确确认所展示稿件后执行：

1. 使用上一阶段返回的 `draft_path` 调用 `finance_prepare_storyboard`，传 `user_confirmed=true`；该工具立即返回后台任务 `job_id`。
2. 使用 `finance_get_job` 查询任务。`queued` 或 `running` 时等待后继续查询；`failed` 时根据 `error` 修正；只有 `completed` 才读取 `result`。
3. 使用当前 Agent 的文本模型严格按照 `result.storyboard_prompt` 生成完整分镜文本，不向用户询问分镜意见。
4. 调用 `finance_prepare_images`，传入相同 `draft_path`、完整 `storyboard_text` 和 `user_confirmed=true`。
5. 对返回结果中 `needs_generation=true` 的每个任务，使用当前 Agent 自己的生图能力生成图片。必须把 `referenced_image_paths` 作为本地图片路径数组原样传给生图能力，并原样使用 `prompt`、`radio` 和 `size`；不得把参考图当作内容图。路径参数序列化失败、宿主不支持本地参考图或无法读取其中任意一张时，必须将该图片记为 `attempts=0`、`capability_unavailable=true`，交给 `finance_submit_images` 使用方舟兜底；严禁改用文字描述、复述提示词、想象参考图内容或无参考图生图。缓存命中的任务不得重做。
6. 当前 Agent 有生图能力时，每张失败图片必须独立尝试最多 3 次；成功结果记录 `image_id`、本地 `image_path`。连续失败 3 次的图片记录 `image_id`、`attempts=3` 和错误列表。当前 Agent 明确没有生图能力时，不尝试，记录 `image_id`、`attempts=0`、`capability_unavailable=true`。
7. 调用 `finance_submit_images`，传入 `context_path`、成功的 `images` 和失败的 `failures`；该工具只对无能力或失败满 3 次的单张图片调用方舟，并立即返回后台任务 `job_id`。
8. 使用 `finance_get_job` 查询提交图片任务；完成后使用 `result.manifest_path` 调用 `finance_finish_video`。
9. `finance_finish_video` 会立即返回后台任务 `job_id`。使用 `finance_get_job` 查询到 `completed`，从 `result` 读取成品；不得因为任务仍在运行就重启 MCP 或绕过工具执行本地脚本。
10. `result.status` 为 `awaiting_publish_confirmation` 后，必须把成片给用户看：展示 `video_path`（打开或给出可播放路径）、标题、短标题、标签和发布文案，然后停止。只询问是否确认发布。未确认不得调用 MatrixMedia。
11. 用户明确确认发布后，调用 MatrixMedia `list_accounts`，筛选 `phone` 等于 `result.matrixmedia_account_group`（「心灵鸡汤」）且已登录的视频账号。平台码对照：抖音 `dy`、快手 `ks`、哔哩哔哩 `blbl`、百家号 `bjh`、头条 `tt`、视频号 `sph`；跳过掘金、番茄视频、小红书。对每个账号依次调用一次 `publish_video`：`file` 用 `result.video_path`，`title` 用 `result.title`，`bt2` 用 `result.short_title`，`tags` 把四个标签拼成一个字符串，`phone` 用账号组名「心灵鸡汤」，`platform` 用上表。一个失败不要中断其余账号，记入结果。
12. 全部调用结束后向用户展示各账号发布结果。然后询问是否删除本次生产文件；用户确认后再调用 `finance_clear_run`，传入 `result.run_id` 和 `confirmed=true`。话题记录保留。未确认不得清缓存。

TTS、时间轴、字幕、动效、镜头缓存、封面前插、BGM 混音和成品入库全部由工具自动完成。生图优先使用当前宿主 Agent，因此 Codex、Trae 或其他具备生图并保存本地文件能力的 Agent 均可运行；只有 Agent 无生图能力或单张图片连续失败 3 次时才使用方舟兜底。
Finance 音频策略固定为：完整旁白 `-14 LUFS`、True Peak `-1.5 dB`、LRA `7`，BGM 增益 `0.28`，混合后整体增益 `0.85`，BGM 淡入 `1` 秒、淡出 `2` 秒。Agent 不得自行修改这些值。

“稿件可以”“继续制作”只授权制作视频。发布必须等用户看过成片并再次确认。“可以删”“清缓存”才授权 `finance_clear_run`。
