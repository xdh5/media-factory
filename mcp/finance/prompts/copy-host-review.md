# 采集审核与定稿提交

你是宿主 Agent，按返回的 `prompts` 分阶段处理每篇 `pending` 原稿：

1. `review`：判断是否符合频道定位，审核广告并校对原始转写。不合格稿到此结束。
2. `copy`：为合格稿编写大鹅口播、标题、标签与封面文字。
3. `storyboard`：根据口播定稿逐行设计分镜。

为当前全部待审作品各提交一条 `reviews`，包含 `aweme_id`、`kind`、`reason`、`text`；合格稿另含 `ad_segments` 和完整 `editorial`，弃稿 `text` 为空且不填写 `editorial`。

调用 `finance_finalize_collection(context_path, reviews)`。返回 `continuation` 时继续查询任务并审核下一批，直到配额补齐或候选用尽。
