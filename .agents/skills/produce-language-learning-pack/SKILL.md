---
name: produce-language-learning-pack
description: 制作可复用的语言学习预制图包，包含中英和韩英词表及十张透明主体图。
---

# 制作语言学习图包

1. 用 `language_learning_get_topics` 查 `pack_topics`。用一个英文单词选题，避开库内和本批重复；批量覆盖名词、动词和形容词。图包无需发布日期。
2. 调用 `language_learning_prepare_pack`，按提示生成中英、韩英词表，再用 `language_learning_validate_pack_words` 校验。每包入库后刷新词库再选下一包。
3. 按提示生成真实 Alpha 透明 PNG。用 `language_learning_validate_pack_subject_sheet` 切图，看实际验收图后调用 `language_learning_review_pack_subject_sheet`。缺边或串格先重新定位，内容错误才重生；允许彩色杂边。
4. 验收通过后用 `language_learning_commit_pack` 入库。提交结果不明先查入库状态。主题修正三次仍失败就换题；服务错误重试一次仍失败时报告原因和完成数。
