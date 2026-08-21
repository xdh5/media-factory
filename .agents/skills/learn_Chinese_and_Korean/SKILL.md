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

- 发布走 MatrixMedia MCP，`list_accounts` 筛 `phone` 等于 `韩语`
- 跳过掘金、番茄、小红书

## Prompt

词表与主体图 Prompt 由 MCP 工具返回，不要自行改写模板结构：

- `language_learning_build_vocabulary_prompt` → `user_prompt`
- `language_learning_prepare_images` 内部根据词表生成主体图 Prompt

## 确认门禁

1. **成片**：`language_learning_start_create_videos` 轮询完成后展示成片路径、标题、标签、账号组；未确认不得发布。
2. **清缓存**：发布结束后用户确认才调用 `language_learning_clear_run(run_id, confirmed=true)`。

词表、主体图、卡片、出片中间步骤不逐项确认。

## 制作流程

1. `language_learning_get_topics`：避开近 30 天重复主题。
2. 自选主题后 `language_learning_occupy_topic(topic, learning_modes)`，拿到 `run_id`。
3. `language_learning_build_vocabulary_prompt` 获取词表 Prompt，按原样生成纯文本词表，再 `language_learning_parse_vocabulary_response`。
4. `language_learning_prepare_images`（无需手写主体图 Prompt）。
5. 宿主生图时：每生成一张立刻 `language_learning_save_images`，再 `language_learning_start_submit_images`（无能力或单张失败 3 次才传 `failures` 走方舟）→ `language_learning_poll_task`。
6. `language_learning_start_compose_cards` 分别做 `en-zh` 与 `en-ko`（若本次包含两个方向）→ 各自 poll。
7. `language_learning_start_create_videos`：传入本 Skill 的 `voices`、`publish_config`、`language_pause`、`word_pause` → poll 至 `done=true`。
8. 展示成品；确认后：中文 `language_learning_start_publish` + poll；韩语改调 MatrixMedia（`publish_video` 的 `file` 用成片 `output_path`，`phone` 用 `韩语`，**`bt2` 用 `short_title`**，视频号不得省略）。
9. 展示发布结果后，确认清缓存。

### 后台任务轮询

- 耗时步骤禁止同步调用 `submit_images`（含方舟）、`compose_cards`、`create_videos`、`publish`。
- `start` 立即返回 `task_path`；每 15～30 秒调用 `language_learning_poll_task(task_path)`。
- `status=running` 继续等；`succeeded` 读 `result`；`failed` 读 `error` 并停止。
- 客户端报 MCP 超时后**不要重复 start**，继续 poll 同一 `task_path`。

## MCP 工具一览

| 工具 | 作用 |
| --- | --- |
| `language_learning_get_topics` | 查已占用主题 |
| `language_learning_occupy_topic` | 占坑并创建 run |
| `language_learning_build_vocabulary_prompt` | 返回词表 Prompt |
| `language_learning_parse_vocabulary_response` | 解析词表 |
| `language_learning_prepare_images` | 注册主体图任务 |
| `language_learning_save_images` | 写入已生成图 |
| `language_learning_submit_images` | 提交主体图（同步，勿用） |
| `language_learning_start_submit_images` | 启动主体图提交（含方舟） |
| `language_learning_compose_cards` | 拼单词卡（同步，勿用） |
| `language_learning_start_compose_cards` | 启动拼卡后台任务 |
| `language_learning_create_videos` | 出片（同步，勿用） |
| `language_learning_start_create_videos` | 启动出片后台任务 |
| `language_learning_publish` | 发中文 YouTube + Reels（同步，勿用） |
| `language_learning_start_publish` | 启动发布后台任务 |
| `language_learning_poll_task` | 轮询后台任务 |
| `language_learning_clear_run` | 清本次目录 |
