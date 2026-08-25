---
name: finance-video
description: 使用项目财经 MCP 制作中文财经短视频；适用于“做财经视频”“运行 Finance”“生成理财短视频”等请求。不适用于抖音关键词搜索、爬取或内容研究请求。
---

# 财经视频

MCP 入口：`python -m core.mcp.finance`。**本 Skill 提供 Prompt、范文、TTS、BGM、片头、发布账号组与完整流程**；MCP 只负责编排。禁止绕过 MCP 或直接读写内部文件。

开始交互式生产前，必须先让用户明确这期视频的北京时间计划发布日期 `publish_date`。用户没说清是哪一天时必须先追问；禁止默认今天、禁止先选稿或创建 run，也禁止在日期不明确时生成成片并写入 `production_outputs`。

如果用户要求“抖音搜索”“爬抖音”“找抖音前几名”等内容研究，即使同时提到财经，也必须使用抖音研究 Skill 与 `douyin_research` MCP；不得调用本 Skill 的话题查询代替真实抖音搜索。

## Prompt

| 用途 | 位置 |
| --- | --- |
| 数据库原稿改编 | 本 Skill：`prompts/finance.md` |
| 标题标签 | MCP：`finance_get_metadata_prompt` |
| 分镜 | MCP：`finance_prepare_storyboard` 返回 `storyboard_prompt` |

### 数据库原稿改编

第一步必须调用 `finance_get_source_script`，从抖音研究数据库的“财经”分类选择一条未使用稿件。禁止自行从零写正文，也禁止从 `examples/` 选择范文代替数据库原稿。

如果工具返回 `DOUYIN_SCRIPTS_EXHAUSTED`，说明所有财经稿件都已使用；必须向用户报告并停止制作，不得复用旧稿或自行写稿。如果返回 `DOUYIN_SCRIPTS_BUSY`，说明剩余稿件正在其他任务中制作，也必须停止本次制作。

按返回的 `source.transcript` 识别原稿开头完整的黄金钩子，填入本 Skill 的 `prompts/finance.md`：

- `{{source_text}}`：`source.transcript` 原文
- `{{source_hook}}`：原稿开头的完整黄金钩子

改编必须满足：

- 黄金钩子一字不改，改编正文必须以它原样开头。
- 保留原稿论述顺序、段落功能、案例位置、正反对比和结尾结构；只删减或补充细节。
- 正文目标 500 字左右，允许 450～550 字。过长则删重复解释和次要细节；不足则在原段落位置补细节，不得新增分支结构。
- 保持口语短句：每句单独一行；单句指该行完整一句话，全部字符（含所有标点符号）不得超过 20 字。写稿时自行拆行，禁止把一个词或固定搭配拆到两行。句与句之间换行，不要用逗号连两句完整话。
- 原稿出现作者、账号、课程、机构或其他宣传品牌时，统一替换为【财富研习岛】。
- `finance_save_draft` 必须传回 `source.aweme_id`、`reservation.reservation_token` 和 `source_hook`；保存成功后 MCP 自动将数据库来源标记为已使用，下次不再选择。

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

本地交互式财经制作使用用户提供的单张参考图，通过千问逐镜头生图：

```json
{
  "source": "qwen_reference",
  "reference_image_path": "data/reference_images/finance/bright-light-oil-painting.png"
}
```

- 每个分镜镜头必须建立一条独立生图任务，任务数量必须完整覆盖全部镜头。
- 每张图必须以人像为明确主体，画面中的所有人物都必须是欧美人，并具有自然真实的欧美面孔。
- 画面固定为明亮、通透、温暖的轻油画风，使用高亮自然光、浅色背景、清爽配色和细腻可见的油画笔触；禁止阴暗、压抑、厚重或脏灰。
- 人物必须姿态挺拔舒展、神态坚定从容，呈现有力量、正能量、自信、积极向上的气质；禁止软弱、颓丧、焦虑或消沉。
- 所有任务必须携带同一张用户参考图，但参考图只能用于统一画风、笔触、光影、色彩和质感；禁止参考或复制图中的人物身份、面孔、发型、服装、办公室场景、构图、书桌、电脑及其他物体摆放。必须优先执行当前镜头的场景描述，不得默认生成蓝色西装、办公桌、笔记本电脑或窗边办公室；生成画面禁止文字和水印。
- 调用 `finance_start_generate_images(context_path)` 后，用 `finance_poll_task` 轮询；任一镜头失败即停止，不得用旧图库图片补位。
- 如果全部本地图片已经生成，仅最终 D1 入库因网络异常失败，重连 MCP 后必须调用 `finance_commit_existing_images(context_path)`；该恢复工具只校验现有图片并入库，禁止再次调用千问生图。
- 图片统一保存到 `data/image_library_finance/`，文件名使用与 D1 相同的连续数字编号，例如 `1.png`、`2.png`。
- 每次生图从文件夹中现有 `.png` 的最大数字编号继续递增；全部成功后，MCP 自动把相同编号、图片描述和路径写入 `finance_generated_images`。

GitHub Action 继续使用本地图库选图模式，不得删除或改成千问生图。每期开始必须先随机固定一个图库 line，整期所有镜头只能来自该图库，禁止混用：

- `finance`：存量图库，D1 表 `image_library`，目录 `data/image_library/finance/`，R2 包 `assets/image_library.tar`
- `finance_generated`：千问生成图库，D1 表 `finance_generated_images`，目录 `data/image_library_finance/`，R2 包 `assets/image_library_finance.tar`

随机选定后，`finance_prepare_images` 传入：

```json
{
  "source": "local_library",
  "library_line": "finance 或 finance_generated"
}
```

- 图库记录格式：`{id, caption, image_path}`
- `finance_prepare_images` 返回 `library_catalog` 与 `selection_tasks`；Agent 对照每个镜头的 `match_query` 与各图 `caption`，选出语义最贴近的一张
- 选好后调用 `finance_submit_images`，`images` 传入 `[{image_id, image_path}]`（`image_path` 用 catalog 中的路径）
- 同一期可重复使用同一张图；禁止跨图库混选
- 禁止宿主生图

### 成片（`finance_finish_video` 的 `production_config`）

```json
{
  "bgm_path": "从下方两个路径中随机选择一个",
  "cover_frame_seconds": 0.03333333333333333,
  "intro": "slide_in_shutter",
  "shot_stickers": ["rec"],
  "matrixmedia_account_group": "心灵鸡汤"
}
```

- 每期 BGM 必须从 `core/tools/generate_bgm/static/nothing_to_fare.mp3` 和 `core/tools/generate_bgm/static/aware.mp3` 中随机选择一首；同一期只选择一次并沿用到成片，Agent 不得使用其他曲目或修改混音参数
- 本地生产完成后保留本地产物，不自动上传 R2；只有 GitHub Workflow 或用户明确要求远程交付时才调用 `finance_start_upload_r2`
- 发布服务器 MatrixMedia 使用账号组 `心灵鸡汤`，账号配置由发布环境提供，不再从 D1 读取发布账号组。
- MatrixMedia 发布所有平台时必须传 `creativeStatement="ai_generated"`，给成片添加各平台对应的 AI 生成内容标记；不得省略或改为无标注。
- 跳过掘金、番茄、小红书
- **短标题映射**：用成片返回的 `short_title` 作为可选 `bt2`，不得用长标题 `title` 回填；视频号未传时保持短标题框为空。其它平台有该字段时同样传入。
- `tags` 用空格分隔且带 `#`，例如 `"#存钱 #理财常识 #生活方式 #查理芒格"`（最多 4 个）
- MatrixMedia 返回成功或平台官方预约成功结果后，必须调用 `finance_record_publications`。预约发布只接受 `officialScheduled=true` 的平台官方确认结果，禁止把应用内定时任务入库。心灵鸡汤账号组只记录 `ks→kuaishou`、`dy→douyin`、`bjh→baijiahao`、`tt→toutiao`、`sph→wechat_channels`，不得写入小红书；立即发布的 `publish_at` 写实际成功时间，预约发布写预约时间，均使用带时区的 ISO 8601。

## 确认门禁

1. **成片**：稿件生成后直接制作；`finance_start_finish_video` 完成后展示 `output/finance/run-YYYYMMDD/` 中的 `video_path`、标题、标签与发布文案；`YYYYMMDD` 必须是北京时间计划发布日期。未确认不得调用发布 MCP。本地 MCP 制作不得自动上传 R2；GitHub Workflow 产物才自动交付 R2。成片成功后 MCP 自动以 `source=local_mcp` 写入 `production_outputs`；查询某天是否有财经产物使用 `finance_get_production_outputs(publish_date)`。
2. **清缓存**：发布结束后用户确认才调用 `finance_clear_run(run_id, confirmed=true)`。

财经 GitHub Workflow 并入 `weekly-production`：每周五北京时间 12:00 串行生产下周周一至周日内容；每个计划日若已有财经成片或发布记录则跳过。Workflow 只把成片交付 R2，不执行平台发布。也可手动触发 weekly-production 并指定下周起始周一。

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

1. `finance_get_source_script`：选择并临时占用一条未使用的财经数据库原稿。
2. 按本 Skill 的 `prompts/finance.md` 把原稿改为 450～550 字；黄金钩子和原结构不得改变，宣传品牌统一替换为【财富研习岛】。
3. 从改编正文提炼 `topic`；调用 `finance_get_metadata_prompt` 后写标题标签行。
4. 用**长标题**按语义断成 1～3 行 `cover_lines`。封面不自动折行。
5. 从长标题中选出 1～3 个真正承载点击理由的重点词，作为 `cover_highlights` 传入；每项必须原样出现在 `title` 中。封面重点词使用 `#F2A623` 金黄色，其他文字使用白色，统一加 6px 黑色描边。
6. 先确定北京时间计划发布日期 `publish_date`（`YYYY-MM-DD`，不得早于当天）；`finance_save_draft` 除原参数外传入 `publish_date`、`source_aweme_id`、`source_reservation_token`、`source_hook` 和 `cover_highlights`。MCP 创建 `output/finance/run-YYYYMMDD/`；日期只表示计划发布日，不包含具体时间。保存成功后 MCP 自动将数据库原稿标记为已使用，直接进入制作。

### 第二阶段：制作与发布

1. `finance_start_storyboard(draft_path, tts_config=…)` → `finance_poll_task(task_path)` 直至 `done=true`，取 `result` 作为分镜上下文。
2. 按 `result.storyboard_prompt` 写完整分镜文本（IMAGE 行 + 每句一条 `SUB` 行，见上文「字幕重点」）。
3. 本地交互制作调用 `finance_prepare_images`，传入 `qwen_reference` 配置和用户参考图；确认返回的任务数量覆盖全部镜头。
4. 调用 `finance_start_generate_images(context_path)` → `finance_poll_task` 直至 `done=true`；全部生成后直接写入图库，结果包含生图清单、当次图片目录和数据库连续编号，不设置人物、画风或情绪检查门禁。
5. `finance_start_finish_video` → `finance_poll_task` 直至 `done=true`；传入 `production_config`；配音直接用 `prepare_storyboard` 的 `tts_path`。
6. 展示本地成片路径和发布信息，不在本地制作阶段调用 `finance_start_upload_r2`。
7. 用户确认后，把本地清单和成片交给 MatrixMedia MCP；发布 MCP 先把正式话题幂等写入 D1，再用账号组 `心灵鸡汤` 发布，并对每个平台传入清单中的 `creativeStatement="ai_generated"`。只有用户明确要求远程交付时才上传 R2。
8. 展示发布结果后，确认清缓存。

### 后台任务轮询

- 耗时步骤禁止同步调用 `prepare_storyboard` / `finish_video`。
- `start` 立即返回 `task_path`；每 15～30 秒调用 `finance_poll_task(task_path)`。
- `status=running` 继续等；`succeeded` 读 `result`；`failed` 读 `error` 并停止。
- 客户端报 MCP 超时后**不要重复 start**，继续 poll 同一 `task_path`。

## MCP 工具一览

| 工具 | 作用 |
| --- | --- |
| `finance_get_source_stats` | 只读统计财经原稿总数、可用数、有效占用数和已使用数；不会占用稿件 |
| `finance_get_production_outputs` | 按北京时间计划发布日期查询财经成片及本地/R2位置 |
| `finance_get_source_script` | 选择并临时占用未使用的财经数据库原稿；全部用完时报错 |
| `finance_get_topics` | 兼容保留的已占用话题查询；新流程不作为第一步 |
| `finance_get_metadata_prompt` | 返回标题标签 Prompt |
| `finance_save_draft` | 保存数据库改编稿并将来源标记为已使用 |
| `finance_prepare_storyboard` | TTS + 分镜（同步，易超时，勿用） |
| `finance_start_storyboard` | 启动 TTS + 分镜后台任务 |
| `finance_poll_task` | 轮询后台任务 |
| `finance_prepare_images` | 按 image_config 准备镜头图 |
| `finance_start_generate_images` | 按用户参考图逐镜头调用千问生图，并直接写入独立连续编号图库 |
| `finance_commit_existing_images` | 生图已完成但 D1 入库失败时，仅校验现有图并重试入库，绝不重新生图 |
| `finance_save_images` | 写入已生成图（通常不用） |
| `finance_submit_images` | 提交选图清单 |
| `finance_finish_video` | 合成成片（同步，易超时，勿用） |
| `finance_start_finish_video` | 启动成片合成后台任务 |
| `finance_start_upload_r2` | 后台上传财经成片、封面和发布清单到 R2 |
| `finance_clear_run` | 清本次目录 |
