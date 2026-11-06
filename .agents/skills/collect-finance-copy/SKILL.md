---
name: collect-finance-copy
description: 管理财经作者，或采集泛认知觉醒与成长励志类抖音口播并定稿入库。
---

# 采集财经文案

1. 用 `finance_manage_authors` 管理作者，可传主页或分享口令，显示名可选。
2. 用 `finance_start_collection` 按 `share_text` 采单条或按 `count` 分配作者配额。用 `finance_get_task` 取待审稿和审核提示。
3. 按返回提示筛主题、校对并定稿。用 `finance_get_inventory` 和 `finance_manage_drafts` 查话题。编辑未使用旧稿用 `finance_manage_drafts(action="save")`；素材不足留待编辑。
4. 用 `finance_finalize_collection` 一次提交整批。继续处理 `continuation`，直至配额补齐或候选用尽。单条不合格时请用户换稿。
5. 报告入库、各作者取稿、弃稿和失败数。累计弃稿率、原因及来源见 `finance_get_inventory.collection_review`。
