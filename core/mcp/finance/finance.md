# 财经 MCP

编排入口：`python -m core.mcp.finance`。

生产参数以 `finance_get_production_config` 返回值为唯一标准；Agent 与 GitHub Runner 共用，禁止在各自入口复制。

财经线是唯一的文章成片线（原心灵鸡汤线已并入删除）；财经 Skill 提供原稿整理规则等业务参数，标题标签与分镜 Prompt 在 `core/mcp/finance/prompts/`。完整流程见 `.agents/skills/produce-finance-video/SKILL.md`。收集财经文案也在本 MCP，见 `.agents/skills/collect-finance-copy/SKILL.md`。

## 目录职责

- `__main__.py`：启动入口；`server.py`：创建服务实例。
- `tools/registry.py`：注册工具，保持原有工具名称和参数。
- `workflows/`：按稿件、素材、交付、后台任务拆分业务编排。
- `services/`：稿件处理、分镜、素材准备、收集文案、合成和上传服务；调用方直接导入所需服务。
- `services/collect_copy.py`：下载抖音链接、转写并写入财经文案库。
- `services/production_config.py`：成片参数校验。
- `services/video_layers.py`：字幕、钩子标题和章节图层。
- `services/video_opening.py`：片头渲染和缓存。
- `services/video_materials.py`：素材时长处理、分镜清单和署名。
- `services/assemble_finance_video.py`：组织合成步骤并登记生产产物。
- `infrastructure/gateways.py`：工作流依赖的外部工具接口。
- `config/`：生产配置、目录规则和服务说明；`errors/`：领域错误。
- `prompts/`：现有业务提示词。

## 工具编排

```
finance_get_production_config
finance_get_automation_plan(publish_date)
  └─ 每个计划发布日期目标为 1 条，返回尚缺少的 content_part（1）
finance_get_source_hook_prompt / finance_validate_source_hook_response
finance_get_article_prompt(source_text, source_hook)
finance_get_article_chunk_plan
  └─ 首段钩子与后续语义短句拆成多个小任务
finance_get_article_chunk_generation_prompt / finance_validate_article_chunk_response
  └─ Runner 逐段生成与校验，失败只重试当前段
finance_validate_article_response
  └─ 合并后执行全文校验
finance_get_topic_generation_prompt / finance_validate_topic_response
finance_get_metadata_generation_prompt / finance_validate_metadata_response
  └─ 只确定长短标题与标签
finance_get_visual_metadata_prompt / finance_validate_visual_metadata_response
  └─ 根据确定标题生成封面断行与重点词
finance_get_article_linebreak_prompt / finance_validate_article_linebreak_response
  └─ 每段改写后单独断句，去掉换行必须与改写稿逐字一致
finance_get_stock_video_selection_prompt / finance_validate_stock_video_selection_response
finance_start_collect_copy(share_text, collection_name)
└─ services.collect_copy.collect_copy
   └─ 收集财经文案：下载单条抖音链接、转写口播并写入文案库
finance_poll_task(task_path)

finance_get_source_stats
└─ cloudflare_data.get_finance_copy_stats
   └─ 只读统计原稿总数、可用数、有效占用数和已使用数

finance_get_source_script
└─ cloudflare_data.reserve_finance_copy
   └─ 选择未使用原稿并临时占用

finance_get_metadata_prompt
└─ tools.prompts.build_metadata_prompt
   └─ prompts/metadata.md

[Agent 按 Skill 把原稿整理为正文：三类必做改动（品牌替换、连载指涉改写、错别字修正）+ 措辞级改写但保留大结构与信息，再按 metadata_prompt 写标题标签]

finance_save_draft(...)
└─ topic_dedup.get_topic 查重；暂不写 D1
└─ tools.save_draft.save_draft
   └─ tools.parse_metadata.parse_metadata
└─ 来源原稿保持临时占用，暂不标记已使用

finance_get_topics
└─ topic_dedup.get_topic

finance_start_storyboard(draft_path, tts_config, material_strategy)
└─ core.mcp._task_runner.submit_task
   └─ tools.storyboard.prepare_storyboard
      └─ prompts/shot_image_rules.md（qwen_reference）
      └─ prompts/stock_video_rules.md（stock_video）

finance_poll_task(task_path)
└─ core.mcp._task_runner.poll_task

[Agent 按 storyboard_prompt 写分镜行，并为每句原样写 SUB 字幕；成片统一套用黄色 karaoke 逐字扫]

素材策略 A：参考图千问生图
finance_prepare_images(..., image_config)
└─ tools.prepare_shot_images.prepare_shot_images
   └─ qwen_reference → 每个镜头建立独立任务并附带用户参考图
finance_start_generate_images(context_path)
└─ tools.generate_qwen_shot_images.generate_qwen_shot_images
finance_save_images / finance_submit_images
└─ generate_image 保存或提交 Agent 图任务

素材策略 B：正版实拍视频
finance_start_video_search(draft_path, storyboard_text, video_config)
└─ tools.prepare_videos.prepare_video_searches
   └─ stock_video.search_stock_videos（Pexels → Pixabay → Coverr 兜底）
finance_start_download_videos(context_path)
└─ tools.prepare_videos.download_selected_videos
   └─ stock_video.prepare_stock_clip 一次完成拼接、裁切、帧率规范化与磨砂
   └─ 按素材与参数签名复用完成镜头；最多并发处理 3 个镜头

finance_start_finish_video(..., production_config, material_manifest_path, intro_image_path?)
└─ core.mcp._task_runner.submit_task
   └─ tools.assemble_finance_video.finish_finance_video
      └─ 按素材清单自动识别策略（images → 千问生图；videos → 实拍视频）
      └─ 复用 prepare_storyboard 的 tts_path
      └─ 从本期下载的正文实拍视频帧随机选底图，再由 generate_cover_image 保留原封面叠字样式
      └─ generate_shot.generate_shot_from_intro（片头动画 + 快门音效）
      └─ 黄金钩子图层：字幕位置覆盖 + generate_subtitles 按行生成 hook-title-N.ass（字魂群英体 165px，按标点断行，单行红字黑边 / 多行首行黄黑边其余红白边，\pos 堆叠）
      └─ generate_final_video
      └─ 成片成功后 cloudflare_data.mark_finance_copy_used

finance_poll_task(task_path)
└─ core.mcp._task_runner.poll_task

finance_clear_run
└─ clear_cache.clear_run
```

## 内部模块

| 文件 | 职责 |
| --- | --- |
| `tools/prompts.py` | 标题标签 Prompt、分镜规则（按素材策略选文件）读取与拼装 |
| `tools/save_draft.py` | 稿件读写、品牌替换后正文的断行与标签校验 |
| `tools/parse_metadata.py` | 标题标签格式校验 |
| `tools/storyboard.py` | TTS、timeline 与分镜解析（IMAGE / VIDEO 两种行标记） |
| `tools/narration.py` | 旁白切句与字幕显示（去句尾标点） |
| `tools/prepare_shot_images.py` | 按 image_config 准备镜头图 |
| `tools/generate_qwen_shot_images.py` | 逐镜头千问生图并登记独立生成图库 |
| `tools/prepare_videos.py` | 正版实拍视频搜索、下载、规范化与磨砂 |
| `tools/assemble_finance_video.py` | 封面、片头、钩子图层与最终合成 |
| `tools/upload_to_r2.py` | 上传成片、封面和生产清单到 R2 |

## 目录

- 缓存：`cache/finance/{run_id}/`
- 成片：`cache/output/finance/run-YYYYMMDD/`，日期为北京时间计划发布日期
- 产物记录：成片成功后自动写入 D1 `production_outputs`
- 千问生成图库：`data/image_library_finance/{连续编号}.png`
- 来源稿件：已收集的财经文案；保存草稿后继续临时占用，成片成功后才永久标记为已使用
- 素材来源清单：实拍视频策略会写出 `cache/output/finance/{run_id}/attribution-comment.txt`
- 图片记录：独立 D1 表 `finance_generated_images`

正文素材按搜索顺序选择宽高至少 1920×1080 的候选；单段不足时最多拼接两段，合计时长必须覆盖镜头。当前站无法满足时搜索下一站，不再调用模型选片。全部站点无法满足时报错。

性能记录：素材清单的 elapsed_seconds 与 timings 记录总耗时、逐镜头下载耗时及缓存命中；成片清单的 performance 记录拼接、时间戳规范化、最终合成耗时与最终成片缓存命中。新镜头已统一为 30 帧，不再额外整片转码规范时间戳。相同输入的最终成片也按签名复用，后续登记失败重试不会重复烧字幕。

下载自动成片：finance_start_download_videos 默认 auto_finish=true，下载后在同一后台任务继续合成并登记产物，最终结果包含 video_path、成片 manifest_path、material_manifest_path、auto_finished=true。production_config 可省略，默认读取统一生产配置；production_source 默认 local_mcp，GitHub 必须传 github_workflow。自动流水线可由 MCP 生成重点句；独立合成仍要求宿主传重点句。仅需要素材时显式传 auto_finish=false。自动合成成功后禁止重复调用独立合成工具。
