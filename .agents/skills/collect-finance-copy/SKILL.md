---
name: collect-finance-copy
description: 管理财经作者，或采集泛认知觉醒与成长励志类抖音口播并定稿入库。
---

# 采集财经文案

1. 用 `finance_manage_authors` 管理作者，可传主页或分享口令，显示名可选。
2. 用 `finance_start_collection` 按 `share_text` 采单条或按 `count` 分配作者配额。用 `finance_get_task` 取待审稿和审核提示。
3. 逐篇通读原始转写，按返回提示筛主题、去广告、校正错字和同音误识、补齐标点并定稿。按句意和口播停顿断行，为每篇单独写标题和内容标签。用 `finance_get_inventory` 和 `finance_manage_drafts` 查话题和参考未使用定稿。编辑未使用旧稿用 `finance_manage_drafts(action="save")`；素材不足留待编辑。
4. 用 `finance_finalize_collection` 一次提交整批。继续处理 `continuation`，直至配额补齐或候选用尽。单条不合格时请用户换稿。
5. 报告入库、各作者取稿、弃稿和失败数。累计弃稿率、原因及来源见 `finance_get_inventory.collection_review`。

重编旧稿以原始转写为底稿，逐篇保留论证、例子、对话轮次和顺序。校正误识、补标点、按口播停顿断行。品牌替换后通读开头和正文，删除重复署名，对话角色保留区分。
