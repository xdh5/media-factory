# 语言学习 MCP

编排入口：`python -m core.mcp.language_learning`。

固定生产、模型任务 Prompt、自动预检与发布时间参数以本 MCP 返回值为唯一标准；Agent 与 GitHub Runner 只在模型执行主体上不同。

language_learning_get_production_config
language_learning_get_automation_plan
language_learning_get_topic_generation_prompt / language_learning_validate_topic_response

TTS、发布账号组与完整流程见 `.agents/skills/learn_Chinese_and_Korean/SKILL.md`。Prompt 模板在 `prompts/`。

## 工具编排

```
language_learning_get_topics
└─ topic_dedup.get_topic
└─ services.vocabulary.list_recent_words（最近 100 天）

language_learning_occupy_topic(topic, learning_modes, publish_date)
└─ 查重后创建 cache/output 目录，返回按计划发布日期生成的 run_id；暂不写 D1
└─ 重做 D1 已存在的同一期时可显式传 redo_existing_run=true；普通生产保持关闭

language_learning_build_vocabulary_prompt(topic, learning_modes)
└─ services.prompt_service.build_vocabulary_prompt
└─ services.vocabulary.list_recent_words
   └─ prompts/vocabulary-user.md

[Agent 按 user_prompt 写词表]

language_learning_parse_vocabulary_response(response_text, learning_modes, topic, run_id)
└─ services.prompt_service.parse_vocabulary_response
└─ services.vocabulary.validate_words
   └─ 格式校验后要求 10 个单词中至少 5 个不在最近 100 天词库；暂不写 D1

预制词包路径：
language_learning_prepare_pack / language_learning_validate_pack_words
└─ 复用同一套词表 Prompt、解析器和最近 100 天重复规则

[宿主 Agent 生成一张真实 Alpha 透明主题图，并按共用视觉 Prompt 提交十个主体框]

language_learning_validate_pack_subject_sheet
└─ 复用 services.subject_cards.validate_subject_sheet 完成定位和十张主体切图

language_learning_review_pack_subject_sheet
└─ 复用整图视觉验收；未通过时禁止提交词包

language_learning_commit_pack
└─ 只上传通过验收的十张透明主体切图并写入 D1

language_learning_claim_pack / language_learning_start_compose_pack_cards
└─ GitHub Action 领取十张已验收切图后直接拼卡，不再执行首次切图和视觉验收

language_learning_prepare_images
└─ services.prompt_service.build_subject_sheet_prompt
   └─ prompts/subject-sheet.md
   └─ generate_image.prepare_agent_image_tasks

language_learning_save_images
└─ generate_image.save_agent_image_tasks

language_learning_submit_images
└─ generate_image.submit_agent_image_tasks  （同步，千问仅作失败兜底生图）

language_learning_start_submit_images
└─ core.mcp._task_runner.submit_task

language_learning_get_visual_validation_prompt
└─ 返回宿主 Agent 只定位十个主体坐标所需的 Prompt

[宿主 Agent 按 Prompt 提交十个主体框，不做内容质检]

language_learning_validate_subject_sheet
└─ services.subject_cards.validate_subject_sheet
   └─ 硬校验真实 Alpha 透明通道；按十个框输出十张透明主体和一张切图整体验收图

[宿主 Agent 打开十张实际切图组成的整体验收图做一次性验收]
  └─ 先调用 language_learning_get_sheet_validation_prompt，检查数量、切图完整性、文字、水印、画风和透明边缘

language_learning_review_subject_sheet
└─ 缺少真实透明通道或切图验收失败时重做透明图，不允许纯色背景兜底
└─ 未全部通过时禁止拼卡

language_learning_compose_cards
└─ services.subject_cards.compose_fixed_cards  （同步）

language_learning_start_compose_cards
└─ core.mcp._task_runner.submit_task

language_learning_create_videos / language_learning_start_create_videos
└─ 默认同时生成 standard 原版分段和 quiz 倒计时问答版
└─ 问答版倒计时音轨默认 static/sfx/countdown.mp3
└─ services.videos.create_vocabulary_videos
└─ services.publishing.attach_publish_manifest

language_learning_start_upload_r2
└─ services.publishing.upload_publish_assets_to_r2
   └─ 上传成片、主题图与发布清单

平台发布不属于本 MCP；统一调用 `python -m core.mcp.publishing`。

language_learning_poll_task(task_path)
└─ core.mcp._task_runner.poll_task

language_learning_clear_run
└─ clear_cache.clear_run
```

## 工程分层

| 文件 | 职责 |
| --- | --- |
| `__main__.py` | stdio 启动入口 |
| `server.py` | 创建 FastMCP 并注册 Tools |
| `tools/` | Tool 接口注册，不放业务实现 |
| `prompts/` | 词表、透明主题图、定位和切图验收 Prompt |
| `workflows/` | 共用查询、直接制作、预制包、成片交付和后台任务编排 |
| `services/prompt_service.py` | 词表与主题图 Prompt 生成、词表解析 |
| `services/vocabulary.py` | 最近 100 天词库、新词比例校验与历史记录 |
| `services/subject_cards.py` | 透明校验、定位切图、切图验收图和单词卡渲染 |
| `services/videos.py` | 卡片与双语 TTS 合成竖版成片 |
| `services/publishing.py` | 成片交付清单、产物登记和 R2 上传 |
| `errors/` | 领域错误与错误码 |
| `config/` | 服务说明、生产参数、路径和技术常量 |
| `infrastructure/` | D1、R2、生图和后台任务适配入口 |

## 目录

- 缓存：`cache/language_learning/{run_id}/`
- 预制词包验收缓存：`cache/language_learning/packs/{pack_id}/subject-cutouts/`
- 成片：`output/language_learning/run-YYYYMMDD/`，日期为北京时间计划发布日期
- 产物记录：本地成片成功后写入 `source=local_mcp`；GitHub 在 R2 交付成功后写入 `source=github_workflow`；`language_learning_get_production_outputs(publish_date)` 可按日期查询
- 话题与单词历史：通过 `CLOUDFLARE_DATA_API_URL` 指向的鉴权 Worker 访问 Cloudflare D1
