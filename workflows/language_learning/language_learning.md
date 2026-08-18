# 语言学习工作流

中英 / 韩英词汇短视频。MCP 入口是 `python -m workflows.language_learning.index`（Cursor / Trae 配置里的 `args` 必须是 `-m` + `workflows.language_learning.index`）。Agent 只通过 MCP 编排，禁止自行生成主体图或直接读写工作流内部文件。

## 谁干什么

| 层级 | 职责 |
| --- | --- |
| 宿主 Agent | 选题、按 Prompt 写纯文本词表、优先自己生主体图；成片后给用户看标题/标签/账号组；确认后再发；再确认后清缓存 |
| `media-factory-language-learning` MCP | `index.py` 暴露 `language_learning_*` 工具：话题、词表、生图任务、拼卡、出片、YouTube 发布、查任务、清本次生产目录 |
| YouTube 工具 | 中文视频发到账号组「学中文」。韩语视频当前不走这条发布 |
| `core/tools` | 生图、TTS、出片、话题去重、后台任务、清目录 |

语言学习私有代码在 `workflows/language_learning/`：`index.py` 是 MCP 入口，`tools/vocabulary.py` 管 Prompt 与词表解析，`tools/cards.py` 拼固定模板卡片，`tools/video.py` 出片，`tools/publish.py` 写发布清单并上传 YouTube，`job_runner.py` 把后台单派给这些函数。Prompt 和中韩固定模板图也是工作流私有。

## 目录与数据

- 统一库：`data/media_factory.sqlite3`（话题历史、后台任务 `workflow_jobs`）
- 一次生产：`data/language_learning/runs/{run_id}/cache/`（中间产物）、`outputs/`（成品）
- `run_id` 形如 `run-000001`，话题写入后生成
- 清缓存只删这棵 `runs/{run_id}`，不改话题库

## 确认门禁（两处）

1. **成片**：`language_learning_create_videos` 完成后必须向用户展示标题、标签和账号组（中文固定「学中文」）。未确认不得调用 `language_learning_publish`。
2. **清缓存**：发布结束后询问是否删除本次本地文件。用户明确确认后才调用 `language_learning_clear_run(run_id, confirmed=true)`。发布与清缓存不是同一次确认。

词表、主体图、卡片和出片中间步骤不向用户逐项确认。除上述确认外，不询问画风、声音、暂停时长或缓存参数。

## Agent 步骤

全程只调 `language_learning_*`。禁止本地脚本代替 MCP。

1. `language_learning_get_topics`：近 30 天已占用话题。Agent 自选不重复主题。
2. `language_learning_build_vocabulary_prompt`：占用主题并返回词表 Prompt；按原样生成纯文本词表，不要改模板结构。
3. `language_learning_parse_vocabulary_response`：解析词表。格式错误时按返回原因修正后重解析。
4. `language_learning_prepare_images`：返回一张 16:9 透明 2×5 主体图任务。`needs_generation=true` 时由宿主生图，原样使用 `prompt`/`radio`/`size`。无生图能力则 `capability_unavailable=true`、`attempts=0`，交给提交工具走方舟。有生图能力时最多试 3 次。
5. `language_learning_submit_images` → 立刻返回 `job_id`，再用 `language_learning_get_job`。完成后用 `result.subject_sheet_path`。
6. `language_learning_compose_cards` 分别做中文（`en-zh`）和韩文（`en-ko`）卡片，每次都返回 `job_id`，用 `language_learning_get_job` 等到 `completed`。
7. `language_learning_create_videos` → `job_id` → `language_learning_get_job` 到 `completed`。读取成片、标题、标签和账号组。不得因耗时长而重启 MCP 或绕过工具。
8. 向用户展示后停。确认发布后 `language_learning_publish(manifest_path, publish_confirmed=true)` → `job_id` → `language_learning_get_job`。中文固定发 YouTube「学中文」。
9. 展示发布结果后，再问是否删本地文件；确认后 `language_learning_clear_run`。

## 后台任务

`language_learning_submit_images`、`language_learning_compose_cards`、`language_learning_create_videos`、`language_learning_publish` 经共用 `enqueue_job` 提交，独立进程执行（`handler` 为 `workflows.language_learning.job_runner:run_job`），MCP 立即返回 `job_id`。查询只用 `language_learning_get_job`。

状态：`queued` → `running` → `completed` / `failed`。运行中约 10 秒心跳。MCP 启动时只把本工作流仍排队或运行中的任务标为中断；已有缓存保留，重提原步骤即可续跑。

## 成片时工具自动做的

主体图切格贴到中韩固定单词卡、双语 TTS、竖版出片、写成片和发布清单。中文标题形如 `10 Essential {Topic} Words in Chinese`，标签为 `#learnchinese` 等四个固定标签。

## 画面与音频（固定）

画面：一张 2×5 透明主体图，再贴到中文/韩文固定模板。不要自己另画卡片底图。

音频：每个词先英语再目标语（中文或韩语），词间与语种间停顿默认 `0.3` 秒。Agent 不得改默认值，除非用户明确要求。
