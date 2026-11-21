---
name: produce-language-learning-video
description: 制作中英或韩英词汇短视频，使用语言学习 MCP 的生产配置。
---

# 制作语言学习视频

1. 确认北京时间 `publish_date`，读取 `language_learning_get_production_config` 和该日期的生产计划。
2. 调用 `language_learning_start_production(publish_date)`。workflow 从已验收库存领取词包，完成拼卡、配音、原版与问答版合成、R2 上传及产物登记。
3. 使用 `language_learning_poll_task` 查询同一 task_path，直至完成；按最终结果交付本地成片、标题、标签和 R2 地址。
4. 库存不足时按 `produce-language-learning-pack` 技能准备词包，再启动该日期的生产。视频生产期间不另行占用主题、制作主体图或手工拼卡。
5. 原版与问答版共用标题；发布记录按产物区分版本。平台发布使用对应发布技能。
