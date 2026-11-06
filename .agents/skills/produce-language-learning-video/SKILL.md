---
name: produce-language-learning-video
description: 制作中英或韩英词汇短视频，使用语言学习 MCP 的生产配置。
---

# 制作语言学习视频

1. 确定北京时间计划发布日期 `publish_date`；有歧义先问，确认后才占用话题。用 `language_learning_get_production_config` 读取语言方向、配音和成片参数。
2. 用 `language_learning_get_topics` 读近期主题。按主题提示生成并校验，再用 `language_learning_occupy_topic` 占用。按词表提示生成并调用 `language_learning_parse_vocabulary_response` 校验。
3. 按 `language_learning_prepare_images` 返回的提示生成主体图。每张保存后立即启动提交；生图不可用或达到失败上限时按工具返回的流程处理。
4. 按定位提示找十个框，用 `language_learning_validate_subject_sheet` 切图。查看实际验收图后用 `language_learning_review_subject_sheet` 提交结果。切图缺边或混入相邻主体先重新定位；内容错误才重生，每张最多生成三次。彩色杂边可接受。
5. 按语言方向启动拼卡和成片，原样使用配置中的配音、停顿、格式和元数据。用 `language_learning_poll_task` 查同一任务，交付本地成片、标题与标签。
