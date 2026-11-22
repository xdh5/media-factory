---
name: collect-finance-copy
description: 管理采集作者，采集跨领域认知提升口播，审核并完成大鹅文案与分镜定稿。
---

# 采集认知提升文案

频道面向普通人，涵盖情绪、关系、职场、家庭、人生及通俗财富与商业认知。按全文是否帮助观众理解问题、改善判断和行动选稿，不按领域或关键词一刀切；专业财经与项目变现教学不作为主体。

1. 用 `finance_manage_authors` 管理作者，可传主页或分享口令，显示名可选。
2. 用 `finance_start_collection` 按 `share_text` 采单条或按 `count` 分配作者配额，再用 `finance_get_task` 读取待审原文和提示词。
3. 依次执行返回的 `prompts.review`、`prompts.rewrite`、`prompts.metadata`、`prompts.storyboard`，分别负责选题审核、校对与改写、标题标签及封面文字、分镜。弃稿不继续定稿；全部内容判断和生成由宿主 Agent 完成。
4. 用 `finance_get_inventory` 查询话题，用 `finance_manage_drafts` 查看未使用定稿。重编旧稿以原始转写为底稿，遵循相同文案和分镜规范；通过 `finance_manage_drafts(action="save")` 保存。
5. 用 `finance_finalize_collection(context_path, reviews)` 一次提交当前全部待审作品，每篇包含 `aweme_id`、`kind`、`reason`、`text`，`kind` 只用 `keep`（要稿）或 `skip`（不要稿）；合格稿另含 `ad_segments` 和完整 `editorial`，弃稿 `text` 为空且不填写 `editorial`。继续处理 `continuation`，直至配额补齐或候选用尽；单条不合格时报告原因。
6. 报告入库、各作者取稿、弃稿和失败数。累计弃稿率、原因及来源见 `finance_get_inventory.collection_review`。

具体收录标准、品牌结构、人物命名、字段和分镜格式只在 MCP 对应阶段提示词维护，不在技能中重复定义。编辑旧稿时读取项目内 `mcp/finance/prompts/editorial-rewrite.md`、`editorial-metadata.md` 和 `editorial-storyboard.md`。
