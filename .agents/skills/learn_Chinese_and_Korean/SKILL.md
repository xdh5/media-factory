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
  "account_group": "Daily Chinese Learning",
  "youtube_account": "language_learning",
  "tags": ["#learnchinese", "#chinesevocabulary", "#mandarinchinese", "#dailychinese"],
  "short_title": "中文{topic}怎么说"
}
```

- YouTube / Meta Reels 使用 `.env` 里 `LANGUAGE_LEARNING_*`（`youtube_account` 即账号前缀）
- Meta 只能复用生产 Workflow 已写入发布清单的 R2 公网 `video_url`；缺少 URL 必须报错，禁止本地直传或在发布阶段重复上传 R2
- 展示给用户看的账号组名：`Daily Chinese Learning`

**韩语 `en-ko`**

```json
{
  "account_group": "韩语",
  "tags": ["#学韩语", "#韩语单词", "#韩语入门", "#每日韩语"],
  "short_title": "韩语单词怎么说",
  "platforms": ["dy", "ks", "blbl", "bjh", "tt", "sph"]
}
```

- 生产完成后上传 R2；所有平台发布只能触发 GitHub 的“阿里云发布 R2 成片”Workflow
- 阿里云发布机上的独立 MatrixMedia 使用账号组 `韩语`
- 跳过掘金、番茄、小红书

## Prompt

词表与主体图 Prompt 由 MCP 工具返回，不要自行改写模板结构：

- `language_learning_build_vocabulary_prompt` → `user_prompt`
- `language_learning_prepare_images` 内部根据词表生成主体图 Prompt

TOPIC 必须是一个不含空格的英文单词。词表固定执行最近 100 天去重：每期 10 个英语单词中，至少 5 个必须未在最近 100 天使用。`build_vocabulary_prompt` 会把历史词库写进 `user_prompt`，`parse_vocabulary_response` 只校验、不写库；用户触发发布后才把话题与全部 10 个单词正式写入 D1。

## 确认门禁

1. **成片**：`language_learning_start_create_videos` 轮询完成后展示成片路径、标题、标签、账号组与 R2 清单 URL；未确认不得触发阿里云发布 Workflow。
2. **清缓存**：发布结束后用户确认才调用 `language_learning_clear_run(run_id, confirmed=true)`。

词表、主体图、卡片、出片中间步骤不逐项确认。

## 制作流程

1. `language_learning_get_topics`：避开近 30 天重复主题。
2. 自选单个英文单词主题后 `language_learning_occupy_topic(topic, learning_modes)`，只创建本次生产目录并拿到 `run_id`，不写 D1。
3. `language_learning_build_vocabulary_prompt(topic, learning_modes)` 获取包含最近 100 天词库的 Prompt，按原样生成纯文本词表；再调用 `language_learning_parse_vocabulary_response(response_text, learning_modes, topic, run_id)`，由 MCP 强制校验至少 5 个新词，但暂不写库。
4. `language_learning_prepare_images`（无需手写主体图 Prompt）。
5. 宿主生图时：每生成一张立刻 `language_learning_save_images`，再 `language_learning_start_submit_images`（无能力或单张失败 3 次才传 `failures` 走方舟）→ `language_learning_poll_task`。
6. `language_learning_start_compose_cards` 分别做 `en-zh` 与 `en-ko`（若本次包含两个方向）→ 各自 poll。
7. `language_learning_start_create_videos`：传入本 Skill 的 `voices`、`publish_config`、`language_pause`、`word_pause` → poll 至 `done=true`。GitHub Action 交接时必须同时保留原始主题图，上传 R2 后在清单写入 `subject_sheet_url`。
8. 展示原始主题图和成品；确认后用 R2 清单 URL 触发 `.github/workflows/publish-from-r2.yml`。发布任务先幂等写入正式话题与本期 10 个单词，再执行中文 YouTube / Meta 与韩语 MatrixMedia 发布。
9. 展示发布结果后，确认清缓存。

### 后台任务轮询

- 耗时步骤禁止同步调用 `submit_images`（含方舟）、`compose_cards`、`create_videos`、`publish`。
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
| `language_learning_start_submit_images` | 启动主体图提交（含方舟） |
| `language_learning_compose_cards` | 拼单词卡（同步，勿用） |
| `language_learning_start_compose_cards` | 启动拼卡后台任务 |
| `language_learning_create_videos` | 出片（同步，勿用） |
| `language_learning_start_create_videos` | 启动出片后台任务 |
| `language_learning_publish` | 兼容旧客户端；非阿里云环境会拒绝发布 |
| `language_learning_start_publish` | 兼容旧客户端；正式发布统一走阿里云 Workflow |
| `language_learning_poll_task` | 轮询后台任务 |
| `language_learning_clear_run` | 清本次目录 |
