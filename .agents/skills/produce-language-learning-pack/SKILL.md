---
name: produce-language-learning-pack
description: 制作可复用的语言学习预制图包，包含中英和韩英词表及十张透明主体图。
---

# 制作语言学习图包

1. 用 `language_learning_get_topics` 查 `pack_topics`，避开已有主题和本批已选主题。主题用一个英文单词。未指定时自主选题，批量覆盖名词、动词和形容词。
2. 用 `language_learning_prepare_pack` 取提示，生成中英、韩英各 10 词，用 `language_learning_validate_pack_words` 校验。最近 100 天最多重复 5 词；每包入库后重新读取词库再选下一包。
3. 按返回提示生成一张含十个主体的真实 Alpha 透明 PNG。动词和形容词用人物动作或小场景表达。
4. 用 `language_learning_validate_pack_subject_sheet` 切图，查看实际验收图后调用 `language_learning_review_pack_subject_sheet`。缺边或混入相邻主体先重新定位，内容错误才重生。彩色杂边可接受。
5. 验收通过后用 `language_learning_commit_pack` 入库。主题连续修正三次仍失败就换题；服务错误重试一次仍失败，报告原因和完成数。提交结果不明先查入库状态。

图包不需要发布日期，也不占用成片话题。
