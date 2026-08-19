# Finance 工作流

中文财经文生图短视频。这是文生图 MCP 的一条业务线，不自带 MCP。Agent 只通过 `python -m mcp_servers.text2image` 编排，禁止直接跑 MCP 内部实现或读写缓存/数据库。

## 谁干什么

| 层级 | 职责 |
| --- | --- |
| 宿主 Agent | 按本线 Skill 选题、写正文和标题标签、写分镜；镜头从图库抽取，不要生图；成片后给用户看；确认后发矩媒；再确认后清缓存 |
| `media-factory-text2image` MCP | `mcp_servers/text2image` 暴露 `text2image_*` 工具。调用时 `line` 固定为 `finance` |
| MatrixMedia MCP | 按账号组「心灵鸡汤」逐个发 |
| `core/tools`、`core/capabilities` | TTS、生图、出片、话题去重、后台任务、清目录、BGM、片头 |

财经私有配置在 `workflows/finance/`：`line.py` 导出画风、BGM、音色、账号组、写稿 Prompt、范文和人物参考图。封面由共用 `core.tools.cover.generate_cover` 刻字。

## 目录与数据

- 统一库：`data/media_factory.sqlite3`（话题历史、后台任务 `workflow_jobs`、财经图库 `image_library`）
- 图库文件：`data/image_library/finance/`
- 一次生产：`data/finance/runs/{run_id}/cache/`、`outputs/`
- 清缓存只删这棵 `runs/{run_id}`，不改话题库

## 确认门禁（三处）

1. **稿件**：`text2image_save_draft` 之后必须把话题、正文、长标题、短标题、四个标签完整展示给用户。未确认不得做 TTS/分镜/图/视频。
2. **成片**：`text2image_finish_video` 完成后 `status` 为 `awaiting_publish_confirmation`。未确认不得调矩媒。
3. **清缓存**：发布结束后用户明确确认才调用 `text2image_clear_run(line="finance", run_id, confirmed=true)`。

## Agent 步骤

制作阶段只调 `text2image_*`，且 `line` 始终为 `finance`。不要问画风、BGM、声音。发布阶段改调 MatrixMedia。

1. `text2image_get_draft_context(line="finance")`
2. `text2image_save_draft(line="finance", ...)` → 停，等稿件确认
3. `text2image_prepare_storyboard` → `job_id` → `text2image_wait_task`
4. 按 `result.storyboard_prompt` 写分镜
5. `text2image_prepare_images`（从图库抽图：本期不重复，并按历史均分冷却）→ `text2image_submit_images` → `text2image_wait_task`
6. `text2image_finish_video` → `text2image_wait_task`
7. 展示成片；确认后按 `result.matrixmedia_account_group`（心灵鸡汤）发布
8. 再确认后 `text2image_clear_run(line="finance", ...)`

## 画面与音频（本线固定）

画面：从财经图库按分镜匹配后抽取，同一期不重复；按历史选用冷却，长期尽量均分。镜头图禁止可读文字。封面出片时刻字。

音频：旁白倍速 `+20%`，BGM 为电影感励志钢琴，增益 `0.28`，混合 `0.85`，淡入 1 秒、淡出 2 秒。Agent 不得改这些值。
