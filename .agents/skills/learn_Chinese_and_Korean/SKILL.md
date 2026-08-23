---
name: learn-chinese-and-korean
description: 使用语言学习 MCP 制作中英/韩英词汇短视频；适用于“做语言学习视频”“中韩学习视频”等请求。
---

# 语言学习视频

MCP 入口：`python -m core.mcp.language_learning`。MCP 负责编排与 Prompt；**本 Skill 提供 TTS 音色、发布账号组与完整流程**。禁止绕过 MCP 或直接读写内部文件。

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
- YouTube 定时发布时，给 `language_learning_start_publish` 传带时区的 ISO 8601 `publish_at`，例如北京时间 `2026-08-23T16:00:00+08:00`。视频会提前上传为私密并由 YouTube 到点公开；不传则保持立即公开。
- TikTok 通过 Zernio 发布生产阶段已经上传 R2 的中文成片，使用共用的 `ZERNIO_API_KEY` 与 `LANGUAGE_LEARNING_TIKTOK_*`
- Instagram 使用 Graph API 和 R2 公网成片；只发指定分段时，给 `language_learning_start_publish` 传 `targets=["instagram"]` 与 `video_parts=[1]` 或 `[2]`。
- 展示给用户看的账号组名：`中文`；成员从 Cloudflare D1 的发布账号组读取，当前包含 YouTube `language_learning` 与 Meta `daily-chinese-learning` 交叉发布入口。

**韩语 `en-ko`**

```json
{
  "account_group": "韩语",
  "tags": ["#学韩语", "#韩语单词", "#韩语入门", "#每日韩语"],
  "short_title": "韩语单词怎么说",
  "platforms": ["dy", "ks", "blbl", "bjh", "tt", "sph"]
}
```

- 生产完成后调用 `language_learning_start_upload_r2` 上传 R2
- 发布路由账号组为 `韩语`；从 Cloudflare D1 解析到发布服务器 MatrixMedia 同名账号组 `韩语`。
- 跳过掘金、番茄、小红书

## Prompt

词表与主体图 Prompt 由 MCP 工具返回，不要自行改写模板结构：

- `language_learning_build_vocabulary_prompt` → `user_prompt`
- `language_learning_prepare_images` 内部根据词表生成主体图 Prompt；Prompt 要求自行选择与全部主体反差明显的单一纯色背景、禁止阴影，并明确禁止生成任何文字、标签、数字、网格线和水印

TOPIC 必须是一个不含空格的英文单词。词表固定执行最近 100 天去重：每期 10 个英语单词中，至少 5 个必须未在最近 100 天使用。`build_vocabulary_prompt` 会把历史词库写进 `user_prompt`，`parse_vocabulary_response` 只校验、不写库；用户触发发布后才把话题与全部 10 个单词正式写入 D1。

无论单独生成韩语还是同时生成中英、韩英，韩语罗马音都必须与韩文音节逐一对应，并使用英文半角连字符 `-` 分隔；解析器必须硬校验，不能只依赖 Prompt。

## 确认门禁

1. **成片**：`language_learning_start_create_videos` 与 `language_learning_start_upload_r2` 轮询完成后展示成片路径、标题、标签、账号组与 R2 清单 URL；未确认不得调用发布 MCP。
2. **清缓存**：发布结束后用户确认才调用 `language_learning_clear_run(run_id, confirmed=true)`。

词表、主体图、卡片、出片中间步骤不逐项确认。

## 制作流程

1. `language_learning_get_topics`：避开近 30 天重复主题。
2. 自选单个英文单词主题后 `language_learning_occupy_topic(topic, learning_modes)`，只创建本次生产目录并拿到 `run_id`，不写 D1。
3. `language_learning_build_vocabulary_prompt(topic, learning_modes)` 获取包含最近 100 天词库的 Prompt，按原样生成纯文本词表；再调用 `language_learning_parse_vocabulary_response(response_text, learning_modes, topic, run_id)`，由 MCP 强制校验至少 5 个新词，但暂不写库。
4. `language_learning_prepare_images`（无需手写主体图 Prompt）。
5. 宿主生图时：每生成一张立刻 `language_learning_save_images`，再 `language_learning_start_submit_images`（无能力或单张失败 3 次才传 `failures` 走千问兜底生图）→ `language_learning_poll_task`。MCP 不调用千问文本或视觉模型。
6. 调用 `language_learning_get_visual_validation_prompt`，宿主 Agent 按返回的 Prompt 亲自检查主题图是否恰好十个主体、上排五个、下排五个且无文字，并返回按上排从左到右、下排从左到右排序的十个保守边界框；调用 `language_learning_validate_subject_sheet` 后，Python 去背景并输出十张抠图。
7. 宿主 Agent 必须打开十张抠图逐张检查，再调用 `language_learning_review_cutouts` 提交十条结论。第一次仅裁剪框有问题时调整完整十框并重新调用 `language_learning_validate_subject_sheet`；第二次仍抠坏，或源图本身残缺、重叠、被背景色吃掉时，调用 `language_learning_prepare_images` 重新生主题图。主题图最多生成 3 次，第三次仍失败必须报错停止。未通过逐张检查时禁止拼卡。
8. `language_learning_start_compose_cards` 分别做 `en-zh` 与 `en-ko`（若本次包含两个方向）→ 各自 poll。卡片内十个主体保持原比例并完整包含在固定图片区域内：横向主体按区域宽度缩放，纵向主体按区域高度缩放，宽高均不得越界，最后水平和垂直居中。
9. `language_learning_start_create_videos`：传入本 Skill 的 `voices`、`publish_config`、`language_pause`、`word_pause` → poll 至 `done=true`。
10. `language_learning_start_upload_r2` 上传成片、主题图和本地发布清单 → poll 至 `done=true`，保留返回的 `manifest_url` 与 `subject_sheet_url`。
11. 用户确认发布后：韩语条目交给发布服务器上的 MatrixMedia MCP；中文调用 `language_learning_start_publish` 发布 YouTube 和 TikTok。发布 MCP 幂等写入正式话题与本期 10 个单词。
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
| `language_learning_occupy_topic` | 占坑并创建 run |
| `language_learning_build_vocabulary_prompt` | 返回包含最近词库的词表 Prompt |
| `language_learning_parse_vocabulary_response` | 解析词表、校验至少一半新词，发布前不写历史 |
| `language_learning_prepare_images` | 注册主体图任务 |
| `language_learning_save_images` | 写入已生成图 |
| `language_learning_submit_images` | 提交主体图（同步，勿用） |
| `language_learning_start_submit_images` | 启动主体图提交（可选千问兜底生图） |
| `language_learning_get_visual_validation_prompt` | 返回宿主 Agent 的主题图验收 Prompt |
| `language_learning_validate_subject_sheet` | 接收宿主 Agent 的十个框并抠图 |
| `language_learning_review_cutouts` | 接收宿主 Agent 对十张抠图的逐张检查 |
| `language_learning_compose_cards` | 拼单词卡（同步，勿用） |
| `language_learning_start_compose_cards` | 启动拼卡后台任务 |
| `language_learning_create_videos` | 出片（同步，勿用） |
| `language_learning_start_create_videos` | 启动出片后台任务 |
| `language_learning_start_upload_r2` | 后台上传成片、主题图和发布清单到 R2 |
| `language_learning_publish` | 兼容旧客户端的同步发布入口 |
| `language_learning_start_publish` | 后台发布中文 YouTube 和 TikTok，并写入内容历史 |
| `language_learning_poll_task` | 轮询后台任务 |
| `language_learning_clear_run` | 清本次目录 |
