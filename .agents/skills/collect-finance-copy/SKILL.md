---
name: collect-finance-copy
description: 管理采集作者，采集跨领域认知提升口播，审核并完成大鹅文案与分镜定稿。
---

# 采集认知提升文案

频道面向普通人，涵盖情绪、关系、职场、家庭、人生及通俗财富与商业认知。按全文是否帮助观众理解问题、改善判断和行动选稿，不按领域或关键词一刀切；专业财经与项目变现教学不作为主体。

1. 用 `finance_manage_authors` 管理作者，可传主页或分享口令，显示名可选。
2. 用 `finance_start_collection` 按 `share_text` 采单条或按 `count` 分配作者配额，再用 `finance_get_task` 读取待审原文和提示词。
3. 依次执行返回的 `prompts.review`、`prompts.writing`、`prompts.metadata`、`prompts.storyboard`、`prompts.ssml`，分别负责选题审核、原创撰稿、标题标签及封面文字、分镜、配音设计。弃稿不继续定稿；全部内容判断和生成由宿主 Agent 完成。
   选题通过后，先校对原始转写：逐字记录插入广告到 `ad_segments` 并删除，没有则填空数组；补标点，纠正错字、同音误识和人名误识，清理开头冗余称呼，保留事实、数字、论证、例子和顺序，将校对稿保存为 `text`，再交给原创撰稿提示词。
   将原创稿的主题、正文分别放入 `editorial.topic`、`editorial.article`。根据原创撰稿提示词创作黄金钩子，放入 `editorial.source_hook`，须与正文开头一致且不包含开场白；从 `text` 连续摘录与该主题相关的原文片段到 `editorial.db_source_hook`，只用于来源核对，不要求与新钩子逐字对应。将实际品牌替换按 `from`、`to` 记录到 `editorial.replacements`，没有则填空数组。
   将原创稿与发布文案字段合并为 `editorial`，分镜文本放入 `editorial.storyboard`，随正文一起提交入库。生产 workflow 直接读取关键词搜索；选择生图时，由制作技能领取图片任务并应用独立的生图提示词。
   按 SSML 提示词为正文每行生成一个 `<s>` 片段，按顺序保存到 `editorial.ssml` 字符串数组，正文修改时同步更新。音色由 TTS 配置传入，生产直接执行，字幕读取纯文本。
   将发布文案结果中的完整标题、短标题、标签、封面断行和重点字分别放入 `editorial.title`、`editorial.short_title`、`editorial.hashtags`、`editorial.cover_lines`、`editorial.cover_highlights`；后三项为数组，标签不带井号。
4. 用 `finance_get_inventory` 查询话题，用 `finance_manage_drafts` 查看未使用定稿。用户要求重编旧稿时，以校对原稿为参考，按当前原创撰稿和分镜规范处理；通过 `finance_manage_drafts(action="save")` 保存。
5. 用 `finance_finalize_collection(context_path, reviews)` 一次提交当前全部待审作品，每篇包含 `aweme_id`、`kind`、`reason`、`text`，`kind` 只用 `keep`（要稿）或 `skip`（不要稿）；合格稿另含 `ad_segments` 和完整 `editorial`，弃稿 `text` 为空且不填写 `editorial`。继续处理 `continuation`，直至配额补齐或候选用尽；单条不合格时报告原因。
6. 每篇定稿入库后，用 `finance_manage_cover(aweme_id)` 领取文章、长短标题、封面提示词与参考图。宿主使用生图工具参考两张图片，分别整体生成含文字的4:3横版、3:4竖版与16:9宽屏封面，按 `image_requests` 保存三张独立图片。不调用代码排版，不从 Pexels 拼风景；背景由生图工具按文章内容生成。
7. 宿主查看实际成图，分别逐字核对三版长短标题，确认无错字、漏字、乱码，构图、角色及背景符合封面提示词后，用 `finance_manage_cover(aweme_id, image_paths={"landscape": 横版路径, "portrait": 竖版路径, "widescreen": 宽屏路径})` 上传 R2 并登记。标题修改后重新生成封面，未登记封面须报告为未完成，不得宣称已可生产。
8. 报告入库、封面完成、各作者取稿、弃稿和失败数。累计弃稿率、原因及来源见 `finance_get_inventory.collection_review`。

内容要求在 MCP 对应阶段提示词维护，业务字段组装和提交步骤在本技能维护。默认使用项目内 `mcp/finance/prompts/editorial-writing.md`，目标1500～2000字、约六分钟；成片时长以实际TTS为准，不增加代码硬性字数拦截。原有 `editorial-rewrite.md` 保留，仅在用户明确要求按原稿改写时使用；两套撰稿提示词不同时套用。标题与分镜分别遵循 `editorial-metadata.md` 和 `editorial-storyboard.md`。
