---
name: produce-language-learning-video
description: 制作中英或韩英词汇短视频，使用语言学习 MCP 的生产配置。
---

# 制作语言学习视频

1. 确认北京时间 `publish_date` 后读取 `language_learning_get_production_config`。用 `language_learning_get_topics` 查近期主题，选题校验后用 `language_learning_occupy_topic` 占用，词表用 `language_learning_parse_vocabulary_response` 校验。
2. 按 `language_learning_prepare_images` 的提示生成主体图，保存后提交。生图不可用或达到失败上限时按工具结果处理。
3. 用 `language_learning_validate_subject_sheet` 定位切图，查看验收图后用 `language_learning_review_subject_sheet` 提交判断。缺边或串格先重定位，内容错误才重生，最多生成三次；允许彩色杂边。
4. 按配置拼卡和出片，保留配音、停顿、格式及元数据。用 `language_learning_poll_task` 查原任务，交付成片、标题和标签。
