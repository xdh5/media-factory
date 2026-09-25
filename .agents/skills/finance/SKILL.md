---
name: finance-video
description: 使用项目财经 MCP 制作中文短视频（财经、心灵鸡汤等文章类内容）；适用于“做财经视频”“运行 Finance”“生成理财短视频”“做心灵鸡汤视频”等请求。不适用于抖音关键词搜索、爬取或内容研究请求。
---

# 财经视频

MCP 入口：`python -m core.mcp.finance`。**Finance MCP 是 Prompt、素材策略、TTS、BGM、片头和生产参数的唯一真源**；本 Skill 只描述交互门禁与完整流程。禁止绕过 MCP 或直接读写内部文件。

本线是唯一的文章成片线：**心灵鸡汤等非财经文章内容同样走这条线**，不再有独立业务线。内容类型由数据库原稿决定，制作流程完全一致。

开始交互式生产前，必须先让用户明确这期视频的北京时间计划发布日期 `publish_date`。用户没说清是哪一天时必须先追问；禁止默认今天、禁止先选稿或创建 run，也禁止在日期不明确时生成成片并写入 `production_outputs`。

如果用户要求“抖音搜索”“爬抖音”“找抖音前几名”等内容研究，即使同时提到财经，也必须使用抖音研究 Skill 与 `douyin_research` MCP；不得调用本 Skill 的话题查询代替真实抖音搜索。

## Prompt

| 用途 | 位置 |
| --- | --- |
| 原稿整理（三类必做改动 + 措辞级改写，保留大结构与信息） | MCP：`finance_get_article_prompt` |
| 标题标签 | MCP：`finance_get_metadata_prompt` |
| 分镜 | MCP：`finance_start_storyboard` 返回的 `storyboard_prompt`（按素材策略给出 IMAGE 或 VIDEO 规则） |

### 原稿整理

第一步必须调用 `finance_get_source_script`，从抖音研究数据库选择一条未使用稿件。禁止自行从零写正文，也禁止从 `examples/` 选择范文代替数据库原稿。

如果工具返回 `DOUYIN_SCRIPTS_EXHAUSTED`，说明所有稿件都已使用；必须向用户报告并停止制作，不得复用旧稿或自行写稿。如果返回 `DOUYIN_SCRIPTS_BUSY`，说明剩余稿件正在其他任务中制作，也必须停止本次制作。

按返回的 `source.transcript` 调用 `finance_get_source_hook_prompt`，宿主 Agent 按 Prompt 识别后必须调用 `finance_validate_source_hook_response`；再调用 `finance_get_article_prompt` 与 `finance_get_article_generation_prompt`，宿主 Agent 生成 JSON 后必须调用 `finance_validate_article_response`。禁止在 Agent 侧另写钩子、正文解析或校验规则。

- `{{source_text}}`：`source.transcript` 原文
- `{{source_hook}}`：原稿开头完整黄金钩子中**完成品牌替换后的版本**（该版本也是 `finance_save_draft` 要传的 `source_hook`）

整理必须满足（交互式与 GitHub Action 统一执行同一套规则）：

- **三类必做改动**：
  1. **替换作者与品牌**：作者名、账号名、课程名、机构名或其他宣传品牌统一替换为「财富研习岛」。**黄金钩子内部同样执行**——钩子里的机构名、研究名、权威背书也要替换，不留原品牌。
  2. **改写连载指涉**：本文是「财富研习岛」作者独立的一篇文章，没有任何前文。原稿出现「第 X 集/期/话」「上一集/上一期」「这一集/这一期」「下一集/下一期」「上回」「上一条/上个/上一支视频」「前情回顾」「往期」等指向系列前文或后文的表述时，改写成不依赖任何前文也能读懂的独立表述。
  3. **修正错别字**：只修正答案明确的错别字、同音错字和明显转写错误，不改变原意；拿不准时保留原词。
- **在三类改动之外允许措辞级改写**：逐句换说法、调整句式和用词，避免和原稿逐字雷同；但句子顺序、段落划分与论证逻辑必须与原稿一致，每个观点、数字、例子的信息都必须保留，不得压缩、扩写、增删观点或重排段落，正文长度与原稿基本相当。
- **黄金钩子保持原样**：钩子只做品牌替换和明确错别字修正，不做措辞改写；正文必须以处理后的钩子原字原标点原顺序开头，钩子之后才开始改写。
- 断行：按语义切成口语短句，每句单独一行，单行全部字符（含所有标点）不超过 36 字；不得把一个词或固定搭配拆到两行。
- 句与句之间换行，不要用逗号连两句完整话；顿号列举写在同一句里。
- `finance_save_draft` 必须传回 `source.aweme_id`、`reservation.reservation_token` 和 `source_hook`；保存成功后 MCP 自动将数据库来源标记为已使用，下次不再选择。

## 固定参数（调用 MCP 时必须按此传）

### 素材策略（`finance_start_storyboard` 的 `material_strategy`）

固定生产参数必须先调用 `finance_get_production_config` 从 Finance MCP 读取，MCP 是唯一真源，Agent 与 GitHub Action 禁止各自复制一份参数。三类策略并列保留，默认直接使用 MCP 返回的 `stock_video`；只有用户明确要求改用其他策略时才切换：

| 取值 | 画面 | 适用 |
| --- | --- | --- |
| `image_library` | 存量图库选图 → 静态图慢推拉 | 交互式需要省时间时可用 |
| `qwen_reference` | 用户参考图 + 千问逐镜头生图 | 用户明确需要统一画风时使用 |
| `stock_video` | Pexels/Pixabay/Coverr 正版实拍视频 + 片头写实图 | Agent 与 GitHub Action 默认使用 |

### 镜头图（`image_config`，仅 `image_library` / `qwen_reference` 需要）

`image_library`：

```json
{
  "source": "local_library",
  "library_line": "finance"
}
```

- 图库记录格式：`{id, caption, image_path}`
- `finance_prepare_images` 返回 `library_catalog` 与 `selection_tasks`；Agent 对照每个镜头的 `match_query` 与各图 `caption`，选出语义最贴近的一张
- 选好后调用 `finance_submit_images`，`images` 传入 `[{image_id, image_path}]`
- 同一期可重复使用同一张图；禁止宿主生图

`qwen_reference`（用户明确指定时）：

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
- 图片统一保存到 `data/image_library_finance/`，文件名使用与 D1 相同的连续数字编号，例如 `1.png`。

### 实拍视频（`video_config`，仅 `stock_video` 需要）

完整参数直接使用 `finance_get_production_config.video_config`，Skill 不保留副本。

- `soft_blur_sigma` 控制正文素材的白蒙版磨砂强度（`core/tools/soft_blur_video`），传 `0` 关闭；片头图与封面帧保持清晰。
- 流程：`finance_start_video_search(draft_path, storyboard_text, video_config)` → 轮询 → Agent 选候选 → `finance_start_download_videos(context_path, selections)` → 轮询。
- 搜索结果里的 `intro_image_prompt` 用来生成片头写实图（宿主 Agent 生图或 ImageGen 均可），成片时通过 `intro_image_path` 传入。
- 分镜第一个镜头是片头图 + 转场动画，正文从第二个镜头起使用实拍素材；分镜至少要有两个镜头。
- 素材来源不烧进视频；成片会在 `output/finance/<run_id>/attribution-comment.txt` 保留来源页、作者和署名文案。

### TTS（`finance_start_storyboard` 的 `tts_config`）

完整参数直接使用 `finance_get_production_config.tts_config`，Skill 不保留副本。

### 成片（`finance_start_finish_video` 的 `production_config`）

完整参数直接使用 `finance_get_production_config.production_config`，Skill 不保留副本。

- BGM 文件与音量以 MCP 返回值为准，不得在 Agent 或 GitHub 入口覆盖。
- **不要配置 `bgm_credit`**：音乐署名由用户自己补充，生产环节不得写入任何音乐署名。
- 字幕样式、字幕位置、黄金钩子展示等视觉参数全部走 MCP 默认值（`core/tools/generate_final_video/_defaults.py`），Agent 不得在 `production_config` 里重复或覆盖。
- 片头转场固定 `slide_in_shutter`，保留快门音效与 `rec` 贴纸。
- 本地生产完成后保留本地产物，不自动上传 R2；只有 GitHub Workflow 或用户明确要求远程交付时才调用 `finance_start_upload_r2`。
- 发布服务器 MatrixMedia 使用账号组 `心灵鸡汤`。这里的内容线已并入 `finance`，账号组的业务线也就是 `finance`。
- MatrixMedia 发布所有平台时必须传 `creativeStatement="ai_generated"`，给成片添加各平台对应的 AI 生成内容标记；不得省略或改为无标注。
- 跳过掘金、番茄、小红书
- **短标题映射**：用成片返回的 `short_title` 作为可选 `bt2`，不得用长标题 `title` 回填；视频号未传时保持短标题框为空。其它平台有该字段时同样传入。
- `tags` 用空格分隔且带 `#`，例如 `"#存钱 #理财常识 #生活方式 #查理芒格"`（最多 4 个）
- MatrixMedia 返回成功或平台官方预约成功结果后，必须调用 `finance_record_publications`。预约发布只接受 `officialScheduled=true` 的平台官方确认结果，禁止把应用内定时任务入库。心灵鸡汤账号组只记录 `ks→kuaishou`、`dy→douyin`、`bjh→baijiahao`、`tt→toutiao`、`sph→wechat_channels`，不得写入小红书；立即发布的 `publish_at` 写实际成功时间，预约发布写预约时间，均使用带时区的 ISO 8601。

## 确认门禁

1. **素材策略**：默认使用 `stock_video`，无需逐期确认；用户明确指定 `image_library` 或 `qwen_reference` 时按用户选择覆盖。
2. **成片**：稿件生成后直接制作；`finance_start_finish_video` 完成后展示 `output/finance/run-YYYYMMDD/` 中的 `video_path`、标题、标签与发布文案；`YYYYMMDD` 必须是北京时间计划发布日期。未确认不得调用发布 MCP。本地 MCP 制作不得自动上传 R2；GitHub Workflow 产物才自动交付 R2。成片成功后 MCP 自动以 `source=local_mcp` 写入 `production_outputs`；查询某天是否有产物使用 `finance_get_production_outputs(publish_date)`。
3. **清缓存**：发布结束后用户确认才调用 `finance_clear_run(run_id, confirmed=true)`。

中间步骤不逐项确认。

## 字幕与片头钩子

字幕统一使用 `karaoke` 逐词动画：整句白字显示，当前字按配音时间以黄色 `#FFD54A` 从左向右扫过，字幕固定在屏幕正中，屏上文本自动去掉句尾标点。

片头黄金钩子单独展示：第一个镜头的前几句（稿件黄金钩子覆盖的台词行，MCP 按原稿钩子自动识别）改放到屏幕下方的旧版字幕位置逐行出现，同一时间段稿件标题居中显示；钩子读完后，其余字幕回到屏幕正中。标题用字魂群英体（商用需授权，需保证 `static/font/字魂群英体.ttf` 在包内）、字号 165，按标点断行：单行红字（#E30F13）黑边；多行时第一行字幕黄（#FFD54A）黑边，其余行红字白边。这些位置与配色都由 MCP 默认值（`core/tools/generate_final_video/_defaults.py`）控制，Agent 不得覆盖。

分镜里：

- 格式：`台词ID|时长|IMAGE（或 VIDEO）|画面描述或英文检索词|动效参数`，写在全部素材行之后或穿插均可，解析按 ID 合并。
- 每一句都必须原样抄写配音原文，不加 `【】` 或其他重点标记。
- 成片自动套用黄色逐词扫动画，Agent 不得修改预设、颜色或位置。

示例：

```
L001,L002|3.20|IMAGE|油画书房窗边的人对着空钱包|1.00^1.08^0.45^0.50^0.55^0.50^0^0
SUB|L001|普通人最大的财富陷阱
SUB|L002|你以为涨薪就能存钱
```

## 制作流程

### 第一阶段：稿件

1. `finance_get_source_script`：选择并临时占用一条未使用的数据库原稿。
2. 调用 `finance_get_article_prompt` 获取统一 Prompt 并整理原稿：执行三类必做改动并做措辞级改写（保留大结构与全部信息），把作者与品牌替换为「财富研习岛」并按语义断行。
3. 调用 `finance_get_topic_generation_prompt`，生成后交给 `finance_validate_topic_response`；再调用 `finance_get_metadata_generation_prompt`，生成后交给 `finance_validate_metadata_response`。禁止在 Agent 侧另写话题、标题、封面或片头场景校验规则。
4. 用**长标题**按语义断成 1～3 行 `cover_lines`。封面不自动折行。
5. 从长标题中选出 1～3 个真正承载点击理由的重点词，作为 `cover_highlights` 传入；每项必须原样出现在 `title` 中。封面重点词使用 `#F2A623` 金黄色，其他文字使用白色，统一加 6px 黑色描边。
6. 先确定北京时间计划发布日期 `publish_date`（`YYYY-MM-DD`，不得早于当天）；`finance_save_draft` 除原参数外传入 `publish_date`、`source_aweme_id`、`source_reservation_token`、`source_hook`、`cover_highlights`，`stock_video` 策略还要传 `intro_scene`（片头写实图场景描述）。MCP 创建 `output/finance/run-YYYYMMDD/`；日期只表示计划发布日，不包含具体时间。保存成功后 MCP 自动将数据库原稿标记为已使用，直接进入制作。

### 第二阶段：制作与发布

1. 调用 `finance_get_production_config` 读取默认素材策略和参数；用户明确覆盖时仅覆盖素材策略，再 `finance_start_storyboard(draft_path, tts_config=…, material_strategy=…)` → `finance_poll_task(task_path)` 直至 `done=true`，取 `result` 作为分镜上下文。
2. 按 `result.storyboard_prompt` 写完整分镜文本（素材行 + 每句一条纯文本 `SUB` 行，见上文「字幕与片头钩子」）。
3. 按策略准备素材：
   - `image_library` / `qwen_reference`：`finance_prepare_images` → （生图策略）`finance_start_generate_images` + 轮询 / （图库策略）Agent 选图后 `finance_submit_images`；
   - `stock_video`：`finance_start_video_search` + 轮询 → `finance_get_stock_video_selection_prompt` → 宿主 Agent 选候选 → `finance_validate_stock_video_selection_response` → `finance_start_download_videos` + 轮询；同时按 MCP 返回的 `intro_image_prompt` 由宿主 Agent 生成片头写实图。
4. `finance_start_finish_video` → `finance_poll_task` 直至 `done=true`；传入 `production_config`、素材清单路径（`material_manifest_path`），`stock_video` 策略另传 `intro_image_path`。配音直接用 `prepare_storyboard` 的 `tts_path`。
   - 交互式生产必须由宿主 Agent 判断重点句、每段 1～2 行语义断行及每行 1～2 个标红重点词，并通过 `production_config.emphasis_lines.groups` 传入；禁止让 MCP 在交互式生产中自行调用文本模型。
   - 每组可用 `sentence_text` 传入完整句子原文，由工具精确匹配对应字幕句；也可使用工具返回的 `sentence` 编号。不要猜编号。
   - 每个重点显示行必须至少有一个原文连续子串作为标红词；任何一行缺少重点词、拆开词语或拼回后不等于原文，工具都会拒绝该配置。
   - 重点字幕不触发任何提示音效；只保留字幕动画与标红效果。
   - GitHub Action 没有宿主 Agent，允许不传 `groups`，由生产 Runner 调用文本模型 API 完成相同判断。
5. 展示本地成片路径和发布信息，不在本地制作阶段调用 `finance_start_upload_r2`。
6. 用户确认后，把本地清单和成片交给 MatrixMedia MCP；发布 MCP 先把正式话题幂等写入 D1，再用账号组 `心灵鸡汤` 发布，并对每个平台传入清单中的 `creativeStatement="ai_generated"`。只有用户明确要求远程交付时才上传 R2。
7. 展示发布结果后，确认清缓存。

### 生产入口

- GitHub Action：`python -m ops.github_actions finance`（读取 Finance MCP 的统一配置，默认使用 `stock_video`，产物自动上传 R2，不发布平台）。每周六批量处理下周周一至周日，每个计划发布日期生产 2 条财经成片，分别使用 `content_part=1` 和 `content_part=2`；已有分片会在预检时跳过，只补齐缺失分片。
- 交互式：`python -m core.mcp.finance`（本地制作，保留本地产物，发布需用户确认）。

### 后台任务轮询

- 耗时步骤禁止同步调用 `prepare_storyboard` / `finish_video`。
- `start` 立即返回 `task_path`；每 15～30 秒调用 `finance_poll_task(task_path)`。
- `status=running` 继续等；`succeeded` 读 `result`；`failed` 读 `error` 并停止。
- 客户端报 MCP 超时后**不要重复 start**，继续 poll 同一 `task_path`。

## MCP 工具一览

| 工具 | 作用 |
| --- | --- |
| `finance_get_production_config` | 返回 Agent 与 GitHub Runner 共用的默认素材策略、TTS、视频搜索和成片参数 |
| `finance_get_automation_plan` | 返回指定日期的 GitHub 财经生产预检结果 |
| `finance_get_source_hook_prompt` / `finance_validate_source_hook_response` | 共用黄金钩子识别 Prompt 与校验 |
| `finance_get_article_prompt` | 返回 Agent 与 GitHub Runner 共用的正文整理 Prompt |
| `finance_get_article_generation_prompt` / `finance_validate_article_response` | 共用正文模型输出协议与校验 |
| `finance_get_topic_generation_prompt` / `finance_validate_topic_response` | 共用话题生成与去重校验 |
| `finance_get_metadata_generation_prompt` / `finance_validate_metadata_response` | 共用标题、标签、封面和片头场景生成与校验 |
| `finance_get_stock_video_selection_prompt` / `finance_validate_stock_video_selection_response` | 共用正版视频候选选择 Prompt 与校验 |
| `finance_get_source_stats` | 只读统计原稿总数、可用数、有效占用数和已使用数；不会占用稿件 |
| `finance_get_production_outputs` | 按北京时间计划发布日期查询成片及本地/R2位置 |
| `finance_get_source_script` | 选择并临时占用未使用的数据库原稿；全部用完时报错 |
| `finance_get_topics` | 最近 30 天已占用话题查询 |
| `finance_get_metadata_prompt` | 返回标题标签 Prompt |
| `finance_save_draft` | 保存按原稿全文整理的稿件并将来源标记为已使用 |
| `finance_prepare_storyboard` | TTS + 分镜（同步，易超时，勿用） |
| `finance_start_storyboard` | 启动 TTS + 分镜后台任务（需传 `material_strategy`） |
| `finance_poll_task` | 轮询后台任务 |
| `finance_prepare_images` | 按 image_config 准备镜头图（图库/生图策略） |
| `finance_start_generate_images` | 按用户参考图逐镜头调用千问生图，并直接写入独立连续编号图库 |
| `finance_commit_existing_images` | 生图已完成但 D1 入库失败时，仅校验现有图并重试入库，绝不重新生图 |
| `finance_save_images` | 写入已生成图（通常不用） |
| `finance_submit_images` | 提交选图清单 |
| `finance_start_video_search` | 实拍视频策略：逐镜头搜索 Pexels/Pixabay/Coverr 候选 |
| `finance_start_download_videos` | 实拍视频策略：下载、规范化并按配置磨砂 |
| `finance_finish_video` | 合成成片（同步，易超时，勿用） |
| `finance_start_finish_video` | 启动成片合成后台任务 |
| `finance_start_upload_r2` | 后台上传成片、封面和发布清单到 R2 |
| `finance_record_publications` | 发布成功后写入 D1 发布记录 |
| `finance_clear_run` | 清本次目录 |
