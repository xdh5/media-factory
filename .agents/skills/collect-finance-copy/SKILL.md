---
name: collect-finance-copy
description: 管理采集作者，采集跨领域认知提升口播，审核并完成大鹅文案与分镜定稿。
---

# 采集认知提升文案

频道面向普通人，涵盖情绪、关系、职场、家庭、人生及通俗财富与商业认知。按全文是否帮助观众理解问题、改善判断和行动选稿，不按领域或关键词一刀切；专业财经与项目变现教学不作为主体。

1. 用 `finance_manage_authors` 管理作者，可传主页或分享口令，显示名可选。
2. 用 `finance_start_collection` 按 `share_text` 采单条或按 `count` 分配作者配额，再用 `finance_get_task` 读取待审原文和提示词。
3. 依次执行返回的 `prompts.review`、`prompts.rewrite`、`prompts.metadata`、`prompts.storyboard`，分别负责选题审核、校对与改写、标题标签及封面文字、分镜。弃稿不继续定稿；全部内容判断和生成由宿主 Agent 完成。
   选题通过后，先校对原始转写：逐字记录插入广告到 `ad_segments` 并删除，没有则填空数组；补标点，纠正错字、同音误识和人名误识，清理开头冗余称呼，保留事实、数字、论证、例子和顺序，将校对稿保存为 `text`，再交给改写提示词。
   将改写结果的主题、正文分别放入 `editorial.topic`、`editorial.article`。根据改写提示词重写黄金钩子，放入 `editorial.source_hook`，须与正文开头一致且不包含开场白；从 `text` 连续摘录与该主题相关的原文片段到 `editorial.db_source_hook`，只用于来源核对，不要求与新钩子逐字对应。将实际品牌替换按 `from`、`to` 记录到 `editorial.replacements`，没有则填空数组。
   将改写与发布文案字段合并为 `editorial`，分镜文本放入 `editorial.storyboard`，随正文一起提交入库。生产 workflow 直接读取关键词搜索；选择生图时，由制作技能领取图片任务并应用独立的生图提示词。
   将发布文案结果中的完整标题、短标题、标签、封面断行和重点字分别放入 `editorial.title`、`editorial.short_title`、`editorial.hashtags`、`editorial.cover_lines`、`editorial.cover_highlights`；后三项为数组，标签不带井号。
4. 用 `finance_get_inventory` 查询话题，用 `finance_manage_drafts` 查看未使用定稿。重编旧稿以原始转写为底稿，遵循相同文案和分镜规范；通过 `finance_manage_drafts(action="save")` 保存。
5. 用 `finance_finalize_collection(context_path, reviews)` 一次提交当前全部待审作品，每篇包含 `aweme_id`、`kind`、`reason`、`text`，`kind` 只用 `keep`（要稿）或 `skip`（不要稿）；合格稿另含 `ad_segments` 和完整 `editorial`，弃稿 `text` 为空且不填写 `editorial`。继续处理 `continuation`，直至配额补齐或候选用尽；单条不合格时报告原因。
6. 报告入库、各作者取稿、弃稿和失败数。累计弃稿率、原因及来源见 `finance_get_inventory.collection_review`。

内容要求在 MCP 对应阶段提示词维护，业务字段组装和提交步骤在本技能维护。编辑旧稿时读取项目内 `mcp/finance/prompts/editorial-rewrite.md`、`editorial-metadata.md` 和 `editorial-storyboard.md`。
