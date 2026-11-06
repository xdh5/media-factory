---
name: collect-finance-copy
description: 管理财经作者，或采集抖音口播并定稿入库。
---

# 采集财经文案

1. 作者名单用 `finance_manage_authors` 查看、增删。作者可提供主页或跳转主页的分享口令，显示名可选。
2. 用 `finance_start_collection` 采集。单条传原始 `share_text`，批量传 `count`，由工具按作者分配。用 `finance_get_task` 查询并读取 `pending`、`prompt`、`context_path`。
3. 按返回的提示逐篇校对、去广告、定稿。整篇广告标记 `kind=ad`；插入广告在 `ad_segments` 逐字记录。保留事实、顺序和信息量，品牌等统一替换为「财富研习岛」。原文钩子连续摘自校对稿，处理后钩子与替换表一致。
4. 定稿每行最多 36 字，长标题 12～26 字，短标题 6～16 字，四个标签不重复且不带井号。封面 1～3 行，拼接等于长标题，重点词从标题取。用 `finance_get_inventory` 和 `finance_manage_drafts` 查话题；素材不足保留待编辑。编辑旧稿用 `finance_manage_drafts(action="save")`，已使用稿件不改。
5. 用 `finance_finalize_collection` 一次提交当前全部审核项。有 `continuation` 就查其任务并审核，直到完成或候选用尽。报告入库数、各作者取稿数、跳过和失败。
