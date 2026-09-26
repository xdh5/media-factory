---
name: learn-chinese-and-korean
description: 使用语言学习 MCP 制作中英/韩英词汇短视频；适用于“做语言学习视频”“中韩学习视频”等请求。
---

# 语言学习视频

MCP 入口：`python -m core.mcp.language_learning`。**语言学习 MCP 是 Prompt、TTS、停顿、成片格式、发布账号组、平台和自动排期参数的唯一真源**；本 Skill 只描述交互门禁与完整流程。禁止绕过 MCP 或直接读写内部文件。

开始交互式生产前，必须先让用户明确这期视频的北京时间计划发布日期 `publish_date`。用户没说清是哪一天时必须先追问；禁止默认今天、禁止占用话题或创建 run，也禁止在日期不明确时生成成片并写入 `production_outputs`。

## 固定参数

开始生产时先调用 `language_learning_get_production_config(topic, learning_modes)`；Agent 与 GitHub Action 都必须原样复用返回值，禁止在各自入口维护参数副本。

### 语言方向

- `en-zh`：中英学习
- `en-ko`：韩英学习

### TTS 与配音停顿

分别使用 MCP 返回的 `voices`、`language_pause` 与 `word_pause`，Skill 不保留副本。

### 标题、文件名与描述

成片本地文件名必须与发布标题一致（经 `safe_filename` 后保存为 `.mp4`）。

**中文 `en-zh`**

- 标题与文件名：`10 Essential {Topic} Words in Chinese`
- 示例：主题 `Dishes` → `10 Essential Dishes Words in Chinese`
- 问答版也用同一标题，不得加 `guess` 或其它后缀
- 仅原版分段超过 1 段时在末尾加 ` 1/2`、` 2/2`
- **作品描述只发 hashtag，不得加入短标题、完整标题或其它正文**，例如 `#learnchinese #chinesevocabulary #mandarinchinese #dailychinese`

**韩语 `en-ko`**

- 标题与文件名：`韩语｜{该段第一个中文词}的韩语怎么说？`
- 示例：`韩语｜饺子的韩语怎么说？`
- 问答版也用同一标题，不得加 `看图猜词` 或其它后缀
- 仅原版分段超过 1 段时在末尾加 ` 1/2`、` 2/2`
- **作品描述只发 hashtag，不得加入短标题、完整标题或其它正文**，例如 `#学韩语 #韩语单词 #韩语入门 #每日韩语`

### 发布配置（`language_learning_start_create_videos` 的 `publish_config`）

完整配置使用 MCP 返回的 `publish_config`，以下仅描述平台行为，不维护参数副本。

**中文 `en-zh`**

- YouTube 使用项目共用的 `YOUTUBE_OAUTH_CLIENT_ID`、`YOUTUBE_OAUTH_CLIENT_SECRET`，并使用 `.env` 里按频道隔离的 `LANGUAGE_LEARNING_YOUTUBE_*`（`youtube_account` 即账号前缀）
- 多平台发布时间不一致时，给 `language_learning_start_publish` 传 `publish_at_by_target`，键为 `youtube`、`tiktok`、`instagram`、`facebook`，值为带时区的 ISO 8601；值为 `null` 表示立即发布。例如 YouTube、TikTok 在北京时间 16:00 发布而 Meta 立即发布：`{"youtube":"2026-08-24T16:00:00+08:00","tiktok":"2026-08-24T16:00:00+08:00","instagram":null,"facebook":null}`。四个平台同一时间时可继续使用兼容参数 `publish_at`。
- TikTok 通过 Zernio 发布中文成片，使用共用的 `ZERNIO_API_KEY` 与 `LANGUAGE_LEARNING_TIKTOK_*`；本地发布前按需上传该发布资产，GitHub Workflow 使用已经交付 R2 的地址
- Instagram 通过 Zernio 发布中文成片，使用 Meta 专用的 `zernio_api_key_meta`；本地发布前按需上传该发布资产，GitHub Workflow 使用已经交付 R2 的地址。Zernio 只有一个健康 Instagram 账号时自动选择；连接多个账号时必须在 `.env` 配置 `LANGUAGE_LEARNING_INSTAGRAM_ACCOUNT_ID`。只发指定分段时，传 `targets=["instagram"]` 与 `video_parts=[1]` 或 `[2]`。
- Facebook 通过 Zernio 发布中文成片，使用 Meta 专用的 `zernio_api_key_meta`；本地发布前按需上传该发布资产，GitHub Workflow 使用已经交付 R2 的地址。Zernio 只有一个健康 Facebook Page 时自动选择；连接多个 Page 时必须在 `.env` 配置 `LANGUAGE_LEARNING_FACEBOOK_ACCOUNT_ID`。只发指定分段时，传 `targets=["facebook"]` 与 `video_parts=[1]` 或 `[2]`。
- YouTube、TikTok、Instagram、Facebook 的作品描述都只传标签 hashtag；不得把 `short_title`、完整标题或其它文字放进描述。
- 展示给用户看的账号组名为 `中文`；账号配置由 YouTube 与 Zernio 的环境变量提供，不再从 D1 读取发布账号组。官方平台发布成功或预约成功后由语言学习 MCP 自动写入发布记录。

**韩语 `en-ko`**

- 本地生产完成后保留本地产物，不自动上传 R2；只有 GitHub Workflow 或已确认发布的平台需要公网视频地址时才调用 `language_learning_start_upload_r2`
- 发布服务器 MatrixMedia 使用账号组 `韩语`，账号配置由发布环境提供，不再从 D1 读取发布账号组。
- MatrixMedia 发布所有平台时必须传 `creativeStatement="ai_generated"`，给成片添加各平台对应的 AI 生成内容标记；不得省略或改为无标注。
- MatrixMedia 发布时完整标题传 `title`（`韩语｜饺子的韩语怎么说？` 这种格式），作品描述只传标签 hashtag；不得把短标题、完整标题或其它文字放进描述。
- 跳过掘金、番茄
- MatrixMedia 返回成功或预约成功结果后，必须调用 `language_learning_record_publications`。最终平台按 `ks→kuaishou`、`dy→douyin`、`bjh→baijiahao`、`xhs→xiaohongshu`、`tt→toutiao`、`sph→wechat_channels` 映射；立即发布的 `publish_at` 写实际成功时间，预约发布写预约时间，均使用带时区的 ISO 8601。

## Prompt

词表与主体图 Prompt 由 MCP 工具返回，不要自行改写模板结构：

- `language_learning_build_vocabulary_prompt` → `user_prompt`
- `language_learning_prepare_images` 内部根据词表生成主体图 Prompt；必须优先生成带真实 Alpha 通道的透明背景 PNG，只有当前生图能力无法生成透明图时才允许用与全部主体反差明显的单一纯色背景抠图兜底。主体必须是具有自然多色、材质细节和内部明暗的精致全彩插画，禁止单色染色、线稿图标、白色剪影、UI 符号和廉价塑料感；地点、服务、动作等词允许用紧凑小场景表达。主体外部禁止投影、光晕和杂色边缘。禁止把本期目标英语词或其翻译写进图中；与目标词无关的自然场景文字可以保留，仍禁止水印

TOPIC 必须是一个不含空格的英文单词。词表固定执行最近 100 天去重：每期 10 个英语单词中，至少 5 个必须未在最近 100 天使用。`build_vocabulary_prompt` 会把历史词库写进 `user_prompt`，`parse_vocabulary_response` 只校验、不写库；用户触发发布后才把话题与全部 10 个单词正式写入 D1。

无论单独生成韩语还是同时生成中英、韩英，韩语罗马音都必须与韩文音节逐一对应，并使用英文半角连字符 `-` 分隔；解析器必须硬校验，不能只依赖 Prompt。

### 可复用预制词包

任意宿主 Agent 要提前补充词包时，必须调用 `language_learning_prepare_pack(topic)`，按返回的 `vocabulary_prompt` 生成词表后调用 `language_learning_validate_pack_words`。该工具会返回唯一的 `subject_sheet_prompt`：Agent 只生成**一张**按上五下五排列、含十个主体的真实 Alpha 透明 PNG，不能拆成十张图，也不能使用纯色背景抠图。随后调用 `language_learning_commit_pack(pack_id, topic, words, subject_sheet_path)` 上传并写入词包库。

GitHub Action 仅调用 `language_learning_claim_pack(publish_date)` 领取现成词包，下载该主题图后复用 MCP 的视觉定位、透明图校验和裁切，再拼卡出片；不会再次生成词表或图片。没有已验收词包时，GitHub 生产应明确失败，不能静默降级为重新生图。

## 确认门禁

1. **成片**：本地制作完成后展示 `output/language_learning/run-YYYYMMDD/` 中的成片路径、标题、标签与账号组；`YYYYMMDD` 必须是北京时间计划发布日期。未确认不得调用发布 MCP。本地制作不得在成片阶段自动上传 R2；仅 GitHub Workflow 生产完成后自动交付 R2，本地只有在用户确认发布且目标平台需要公网视频地址时才上传发布资产。本地成片成功后 MCP 自动以 `source=local_mcp` 写入 `production_outputs`；GitHub Workflow 只在 R2 交付成功后以 `source=github_workflow` 写入。查询某天产物使用 `language_learning_get_production_outputs(publish_date)`。
2. **清缓存**：发布结束后用户确认才调用 `language_learning_clear_run(run_id, confirmed=true)`。

`weekly-production` 每周六北京时间 12:00 串行生产下周周一至周日内容，只生产并交付 R2，禁止自动发布语言视频。单独的手动发布 Workflow 按数据库预检结果最多重试 3 次；YouTube 使用官方 API，完整上传或预约并返回 `video_id` 才记为成功，抛错或缺少 `video_id` 记为失败。TikTok、Facebook、Instagram 调用 Zernio；Zernio 请求成功并返回 `post_id` 与成功或预约状态后，立即把标题、发布时间、平台、账号、分段及外部 ID 写入现有 `publication_records`，请求失败则不写入。手动发布 Workflow 只复用 GitHub 已交付 R2 的中文成片，手动 MCP 制作仍执行上述成片确认门禁。生产 Workflow 不清缓存。原每日生产命令保留但不再配置定时调度。

词表、主体图、卡片、出片中间步骤不逐项确认。

## 制作流程

1. `language_learning_get_production_config` 获取唯一标准参数；`language_learning_get_topics` 获取最近主题，再调用 `language_learning_get_topic_generation_prompt`，宿主 Agent 生成后必须交给 `language_learning_validate_topic_response`。
2. 先确定北京时间计划发布日期 `publish_date`（`YYYY-MM-DD`，不得早于当天）；自选单个英文单词主题后调用 `language_learning_occupy_topic(topic, learning_modes, publish_date)`，创建 `output/language_learning/run-YYYYMMDD/` 并拿到 `run_id`，不写 D1。日期只表示计划发布日，不包含具体时间。
3. `language_learning_build_vocabulary_prompt(topic, learning_modes)` 获取包含最近 100 天词库的 Prompt，按原样生成纯文本词表；再调用 `language_learning_parse_vocabulary_response(response_text, learning_modes, topic, run_id)`，由 MCP 强制校验至少 5 个新词，但暂不写库。
4. `language_learning_prepare_images`（无需手写主体图 Prompt）。
5. 宿主生图时：每生成一张立刻 `language_learning_save_images`，再 `language_learning_start_submit_images`（无能力或单张失败 3 次才传 `failures` 走千问兜底生图）→ `language_learning_poll_task`。MCP 不调用千问文本或视觉模型。
6. 调用 `language_learning_get_visual_validation_prompt`，宿主 Agent 按返回的 Prompt 只提取按上排从左到右、下排从左到右排序的十个保守边界框，不检查文字、水印、画风、内容或主体完整性；调用 `language_learning_validate_subject_sheet` 后，透明图直接保留 Alpha 通道并裁出十张主体，纯色兜底图才执行自动抠图，统一保存 `subject-sheet-background-removed.png`。
7. 调用 `language_learning_get_sheet_validation_prompt`，宿主 Agent 必须打开**整张透明处理后的完整主题图**（不是十张单独主体），按返回 Prompt 一次性检查：主体数量是否为 10、完整性、文字、水印、全彩配色与材质质感、语义表达、透明边缘残色；全体单色染色、大片无层次纯色块、线稿图标、白色剪影、UI 符号或廉价塑料感必须按 `style` 判定失败。再调用 `language_learning_review_subject_sheet` 提交一条结论。失败时 `failure_kind` 取 `background_edge` / `text` / `watermark` / `style` / `count` / `completeness` 之一。透明图出现杂色边缘时优先重新生成干净透明图；只有透明生成持续失败时才改用高反差单一纯色背景抠图兜底。主题图最多生成 3 次，第三次仍失败必须报错停止。GitHub Action 没有宿主 Agent 时，由 Runner 对整图调用千问视觉执行同一个 MCP Prompt。
8. `language_learning_start_compose_cards` 分别做 `en-zh` 与 `en-ko`（若本次包含两个方向）→ 各自 poll。卡片内十个主体保持原比例并完整包含在固定图片区域内：横向主体按区域宽度缩放，纵向主体按区域高度缩放，宽高均不得越界，最后水平和垂直居中。
9. `language_learning_start_create_videos`：传入 MCP 配置返回的 `voices`、`publish_config`、`language_pause`、`word_pause` 和 `video_formats`；倒计时音轨使用 MCP 默认值，不必传 `countdown_audio_path` → poll 至 `done=true`。
10. 用户确认发布后：韩语原版与问答版一起交给 MatrixMedia；中文调用 `language_learning_start_publish`，原版两段和问答版一条一起发到 YouTube、TikTok、Instagram、Facebook。问答版标题与原版同一套格式，不得加 `guess` 或 `看图猜词`。目标平台需要公网视频地址时，才调用 `language_learning_start_upload_r2` 上传发布资产。发布 MCP 幂等写入正式话题与本期 10 个单词。
11. 展示发布结果后，确认清缓存。

### 后台任务轮询

- 耗时步骤禁止同步调用 `submit_images`（含千问）、`compose_cards`、`create_videos`、`publish`。
- `start` 立即返回 `task_path`；每 15～30 秒调用 `language_learning_poll_task(task_path)`。
- `status=running` 继续等；`succeeded` 读 `result`；`failed` 读 `error` 并停止。
- 客户端报 MCP 超时后**不要重复 start**，继续 poll 同一 `task_path`。

## MCP 工具一览

| 工具 | 作用 |
| --- | --- |
| `language_learning_get_production_config` | 返回 Agent 与 GitHub Runner 共用的全部固定生产和自动发布参数 |
| `language_learning_get_automation_plan` | 返回每周生产与补齐发布的统一预检结果 |
| `language_learning_get_publish_schedule` | 返回 MCP 统一维护的自动发布平台和北京时间预约时间 |
| `language_learning_get_topic_generation_prompt` / `language_learning_validate_topic_response` | 共用主题生成 Prompt 与校验 |
| `language_learning_get_topics` | 查已占用主题和最近 100 天单词 |
| `language_learning_get_production_outputs` | 按北京时间计划发布日期查询语言学习成片并区分本地与 GitHub 来源 |
| `language_learning_occupy_topic` | 占坑并创建 run |
| `language_learning_build_vocabulary_prompt` | 返回包含最近词库的词表 Prompt |
| `language_learning_parse_vocabulary_response` | 解析词表、校验至少一半新词，发布前不写历史 |
| `language_learning_prepare_pack` / `language_learning_validate_pack_words` | 为可复用词包返回词表 Prompt，并校验词表及返回一张十元素透明主题图 Prompt |
| `language_learning_commit_pack` / `language_learning_claim_pack` | 上传一张主题图写入词包库，或由 GitHub 按日期领取一个词包 |
| `language_learning_prepare_images` | 注册主体图任务 |
| `language_learning_save_images` | 写入已生成图 |
| `language_learning_submit_images` | 提交主体图（同步，勿用） |
| `language_learning_start_submit_images` | 启动主体图提交（可选千问兜底生图） |
| `language_learning_get_visual_validation_prompt` | 返回宿主 Agent 定位十个主体框的 Prompt |
| `language_learning_get_sheet_validation_prompt` | 返回宿主 Agent 检查整张去背景主题图的 Prompt |
| `language_learning_validate_subject_sheet` | 接收十个框、整图去背景并裁出十张抠图 |
| `language_learning_review_subject_sheet` | 接收宿主 Agent 对整张去背景主题图的一条验收结论 |
| `language_learning_compose_cards` | 拼单词卡（同步，勿用） |
| `language_learning_start_compose_cards` | 启动拼卡后台任务 |
| `language_learning_create_videos` | 出片（同步，勿用） |
| `language_learning_start_create_videos` | 启动出片后台任务 |
| `language_learning_start_upload_r2` | 后台上传成片、主题图和发布清单到 R2 |
| `language_learning_start_publish` | 后台发布中文 YouTube、TikTok、Instagram 或 Facebook，并写入内容历史 |
| `language_learning_poll_task` | 轮询后台任务 |
| `language_learning_clear_run` | 清本次目录 |
