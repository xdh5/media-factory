# 财经 MCP

编排入口：`python -m core.mcp.finance`。

财经 Skill 提供数据库原稿改编规则等业务参数；标题标签与分镜 Prompt 在 `core/mcp/finance/prompts/`。完整流程见 `.agents/skills/finance/SKILL.md`。

## 工具编排

```
finance_get_source_script
└─ cloudflare_data.reserve_douyin_research_script
   └─ 从财经分类选择未使用原稿并临时占用

finance_get_metadata_prompt
└─ tools.prompts.build_metadata_prompt
   └─ prompts/metadata.md

[Agent 按 Skill 保留黄金钩子和原结构，把数据库原稿改为约 500 字，再按 metadata_prompt 写标题标签]

finance_save_draft(...)
└─ topic_dedup.get_topic 查重；暂不写 D1
└─ tools.save_draft.save_draft
   └─ tools.parse_metadata.parse_metadata
└─ cloudflare_data.mark_douyin_research_script_used
   └─ 保存成功后将来源原稿标记为已使用

finance_get_topics
└─ topic_dedup.get_topic（兼容保留，新流程不作为第一步）

finance_prepare_storyboard(draft_path, tts_config)
└─ tools.storyboard.prepare_storyboard  （同步，易超时）

finance_start_storyboard(...)
└─ core.mcp._task_runner.submit_task
   └─ tools.storyboard.prepare_storyboard

finance_poll_task(task_path)
└─ core.mcp._task_runner.poll_task

finance_start_upload_r2(manifest_path, run_id)
└─ core.mcp._task_runner.submit_task
   └─ tools.upload_to_r2.upload_finance_assets_to_r2

[Agent 按 storyboard_prompt 写分镜 IMAGE 行，并按财经 Skill 为每句写 SUB 字幕重点]

finance_prepare_images(..., image_config)
└─ tools.prepare_shot_images.prepare_shot_images
   └─ local_library → generate_image.list_local_images
   └─ qwen_reference → 每个镜头建立独立任务并附带用户参考图

finance_start_generate_images(context_path)
└─ core.mcp._task_runner.submit_task
   └─ tools.generate_qwen_shot_images.generate_qwen_shot_images
      └─ generate_image.generate_qwen_image（逐任务）
      └─ cloudflare_data.commit_finance_generated_images
      └─ data/image_library/finance_generated/{run_id}/

finance_save_images
└─ generate_image.save_agent_image_tasks

finance_submit_images
└─ generate_image.submit_agent_image_tasks

finance_finish_video(..., production_config)
└─ tools.assemble_finance_video.finish_finance_video  （同步，易超时）

finance_start_finish_video(...)
└─ core.mcp._task_runner.submit_task
   └─ tools.assemble_finance_video.finish_finance_video
      └─ 复用 prepare_storyboard 的 tts_path
      └─ generate_cover_image
      └─ generate_shot.generate_shot_from_intro
      └─ generate_final_video

finance_poll_task(task_path)
└─ core.mcp._task_runner.poll_task

finance_clear_run
└─ clear_cache.clear_run
```

## 内部模块

| 文件 | 职责 |
| --- | --- |
| `tools/prompts.py` | 标题标签 / 分镜 Prompt 读取与拼装 |
| `tools/save_draft.py` | 稿件读写与封面断行校验 |
| `tools/parse_metadata.py` | 标题标签格式校验 |
| `tools/storyboard.py` | TTS、timeline 与分镜解析 |
| `tools/prepare_shot_images.py` | 按 image_config 准备镜头图 |
| `tools/generate_qwen_shot_images.py` | 逐镜头千问生图并登记独立生成图库 |
| `tools/assemble_finance_video.py` | 封面、片头、成片合成 |
| `tools/upload_to_r2.py` | 上传财经成片、封面和发布清单到 R2 |
| `tools/narration.py` | 旁白切句与字幕显示 |

## 目录

- 缓存：`cache/finance/{run_id}/`
- 成片：`outputs/finance/{run_id}/`
- 千问生成图库：`data/image_library/finance_generated/{run_id}/`
- 话题库：通过 `CLOUDFLARE_DATA_API_URL` 指向的鉴权 Worker 访问 Cloudflare D1
- 来源稿件：抖音研究数据库“财经”分类；占用两小时后自动过期，保存稿件成功后永久标记已使用
- 稿件：保存后直接制作，不设置稿件确认门禁
- 图片记录：独立 D1 表 `finance_generated_images`，编号从 1 开始并跨运行持续递增
