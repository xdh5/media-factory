逐篇审核转写，用 `finance_finalize_collection(context_path, reviews)` 提交全部待审作品。每条填写 `aweme_id`、`kind`、`text` 和 `reason`。

| kind | 判定 |
| --- | --- |
| ad | 整篇以推销或导流为主。普通署名、关注提醒和观点表达按上下文判断。 |
| off_topic | 以投资、经商、行情操作或赚钱实操为主，或与认知觉醒、个人成长、励志、心灵鸡汤、人生感悟及人际、情绪成长无关。财富和创业经历可作例证。 |
| length | 去除插入广告后少于 400 字或多于 1200 字，或须扩写、删核心内容才能定稿。 |
| normal | 合格稿。逐字记录插入广告到 `ad_segments`，校对剩余内容后填 `text`，保留事实、数字、例子和顺序。 |

弃稿的 `text` 留空，`reason` 写实际主旨或字数等具体依据。字数不含标点及空白。

合格稿附 `editorial`：

- `article` 为 700～900 字，每行最多 36 字。只压缩重复铺垫和次要细节，保留结构、观点、顺序和核心事实，去除连载指涉。
- 作者、账号、机构、课程名和外号统一为「财富研习岛」，用 `replacements` 的 `from`、`to` 记录。从 `text` 开头逐字摘录 `db_source_hook`，仅替换品牌得到 `source_hook` 并放在定稿开头。
- 填 `topic`、`title`（12～26 字）、`short_title`（6～16 字）、`hashtags`（四个不同且不带井号的标签）、`cover_lines`（一至三行，拼接等于长标题）和取自长标题的 `cover_highlights`。
- 提交前检查软广告和品牌残留，将结论写入 `reason`。

返回 `continuation` 时，查询其任务并继续审核。
