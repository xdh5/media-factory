# 语言学习 MCP

中英 / 韩英词汇短视频。入口：`python -m mcp_servers.language_learning`。Agent 只通过 MCP 编排，禁止自行生成主体图或直接读写内部文件。这不是文生图业务线，也不放在 `workflows/`。

## 谁干什么

| 层级 | 职责 |
| --- | --- |
| 宿主 Agent | 选题、按 Prompt 写纯文本词表、优先自己生主体图；成片后给用户看成片路径/标题/标签/账号组；确认后再发 YouTube、Facebook/Instagram Reels 与矩媒；再确认后清缓存 |
| `media-factory-language-learning` MCP | `mcp_servers/language_learning` 暴露 `language_learning_*` 工具：话题、词表、生图任务、拼卡、出片、中文发布（YouTube+Reels）、等待任务、查任务、清本次生产目录 |
| YouTube 工具 | 中文视频发到已授权频道 Daily Chinese Learning（`data/youtube/tokens` 下对应 channel_id） |
| Meta Reels 工具 | 同一条中文成片再发 Facebook Page Reels 和 Instagram Reels（`.env` 里的 Page / IG 凭据） |
| MatrixMedia MCP | 韩语视频发到账号组「韩语」：`list_accounts`、`login`、`login_status`、`publish_video` |
| `core/tools` | 生图、TTS、出片、话题去重、后台任务、清目录 |

实现都在 `mcp_servers/language_learning/`：`tools/session.py` 管话题与生图任务，`tools/vocabulary.py` 管 Prompt 与词表解析，`tools/cards.py` 拼固定模板卡片，`tools/video.py` 出片，`tools/publish.py` 写发布清单并把中文发到 YouTube 与 Meta Reels，韩语由 Agent 调矩媒 MCP，`job_runner.py` 把后台单派给这些函数。Prompt 和中韩固定模板图也在本 MCP 包内。

## 目录与数据

- 统一库：`data/media_factory.sqlite3`（话题历史、后台任务 `workflow_jobs`）
- 一次生产：`data/language_learning/runs/{run_id}/cache/`（中间产物）、`outputs/`（成品）；中文和韩语成片成功后都会再拷一份 mp4 到当前用户桌面
- `run_id` 形如 `run-000001`，话题写入后生成
- 清缓存只删这棵 `runs/{run_id}`，不改话题库

## 确认门禁（两处）

1. **成片**：`language_learning_create_videos` 完成后必须向用户展示成片路径、标题、标签和账号组（中文 YouTube「Daily Chinese Learning」、韩语「韩语」），让用户看过成品。未确认不得调用 `language_learning_publish`，也不得调矩媒。
2. **清缓存**：发布结束后询问是否删除本次本地文件。用户明确确认后才调用 `language_learning_clear_run(run_id, confirmed=true)`。发布与清缓存不是同一次确认。

词表、主体图、卡片和出片中间步骤不向用户逐项确认。除上述确认外，不询问画风、声音、暂停时长或缓存参数。

## Agent 步骤

全程制作只调 `language_learning_*`。确认发布后：中文走 `language_learning_publish`，韩语改调 MatrixMedia MCP。禁止本地脚本代替 MCP。

1. `language_learning_get_topics`：近 30 天已占用话题。Agent 自选不重复主题。
2. `language_learning_build_vocabulary_prompt`：占用主题并返回词表 Prompt；按原样生成纯文本词表，不要改模板结构。
3. `language_learning_parse_vocabulary_response`：解析词表。格式错误时按返回原因修正后重解析。
4. `language_learning_prepare_images`：返回一张 16:9 透明 2×5 主体图任务。`needs_generation=true` 时由宿主生图，原样使用 `prompt`/`radio`/`size`。无生图能力则 `capability_unavailable=true`、`attempts=0`，交给提交工具走方舟。有生图能力时最多试 3 次。
5. 生图成功后立刻 `language_learning_save_images` 写入缓存，再 `language_learning_submit_images` → 立刻返回 `job_id`，再用 `language_learning_wait_task`。完成后用 `result.subject_sheet_path`。
6. `language_learning_compose_cards` 分别做中文（`en-zh`）和韩文（`en-ko`）卡片，每次都返回 `job_id`，用 `language_learning_wait_task` 等到 `completed`。
7. `language_learning_create_videos` → `job_id` → `language_learning_wait_task` 到 `completed`。读取成片路径、标题、标签和账号组。不得因耗时长而重启 MCP 或绕过工具。
8. 向用户展示成品后停。确认发布后：有中文则 `language_learning_publish(manifest_path, publish_confirmed=true)` → `job_id` → `language_learning_wait_task`（YouTube + Facebook/Instagram Reels）。有韩语则改调 MatrixMedia：`list_accounts` 筛 `phone` 等于「韩语」；未登录的抖音/视频号先 `login` 把二维码发给用户扫；平台 dy/ks/blbl/bjh/tt/sph，跳过掘金、番茄、小红书。对每个账号、每段韩语视频调用 `publish_video`（`file` 用成片 `output_path`，`title` 用成片标题，`bt2`=`short_title`，`tags` 四个标签拼成串，`phone`=「韩语」）。禁止复制改名为 `publish.mp4`。禁止用本地脚本代替矩媒 MCP。仅有韩语时不要调用 `language_learning_publish`。
9. 展示发布结果后，再问是否删本地文件；确认后 `language_learning_clear_run`。

## 后台任务

`language_learning_submit_images`、`language_learning_compose_cards`、`language_learning_create_videos`、`language_learning_publish` 经共用 `enqueue_job` 提交，独立进程执行（`handler` 为 `mcp_servers.language_learning.job_runner:run_job`），MCP 立即返回 `job_id`。等待终态只用 `language_learning_wait_task`。`language_learning_get_job` 只做不阻塞的瞬时快照。

状态：`queued` → `running` → `completed` / `failed`。运行中约 10 秒心跳。MCP 启动时只把本 MCP 仍排队或运行中的任务标为中断；已有缓存保留，重提原步骤即可续跑。

## 成片时工具自动做的

主体图切格贴到中韩固定单词卡、双语 TTS、竖版出片、写成片和发布清单，并把成品 mp4 拷到桌面。出片只调用公有 `render_shot`（静图+配音）和 `concat_videos`，不走财经那套运镜/字幕/封面/BGM。中文标题形如 `10 Essential {Topic} Words in Chinese`，标签为 `#learnchinese` 等四个固定标签。韩语发矩媒账号组「韩语」，标签为 `#学韩语 #韩语单词 #韩语入门 #每日韩语`。

## 画面与音频（固定）

画面：一张 2×5 透明主体图，再贴到中文/韩文固定模板。不要自己另画卡片底图。

音频：每个词先英语再目标语（中文或韩语），词间与语种间停顿默认 `0.3` 秒，配音使用 Edge 原速且不裁句尾。Agent 不得改默认值，除非用户明确要求。
