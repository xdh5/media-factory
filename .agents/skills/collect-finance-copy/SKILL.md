---
name: collect-finance-copy
description: 管理财经作者，或采集泛认知觉醒与成长励志类抖音口播并定稿入库。
---

# 采集财经文案

1. 作者名单用 `finance_manage_authors` 查看、增删。作者可提供主页或跳转主页的分享口令，显示名可选。
2. 用 `finance_start_collection` 采集。单条传原始 `share_text`，批量传 `count`，由工具按作者分配。用 `finance_get_task` 查询并读取 `pending`、`prompt`、`context_path`。
3. 先通读原始转写。整篇广告标记 `kind=ad`，其他稿件按正文主旨筛选。泛认知觉醒、个人成长、励志、心灵鸡汤、人生感悟，以及从成长角度讲人际关系和情绪心态的稿件都可以收。主题不符填 `kind=off_topic`、空 `text`，写明实际主旨，不改写定稿。通过主题筛选的稿件按返回提示校对、去广告、定稿。插入广告在 `ad_segments` 逐字记录。保留事实、顺序和信息量，品牌等统一替换为「财富研习岛」。原文钩子连续摘自校对稿，处理后钩子与替换表一致。
4. 校对稿以去除标点、空格和换行后的字数计，少于 400 字或多于 1200 字，填 `kind=length`、空 `text`，在 `reason` 写明字数与原因，换稿。定稿控制在 700～900 字，只删重复铺垫和次要细节，保留结构、观点、顺序、核心事实与黄金钩子。太短须扩写、太长须删核心内容才能达标时，同样按字数弃稿。定稿每行最多 36 字，长标题 12～26 字，短标题 6～16 字，四个标签不重复且不带井号。封面 1～3 行，拼接等于长标题，重点词从标题取。用 `finance_get_inventory` 和 `finance_manage_drafts` 查话题；素材不足保留待编辑。编辑旧稿用 `finance_manage_drafts(action="save")`，已使用稿件不改。
5. 用 `finance_finalize_collection` 一次提交当前全部审核项。有 `continuation` 就查其任务并审核，直到补足合格稿件或候选用尽。单条链接主题不符时请用户换稿。报告入库数、各作者取稿数、主题、广告和字数弃稿数及失败。用 `finance_get_inventory` 的 `collection_review` 查看累计弃稿率、原因和作者来源。
