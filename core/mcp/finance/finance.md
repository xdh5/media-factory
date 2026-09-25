# 财经 MCP

编排入口：`python -m core.mcp.finance`。

财经线是唯一的文章成片线（原心灵鸡汤线已并入删除）；财经 Skill 提供原稿整理规则等业务参数，标题标签与分镜 Prompt 在 `core/mcp/finance/prompts/`。完整流程见 `.agents/skills/finance/SKILL.md`。

## 工具编排

```
finance_get_source_stats
└─ cloudflare_data.get_douyin_research_script_stats
   └─ 只读统计原稿总数、可用数、有效占用数和已使用数

finance_get_source_script
└─ cloudflare_data.reserve_douyin_research_script
   └─ 选择未使用原稿并临时占用

finance_get_metadata_prompt
└─ tools.prompts.build_metadata_prompt
   └─ prompts/metadata.md

[Agent 按 Skill 把原稿整理为正文：三类必做改动（品牌替换、连载指涉改写、错别字修正）+ 措辞级改写但保留大结构与信息，再按 metadata_prompt 写标题标签]

finance_save_draft(...)
└─ topic_dedup.get_topic 查重；暂不写 D1
└─ tools.save_draft.save_draft
   └─ tools.parse_metadata.parse_metadata
└─ cloudflare_data.mark_douyin_research_script_used
   └─ 保存成功后将来源原稿标记为已使用

finance_get_topics
└─ topic_dedup.get_topic

finance_start_storyboard(draft_path, tts_config, material_strategy)
└─ core.mcp._task_runner.submit_task
   └─ tools.storyboard.prepare_storyboard
      └─ prompts/shot_image_rules.md（image_library / qwen_reference）
      └─ prompts/stock_video_rules.md（stock_video）

finance_poll_task(task_path)
└─ core.mcp._task_runner.poll_task

[Agent 按 storyboard_prompt 写分镜行，并为每句原样写 SUB 字幕；成片统一套用黄色 karaoke 逐字扫]

素材策略 A：存量图库 / 参考图生图
finance_prepare_images(..., image_config)
└─ tools.prepare_shot_images.prepare_shot_images
   └─ local_library → generate_image.list_local_images
   └─ qwen_reference → 每个镜头建立独立任务并附带用户参考图
finance_start_generate_images(context_path)
└─ tools.generate_qwen_shot_images.generate_qwen_shot_images
finance_save_images / finance_submit_images
└─ generate_image 保存或提交 Agent 图任务

素材策略 B：正版实拍视频
finance_start_video_search(draft_path, storyboard_text, video_config)
└─ tools.prepare_videos.prepare_video_searches
   └─ stock_video.search_stock_videos（Pexels → Pixabay → Coverr 兜底）
finance_start_download_videos(context_path, selections)
└─ tools.prepare_videos.download_selected_videos
   └─ stock_video.prepare_stock_clip 裁到镜头时长
   └─ soft_blur_video.blur_video_segments 正文素材白蒙版磨砂

finance_start_finish_video(..., production_config, material_manifest_path, intro_image_path?)
└─ core.mcp._task_runner.submit_task
   └─ tools.assemble_finance_video.finish_finance_video
      └─ 按素材清单自动识别策略（images → 图库/生图；videos → 实拍视频）
      └─ 复用 prepare_storyboard 的 tts_path
      └─ generate_cover_image
      └─ generate_shot.generate_shot_from_intro（片头动画 + 快门音效）
      └─ 黄金钩子图层：字幕位置覆盖 + generate_subtitles 按行生成 hook-title-N.ass（字魂群英体 165px，按标点断行，单行红字黑边 / 多行首行黄黑边其余红白边，\pos 堆叠）
      └─ generate_final_video

finance_poll_task(task_path)
└─ core.mcp._task_runner.poll_task

finance_record_publications
└─ cloudflare_data.commit_publication_records

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
| `tools/upload_to_r2.py` | 上传成片、封面和发布清单到 R2 |

## 目录

- 缓存：`cache/finance/{run_id}/`
- 成片：`output/finance/run-YYYYMMDD/`，日期为北京时间计划发布日期
- 产物记录：成片成功后自动写入 D1 `production_outputs`
- 千问生成图库：`data/image_library_finance/{连续编号}.png`
- 来源稿件：抖音研究数据库；占用两小时后自动过期，保存稿件成功后永久标记为已使用
- 素材来源清单：实拍视频策略会写出 `output/finance/{run_id}/attribution-comment.txt`
- 图片记录：独立 D1 表 `finance_generated_images`
