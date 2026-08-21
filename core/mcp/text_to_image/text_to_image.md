# 文生图 MCP

编排入口：`python -m core.mcp.text_to_image`。

各 Skill 提供正文范文等业务参数；标题标签与分镜 Prompt 在 `core/mcp/text_to_image/prompts/`。财经流程见 `.agents/skills/finance/SKILL.md`。

## 工具编排

```
text_to_image_get_topics
└─ topic_dedup.get_topic

text_to_image_get_metadata_prompt
└─ tools.prompts.build_metadata_prompt
   └─ prompts/metadata.md

[Agent 按 Skill 写正文，按 metadata_prompt 写标题标签]

text_to_image_save_draft(...)
└─ topic_dedup.update
└─ tools.save_draft.save_draft
   └─ tools.parse_metadata.parse_metadata

text_to_image_prepare_storyboard(draft_path, user_confirmed, tts_config)
└─ tools.storyboard.prepare_storyboard  （同步，易超时）

text_to_image_start_storyboard(...)
└─ core.mcp._task_runner.submit_task
   └─ tools.storyboard.prepare_storyboard

text_to_image_poll_task(task_path)
└─ core.mcp._task_runner.poll_task

[Agent 按 storyboard_prompt 写分镜 IMAGE 行，并按财经 Skill 为每句写 SUB 字幕重点]

text_to_image_prepare_images(..., image_config)
└─ tools.prepare_shot_images.prepare_shot_images
   └─ local_library → generate_image.list_local_images

text_to_image_save_images
└─ generate_image.save_agent_image_tasks

text_to_image_submit_images
└─ generate_image.submit_agent_image_tasks

text_to_image_finish_video(..., production_config)
└─ tools.assemble_finance_video.finish_finance_video  （同步，易超时）

text_to_image_start_finish_video(...)
└─ core.mcp._task_runner.submit_task
   └─ tools.assemble_finance_video.finish_finance_video
      └─ 复用 prepare_storyboard 的 tts_path
      └─ generate_cover_image
      └─ generate_shot.generate_shot_from_intro
      └─ generate_final_video

text_to_image_poll_task(task_path)
└─ core.mcp._task_runner.poll_task

text_to_image_clear_run
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
| `tools/assemble_finance_video.py` | 封面、片头、成片合成 |
| `tools/narration.py` | 旁白切句与字幕显示 |

## 目录

- 缓存：`cache/text_to_image/{run_id}/`
- 成片：`outputs/text_to_image/{run_id}/`
- 话题库：`data/media_factory.sqlite3`
