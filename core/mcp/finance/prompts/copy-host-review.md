逐篇校对原始转写、审核广告并完成定稿，再调用 `finance_finalize_collection(context_path, reviews)`。每条填写 `aweme_id`、`kind`、`text` 和简短 `reason`。

- 整篇以推销或导流为目的时，填 `kind=ad`、空 `text`。一般关注提醒、署名和观点表达按全文目的判断。
- 正常稿填 `kind=normal`。将被删的插入广告逐字复制到 `ad_segments`，剩余正文补标点、校正错字后填 `text`。保留原稿结构、事实、数字和例子。
- 正常稿必须提交 `editorial`。按原稿顺序编写 `article`，去除连载指涉，把作者名、账号名、机构名、课程名及外号统一替换为「财富研习岛」，按语义断行，每行最多 36 字。用 `replacements` 记录品牌替换，每项包含 `from` 和 `to`。从 `text` 开头逐字复制黄金钩子到 `db_source_hook`，仅做品牌替换后填 `source_hook`，并用它开篇。
- 补齐 `topic`、`title`（12 至 26 字）、`short_title`（6 至 16 字）、`hashtags`（四个不同的标签，不带井号）、`cover_lines`（一至三行，拼接后与长标题一致）和 `cover_highlights`（取自长标题原文）。
- 提交前逐篇检查软广告和品牌残留，在 `reason` 写明结论。若返回 `continuation`，用 `finance_get_task` 查询并继续审核，直到完成或候选用尽。
