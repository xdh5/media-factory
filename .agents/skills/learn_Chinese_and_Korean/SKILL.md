---
name: learn-chinese-and-korean
description: 使用语言学习 MCP 制作中英/韩英词汇短视频；适用于“做语言学习视频”“中韩学习视频”等请求。
---

# 语言学习视频

MCP 入口：`python -m core.mcp.language_learning`。MCP 负责编排与 Prompt；**本 Skill 提供 TTS 音色、发布账号组与完整流程**。禁止绕过 MCP 或直接读写内部文件。

开始交互式生产前，必须先让用户明确这期视频的北京时间计划发布日期 `publish_date`。用户没说清是哪一天时必须先追问；禁止默认今天、禁止占用话题或创建 run，也禁止在日期不明确时生成成片并写入 `production_outputs`。

## 固定参数（调用 MCP 时必须按此传）

### 语言方向

- `en-zh`：中英学习
- `en-ko`：韩英学习

### TTS 音色（`language_learning_start_create_videos` 的 `voices`）

| 键 | Edge 音色 | 用途 |
| --- | --- | --- |
| `en` | `en-US-AriaNeural` | 每个词的英语读音 |
| `zh` | `zh-CN-XiaoxiaoNeural` | 中文学习片的目标语 |
| `ko` | `ko-KR-SunHiNeural` | 韩语学习片的目标语 |

### 配音停顿（默认，除非用户明确要求修改）

- `language_pause`：`0.3`（英语与目标语之间）
- `word_pause`：`0.3`（每个词之间）

### 发布配置（`language_learning_start_create_videos` 的 `publish_config`）

**中文 `en-zh`**

```json
{
  "account_group": "中文",
  "youtube_account": "language_learning",
  "tags": ["#learnchinese", "#chinesevocabulary", "#mandarinchinese", "#dailychinese"],
  "short_title": "中文{topic}怎么说"
}
```

- YouTube 使用项目共用的 `YOUTUBE_OAUTH_CLIENT_ID`、`YOUTUBE_OAUTH_CLIENT_SECRET`，并使用 `.env` 里按频道隔离的 `LANGUAGE_LEARNING_YOUTUBE_*`（`youtube_account` 即账号前缀）
- 多平台发布时间不一致时，给 `language_learning_start_publish` 传 `publish_at_by_target`，键为 `youtube`、`tiktok`、`instagram`、`facebook`，值为带时区的 ISO 8601；值为 `null` 表示立即发布。例如 YouTube、TikTok 在北京时间 16:00 发布而 Meta 立即发布：`{"youtube":"2026-08-24T16:00:00+08:00","tiktok":"2026-08-24T16:00:00+08:00","instagram":null,"facebook":null}`。四个平台同一时间时可继续使用兼容参数 `publish_at`。
- TikTok 通过 Zernio 发布中文成片，使用共用的 `ZERNIO_API_KEY` 与 `LANGUAGE_LEARNING_TIKTOK_*`；本地发布前按需上传该发布资产，GitHub Workflow 使用已经交付 R2 的地址
- Instagram 通过 Zernio 发布中文成片，使用 Meta 专用的 `zernio_api_key_meta`；本地发布前按需上传该发布资产，GitHub Workflow 使用已经交付 R2 的地址。Zernio 只有一个健康 Instagram 账号时自动选择；连接多个账号时必须在 `.env` 配置 `LANGUAGE_LEARNING_INSTAGRAM_ACCOUNT_ID`。只发指定分段时，传 `targets=["instagram"]` 与 `video_parts=[1]` 或 `[2]`。
- Facebook 通过 Zernio 发布中文成片，使用 Meta 专用的 `zernio_api_key_meta`；本地发布前按需上传该发布资产，GitHub Workflow 使用已经交付 R2 的地址。Zernio 只有一个健康 Facebook Page 时自动选择；连接多个 Page 时必须在 `.env` 配置 `LANGUAGE_LEARNING_FACEBOOK_ACCOUNT_ID`。只发指定分段时，传 `targets=["facebook"]` 与 `video_parts=[1]` 或 `[2]`。
- 展示给用户看的账号组名为 `中文`；账号配置由 YouTube 与 Zernio 的环境变量提供，不再从 D1 读取发布账号组。官方平台发布成功或预约成功后由语言学习 MCP 自动写入发布记录。

**韩语 `en-ko`**

```json
{
  "account_group": "韩语",
  "tags": ["#学韩语", "#韩语单词", "#韩语入门", "#每日韩语"],
  "short_title": "韩语单词怎么说",
  "platforms": ["dy", "ks", "bjh", "xhs", "tt", "sph"]
}
```

- 本地生产完成后保留本地产物，不自动上传 R2；只有 GitHub Workflow 或已确认发布的平台需要公网视频地址时才调用 `language_learning_start_upload_r2`
- 发布服务器 MatrixMedia 使用账号组 `韩语`，账号配置由发布环境提供，不再从 D1 读取发布账号组。
- MatrixMedia 发布所有平台时必须传 `creativeStatement="ai_generated"`，给成片添加各平台对应的 AI 生成内容标记；不得省略或改为无标注。
- 跳过掘金、番茄
- MatrixMedia 返回成功或预约成功结果后，必须调用 `language_learning_record_publications`。最终平台按 `ks→kuaishou`、`dy→douyin`、`bjh→baijiahao`、`xhs→xiaohongshu`、`tt→toutiao`、`sph→wechat_channels` 映射；立即发布的 `publish_at` 写实际成功时间，预约发布写预约时间，均使用带时区的 ISO 8601。

## Prompt

词表与主体图 Prompt 由 MCP 工具返回，不要自行改写模板结构：

- `language_learning_build_vocabulary_prompt` → `user_prompt`
- `language_learning_prepare_images` 内部根据词表生成主体图 Prompt；Prompt 要求自行选择与全部主体反差明显的单一纯色背景、禁止阴影，并明确禁止生成任何文字、标签、数字、网格线和水印

TOPIC 必须是一个不含空格的英文单词。词表固定执行最近 100 天去重：每期 10 个英语单词中，至少 5 个必须未在最近 100 天使用。`build_vocabulary_prompt` 会把历史词库写进 `user_prompt`，`parse_vocabulary_response` 只校验、不写库；用户触发发布后才把话题与全部 10 个单词正式写入 D1。

无论单独生成韩语还是同时生成中英、韩英，韩语罗马音都必须与韩文音节逐一对应，并使用英文半角连字符 `-` 分隔；解析器必须硬校验，不能只依赖 Prompt。

## 确认门禁

1. **成片**：本地制作完成后展示 `output/language_learning/run-YYYYMMDD/` 中的成片路径、标题、标签与账号组；`YYYYMMDD` 必须是北京时间计划发布日期。未确认不得调用发布 MCP。本地制作不得在成片阶段自动上传 R2；仅 GitHub Workflow 生产完成后自动交付 R2，本地只有在用户确认发布且目标平台需要公网视频地址时才上传发布资产。本地成片成功后 MCP 自动以 `source=local_mcp` 写入 `production_outputs`；GitHub Workflow 只在 R2 交付成功后以 `source=github_workflow` 写入。查询某天产物使用 `language_learning_get_production_outputs(publish_date)`。
2. **清缓存**：发布结束后用户确认才调用 `language_learning_clear_run(run_id, confirmed=true)`。

用户明确启用的自动 Workflow 属于持续发布授权：`weekly-production` 每周五北京时间 12:00 串行生产下周周一至周日内容，语言生产完成后自动四平台预约发布；单独的手动发布 Workflow 仅用于补发或重试。发布 Workflow 只复用 GitHub 已交付 R2 的中文成片，通过 YouTube 官方 API 和 Zernio 排期到计划发布日期北京时间 16:00，并按 D1 记录只补发尚未发布的平台，无需逐日再次确认；手动 MCP 制作仍执行上述成片确认门禁。自动 Workflow 不清缓存。

词表、主体图、卡片、出片中间步骤不逐项确认。

## 制作流程

1. `language_learning_get_topics`：避开近 30 天重复主题。
2. 先确定北京时间计划发布日期 `publish_date`（`YYYY-MM-DD`，不得早于当天）；自选单个英文单词主题后调用 `language_learning_occupy_topic(topic, learning_modes, publish_date)`，创建 `output/language_learning/run-YYYYMMDD/` 并拿到 `run_id`，不写 D1。日期只表示计划发布日，不包含具体时间。
3. `language_learning_build_vocabulary_prompt(topic, learning_modes)` 获取包含最近 100 天词库的 Prompt，按原样生成纯文本词表；再调用 `language_learning_parse_vocabulary_response(response_text, learning_modes, topic, run_id)`，由 MCP 强制校验至少 5 个新词，但暂不写库。
4. `language_learning_prepare_images`（无需手写主体图 Prompt）。
5. 宿主生图时：每生成一张立刻 `language_learning_save_images`，再 `language_learning_start_submit_images`（无能力或单张失败 3 次才传 `failures` 走千问兜底生图）→ `language_learning_poll_task`。MCP 不调用千问文本或视觉模型。
6. 调用 `language_learning_get_visual_validation_prompt`，宿主 Agent 按返回的 Prompt 只提取按上排从左到右、下排从左到右排序的十个保守边界框，不检查文字、水印、画风、内容或主体完整性；调用 `language_learning_validate_subject_sheet` 后，Python 整图去背景、输出十张抠图，并保存 `subject-sheet-background-removed.png`。
7. 调用 `language_learning_get_sheet_validation_prompt`，宿主 Agent 必须打开**整张去背景后的完整主题图**（不是十张单独抠图），按返回 Prompt 一次性检查：主体数量是否为 10、完整性、文字、水印、画风、背景残色；再调用 `language_learning_review_subject_sheet` 提交一条结论。失败时 `failure_kind` 取 `background_edge` / `text` / `watermark` / `style` / `count` / `completeness` 之一。背景残色时必须要求换一种与上一张明显不同、且与全部主体反差更大的纯色背景重新生成主题图。主题图最多生成 3 次，第三次仍失败必须报错停止。GitHub Action 没有宿主 Agent 时，由 Runner 对整图调用千问视觉执行同一个 MCP Prompt。
8. `language_learning_start_compose_cards` 分别做 `en-zh` 与 `en-ko`（若本次包含两个方向）→ 各自 poll。卡片内十个主体保持原比例并完整包含在固定图片区域内：横向主体按区域宽度缩放，纵向主体按区域高度缩放，宽高均不得越界，最后水平和垂直居中。
9. `language_learning_start_create_videos`：传入本 Skill 的 `voices`、`publish_config`、`language_pause`、`word_pause` → poll 至 `done=true`。
10. 用户确认发布后：韩语条目直接使用本地产物交给 MatrixMedia MCP，并对每个平台传入条目中的 `creativeStatement="ai_generated"`；中文调用 `language_learning_start_publish`，默认发布 YouTube 和 TikTok，也可用 `targets` 显式发布 Instagram 或 Facebook。目标平台需要公网视频地址时，才调用 `language_learning_start_upload_r2` 上传发布资产。发布 MCP 幂等写入正式话题与本期 10 个单词。
9. 展示发布结果后，确认清缓存。

### 后台任务轮询

- 耗时步骤禁止同步调用 `submit_images`（含千问）、`compose_cards`、`create_videos`、`publish`。
- `start` 立即返回 `task_path`；每 15～30 秒调用 `language_learning_poll_task(task_path)`。
- `status=running` 继续等；`succeeded` 读 `result`；`failed` 读 `error` 并停止。
- 客户端报 MCP 超时后**不要重复 start**，继续 poll 同一 `task_path`。

## MCP 工具一览

| 工具 | 作用 |
| --- | --- |
| `language_learning_get_topics` | 查已占用主题和最近 100 天单词 |
| `language_learning_get_production_outputs` | 按北京时间计划发布日期查询语言学习成片并区分本地与 GitHub 来源 |
| `language_learning_occupy_topic` | 占坑并创建 run |
| `language_learning_build_vocabulary_prompt` | 返回包含最近词库的词表 Prompt |
| `language_learning_parse_vocabulary_response` | 解析词表、校验至少一半新词，发布前不写历史 |
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
