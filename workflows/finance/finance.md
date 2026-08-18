# Finance 工作流

中文财经文生图短视频。MCP 入口是 `python -m workflows.finance.index`（Cursor / Trae 配置里的 `args` 必须是 `-m` + `workflows.finance.index`）。Agent 只通过 MCP 编排，禁止直接跑 `workflow.py` 或读写缓存/数据库。

## 谁干什么

| 层级 | 职责 |
| --- | --- |
| 宿主 Agent | 选题、写正文和标题标签、写分镜、优先自己生图；成片后给用户看；确认后发矩媒；再确认后清缓存 |
| `media-factory-finance` MCP | `index.py` 暴露 `finance_*` 工具：存稿、分镜/交图/出片后台任务、查任务、清本次生产目录 |
| MatrixMedia MCP | `list_accounts`、`publish_video`。按账号组「心灵鸡汤」逐个发，不经过 Python 包装 |
| `core/tools`、`core/capabilities` | TTS、生图、出片、话题去重、后台任务、清目录、BGM、片头 |

财经私有代码在 `workflows/finance/`：`index.py` 是 MCP 入口（与语言学习相同），`tools/draft.py` 管存稿和分镜/出片步骤，`job_runner.py` 把后台单派给这些函数，`workflow.py` 真正合成，`_agent_images.py` 组封面/镜头生图任务。Prompt 和人物参考图也是财经私有。

## 目录与数据

- 统一库：`data/media_factory.sqlite3`（话题历史、后台任务 `workflow_jobs`）
- 一次生产：`data/finance/runs/{run_id}/cache/`（中间产物）、`outputs/`（成品）
- `run_id` 形如 `run-000001`，话题写入后生成
- 清缓存只删这棵 `runs/{run_id}`，不改话题库

## 确认门禁（三处）

1. **稿件**：`finance_save_draft` 之后必须把话题、正文、长标题、短标题、四个标签完整展示给用户。未确认不得做 TTS/分镜/图/视频。「稿件可以」「继续制作」只授权制作。
2. **成片**：`finance_finish_video` 完成后 `status` 为 `awaiting_publish_confirmation`。必须展示 `video_path`、标题、短标题、标签和发布文案，让用户看过成片。未确认不得调矩媒。
3. **清缓存**：发布结束后询问是否删除本次本地文件。用户明确确认后才调用 `finance_clear_run(run_id, confirmed=true)`。发布与清缓存不是同一次确认。

修改稿件：改完后再次 `finance_save_draft`（带原 `draft_path`，不能换话题），必须重新展示并确认。重做指定镜头/图片时只重做对应缓存，完成后再次展示成片并停在发布确认。

## Agent 步骤

制作阶段只调 `finance_*`。发布阶段改调 MatrixMedia。禁止本地脚本代替 MCP。

1. `finance_get_draft_context`：近 30 天已占用话题 + 正文/标题 Prompt。Agent 自选不重复财经话题，按模板写正文和元数据。
2. `finance_save_draft` → 停，等稿件确认。
3. 确认后 `finance_prepare_storyboard(draft_path, user_confirmed=true)` → 立刻返回 `job_id`。
4. `finance_get_job`：`queued`/`running` 再查；`failed` 看 `error`；`completed` 用 `result.storyboard_prompt` 由 Agent 写完整分镜，不问用户分镜意见。
5. `finance_prepare_images`：返回封面和各镜任务。`needs_generation=true` 的项由宿主生图：`prompt`/`radio`/`size`/`referenced_image_paths` 原样使用；参考图不是内容图。无本地参考图能力则 `capability_unavailable=true`、`attempts=0`，交给提交工具走方舟。缓存命中不重做。有生图能力时单张最多试 3 次。
6. `finance_submit_images` → `job_id`，再用 `finance_get_job`。仅无能力或失败满 3 次的单张走方舟。
7. `finance_finish_video` → `job_id` → `finance_get_job` 到 `completed`，读取成片。不得因耗时长而重启 MCP 或绕过工具。
8. 向用户展示成片，停。确认发布后：`list_accounts`，筛 `phone` 等于 `matrixmedia_account_group`（「心灵鸡汤」）且已登录的视频账号。平台：抖音 `dy`、快手 `ks`、哔哩哔哩 `blbl`、百家号 `bjh`、头条 `tt`、视频号 `sph`；跳过掘金、番茄、小红书。对每个账号依次 `publish_video`（`file`=`video_path`，`title`，`bt2`=`short_title`，`tags` 四个标签拼成串，`phone`=账号组名）。一个失败继续发其余账号。
9. 展示各账号结果后，再问是否删本地文件；确认后 `finance_clear_run`。

除上述确认外，不询问画风、声音、BGM、字幕、动效或缓存参数。

## 后台任务

`finance_prepare_storyboard`、`finance_submit_images`、`finance_finish_video` 经共用 `enqueue_job` 提交，独立进程执行（财经 `handler` 为 `workflows.finance.job_runner:run_job`），MCP 立即返回 `job_id`。查询只用 `finance_get_job`。

状态：`queued` → `running` → `completed` / `failed`。运行中约 10 秒心跳。MCP 启动时只把本工作流仍排队或运行中的任务标为中断；已有缓存保留，重提原步骤即可续跑。

## 成片时工具自动做的

TTS（云希）、响度、时间轴、字幕、动效、镜头缓存、封面前插、BGM 混音、写成片。不写成品索引表；结果在 `finish_video` 的 `result` 和 `data/finance/runs/{run_id}/`。

## 画面与音频（固定）

画面：油画参考图 + 财经人物参考图。人物为克制的欧美气质，不复制参考图身份或构图。普通镜头禁止可读文字、数字、字母、Logo、图表、手机界面等。封面只允许准确标题融入油画。

音频：旁白 `-14 LUFS`、True Peak `-1.5 dB`、LRA `7`，保持原采样帧数。BGM 为电影感励志钢琴，增益 `0.28`，混合 `0.85`，淡入 1 秒、淡出 2 秒。Agent 不得改这些值。
