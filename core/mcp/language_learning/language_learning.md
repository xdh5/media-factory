# 语言学习 MCP

编排入口：`python -m core.mcp.language_learning`。

TTS、发布账号组与完整流程见 `.agents/skills/learn_Chinese_and_Korean/SKILL.md`。Prompt 模板在 `prompts/`。

## 工具编排

```
language_learning_get_topics
└─ topic_dedup.get_topic
└─ tools.vocabulary_history.list_recent_words（最近 100 天）

language_learning_occupy_topic(topic, learning_modes)
└─ 查重后创建 cache/outputs 目录，返回 run_id；暂不写 D1

language_learning_build_vocabulary_prompt(topic, learning_modes)
└─ tools.vocabulary_prompt.build_vocabulary_prompt
└─ tools.vocabulary_history.list_recent_words
   └─ prompts/vocabulary-user.md

[Agent 按 user_prompt 写词表]

language_learning_parse_vocabulary_response(response_text, learning_modes, topic, run_id)
└─ tools.vocabulary_prompt.parse_vocabulary_response
└─ tools.vocabulary_history.validate_words
   └─ 格式校验后要求 10 个单词中至少 5 个不在最近 100 天词库；暂不写 D1

language_learning_prepare_images
└─ tools.vocabulary_prompt.build_subject_sheet_prompt
   └─ prompts/subject-sheet.md
   └─ generate_image.prepare_agent_image_tasks

language_learning_save_images
└─ generate_image.save_agent_image_tasks

language_learning_submit_images
└─ generate_image.submit_agent_image_tasks  （同步，千问仅作失败兜底生图）

language_learning_start_submit_images
└─ core.mcp._task_runner.submit_task

language_learning_get_visual_validation_prompt
└─ 返回宿主 Agent 检查主题图和定位十个主体所需的 Prompt

[宿主 Agent 按 Prompt 检查主题图并提交十个主体框]

language_learning_validate_subject_sheet
└─ tools.compose_fixed_cards.validate_subject_sheet
   └─ Python 去背景并输出十张抠图

[宿主 Agent 打开十张抠图逐张检查]

language_learning_review_cutouts
└─ 第一次裁坏时要求调整框重抠
└─ 第二次仍坏或源图损坏时要求重新生图
└─ 未全部通过时禁止拼卡

language_learning_compose_cards
└─ tools.compose_fixed_cards.compose_fixed_cards  （同步）

language_learning_start_compose_cards
└─ core.mcp._task_runner.submit_task

language_learning_create_videos
└─ tools.create_vocabulary_videos.create_vocabulary_videos  （同步，易超时）

language_learning_start_create_videos
└─ core.mcp._task_runner.submit_task
   └─ generate_tts
   └─ generate_final_video
   └─ tools.publish_vocabulary_videos.attach_publish_manifest

language_learning_start_upload_r2
└─ tools.publish_vocabulary_videos.upload_publish_assets_to_r2
   └─ 上传成片、主题图与发布清单

language_learning_publish
└─ 兼容旧客户端的同步发布入口

language_learning_start_publish
└─ 后台发布中文 YouTube 与 TikTok，并幂等写入正式话题和十个单词

language_learning_poll_task(task_path)
└─ core.mcp._task_runner.poll_task

language_learning_clear_run
└─ clear_cache.clear_run
```

## 内部模块

| 文件 | 职责 |
| --- | --- |
| `tools/vocabulary_prompt.py` | 词表 / 主体图 Prompt 生成与词表解析 |
| `tools/vocabulary_history.py` | 最近 100 天词库、新词比例校验与历史记录 |
| `tools/compose_fixed_cards.py` | 接收宿主 Agent 主体框、抠图、逐张检查门禁并贴到固定模板单词卡 |
| `tools/create_vocabulary_videos.py` | 卡片 + 双语 TTS → 竖版成片 |
| `tools/publish_vocabulary_videos.py` | 写发布清单、上传 R2，并通过 MCP 发布 YouTube 与 TikTok |

## 目录

- 缓存：`cache/language_learning/{run_id}/`
- 成片：`outputs/language_learning/{run_id}/`
- 话题与单词历史：通过 `CLOUDFLARE_DATA_API_URL` 指向的鉴权 Worker 访问 Cloudflare D1
