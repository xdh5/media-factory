---
name: finance-video
description: 使用项目财经 MCP 制作中文财经短视频；适用于“做财经视频”“运行 Finance”“生成理财短视频”等请求。
---

# 财经视频

MCP 入口：`python -m core.mcp.finance`。**本 Skill 提供 Prompt、范文、TTS、BGM、片头、发布账号组与完整流程**；MCP 只负责编排。禁止绕过 MCP 或直接读写内部文件。

## Prompt

| 用途 | 位置 |
| --- | --- |
| 正文、钩子、范文 | 本 Skill：`prompts/finance.md`、`examples/` |
| 标题标签 | MCP：`finance_get_metadata_prompt` |
| 分镜 | MCP：`finance_prepare_storyboard` 返回 `storyboard_prompt` |

### 正文 Prompt 占位符

按选定 `topic` 填入本 Skill 的 `prompts/finance.md`：

- `{{topic}}`：中文话题
- `{{hooks}}`：`examples/hooks.txt` 全文
- `{{article_examples}}`：各范文 `### 文件名\n正文` 拼接

## 固定参数（调用 MCP 时必须按此传）

### TTS（`finance_start_storyboard` 的 `tts_config`）

```json
{
  "voice": "zh-CN-YunjianNeural",
  "rate": "+20%",
  "trim_trailing_silence": true
}
```

### 镜头图（`finance_prepare_images` 的 `image_config`）

财经固定使用本地图库，由 Agent 按 caption 与镜头 prompt 语义匹配选图：

```json
{
  "source": "local_library",
  "library_line": "finance"
}
```

- 图库目录：`data/image_library/finance/`
- 本地图库存在时直接使用；缺失时 MCP 自动从 R2 的 `assets/finance-images.tar` 下载并解压恢复
- 图库记录格式：`{id, caption, image_path}`
- `finance_prepare_images` 返回 `library_catalog` 与 `selection_tasks`；Agent 对照每个镜头的 `match_query` 与各图 `caption`，选出语义最贴近的一张
- 选好后调用 `finance_submit_images`，`images` 传入 `[{image_id, image_path}]`（`image_path` 用 catalog 中的路径）
- 同一期可重复使用同一张图，无需考虑历史选用均分
- 禁止宿主生图

### 成片（`finance_finish_video` 的 `production_config`）

```json
{
  "bgm_path": "core/tools/generate_bgm/static/cinematic-inspirational-piano-ambient-128209.mp3",
  "cover_frame_seconds": 0.03333333333333333,
  "intro": "slide_in_shutter",
  "shot_stickers": ["rec"],
  "matrixmedia_account_group": "心灵鸡汤"
}
```

- BGM 固定 `cinematic-inspirational-piano-ambient-128209`；Agent 不得改曲目或混音参数
- 生产完成后调用 `finance_start_upload_r2` 上传 R2
- 发布服务器上的独立 MatrixMedia MCP 使用账号组 `心灵鸡汤`
- 跳过掘金、番茄、小红书
- **视频号必填 `bt2`**：用成片返回的 `short_title`（稿件短标题，已是 6～16 字）。禁止省略，禁止把长标题 `title` 填进短标题框。其它平台也一律带上 `bt2`，避免漏传。
- `tags` 用空格分隔且带 `#`，例如 `"#存钱 #理财常识 #生活方式 #查理芒格"`（最多 4 个）

## 确认门禁

1. **成片**：稿件生成后直接制作；`finance_start_finish_video` 与 `finance_start_upload_r2` 轮询完成后展示 `video_path`、标题、标签、发布文案与 R2 清单 URL；未确认不得调用发布 MCP。
2. **清缓存**：发布结束后用户确认才调用 `finance_clear_run(run_id, confirmed=true)`。

中间步骤不逐项确认。

## 字幕重点

写分镜时必须给 timeline 里每一句台词标重点，不要等成片后再改。

- 格式：`SUB|台词ID|屏上文本`，写在全部 IMAGE 行之后（或穿插均可，解析按 ID 合并）。
- 用【】包住要强调的词；**括号只是标记，画面上不显示**。
- 一句可以：只标几个字、**整句都包进【】**、或**完全不标**（原样抄台词、不加括号）。
- 同一句可以有多处【】，但不能嵌套；【】内不能为空。
- 去掉【】之后，必须与该句配音原文一致（屏上仍会去掉句读标点，顿号保留）。
- 成片自动套用样式，Agent 不要改字号或颜色：相对默认字幕 **130%**（`font_size: 130`），颜色 **`#FFD54A`**。

示例：

```
L001,L002|3.20|IMAGE|油画书房窗边的人对着空钱包|1.00^1.08^0.45^0.50^0.55^0.50^0^0
SUB|L001|普通人最大的【财富陷阱】
SUB|L002|你以为涨薪就能存钱
```

## 制作流程

### 第一阶段：稿件

1. `finance_get_topics`：避开近 30 天重复话题。
2. 按本 Skill 正文模板与范文生成正文；调用 `finance_get_metadata_prompt` 后写标题标签行。
3. 用**长标题**按语义断成 1～3 行 `cover_lines`（拼接去空白后必须等于长标题 `title`）。封面不自动折行。
4. `finance_save_draft` → 只保存本次生产稿件，不写 D1，直接进入制作。

### 第二阶段：制作与发布

1. `finance_start_storyboard(draft_path, tts_config=…)` → `finance_poll_task(task_path)` 直至 `done=true`，取 `result` 作为分镜上下文。
2. 按 `result.storyboard_prompt` 写完整分镜文本（IMAGE 行 + 每句一条 `SUB` 行，见上文「字幕重点」）。
3. `finance_prepare_images`（传入本 Skill 的 `image_config`）→ 按 `library_catalog` 与 `selection_tasks` 为每个镜头选最贴近的图 → `finance_submit_images`（`images` 传 `[{image_id, image_path}]`）。
4. `finance_start_finish_video` → `finance_poll_task` 直至 `done=true`；传入 `production_config`；配音直接用 `prepare_storyboard` 的 `tts_path`。
5. 调用 `finance_start_upload_r2(manifest_path, run_id)` → `finance_poll_task` 直至完成，展示成片和 `manifest_url`。
6. 用户确认后，把 R2 清单 URL 交给发布服务器上的独立 MatrixMedia MCP；发布 MCP 先把正式话题幂等写入 D1，再用账号组 `心灵鸡汤` 发布。
7. 展示发布结果后，确认清缓存。

### 后台任务轮询

- 耗时步骤禁止同步调用 `prepare_storyboard` / `finish_video`。
- `start` 立即返回 `task_path`；每 15～30 秒调用 `finance_poll_task(task_path)`。
- `status=running` 继续等；`succeeded` 读 `result`；`failed` 读 `error` 并停止。
- 客户端报 MCP 超时后**不要重复 start**，继续 poll 同一 `task_path`。

## MCP 工具一览

| 工具 | 作用 |
| --- | --- |
| `finance_get_topics` | 查已占用话题 |
| `finance_get_metadata_prompt` | 返回标题标签 Prompt |
| `finance_save_draft` | 占坑并保存稿件 |
| `finance_prepare_storyboard` | TTS + 分镜（同步，易超时，勿用） |
| `finance_start_storyboard` | 启动 TTS + 分镜后台任务 |
| `finance_poll_task` | 轮询后台任务 |
| `finance_prepare_images` | 按 image_config 准备镜头图 |
| `finance_save_images` | 写入已生成图（通常不用） |
| `finance_submit_images` | 提交选图清单 |
| `finance_finish_video` | 合成成片（同步，易超时，勿用） |
| `finance_start_finish_video` | 启动成片合成后台任务 |
| `finance_start_upload_r2` | 后台上传财经成片、封面和发布清单到 R2 |
| `finance_clear_run` | 清本次目录 |
