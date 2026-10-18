---
name: collect-finance-copy
description: 使用财经 MCP 收集财经文案：保存单条抖音链接，维护财经作者名单，或按作者平分抓取指定数量的最新口播。适用于“收集财经文案”“把这个抖音链接转写入库”“添加财经作者”“查看作者名单”“抓取100个财经稿件”等请求。不用于制作成片。
---

# 收集财经文案

只通过 `finance` MCP 完成。下载和作者作品列表由该 MCP 调用 media-collector 子仓库，不要改到工厂的 `core/tools`。分类固定为“财经”。用户要求保存或抓取即表示授权下载、转写并写入财经文案库，无需再次确认。

作者名单保存在数据库里，可以随时增加、删除和查看，不是一次性导入。

## 作者怎么提供

每行一位作者。可以贴作者主页，也可以整段贴「查看TA的更多作品」分享口令。需要显示名时，在链接或口令后面加一个空格再写名字。

```text
https://www.douyin.com/user/MS4wLjABAAAA... 显示名
8- 长按复制此条消息，打开抖音搜索，查看TA的更多作品。 https://v.douyin.com/xxxx/ 4@9.com :3pm
```

口令里的短链必须跳到作者主页。不要用单条作品链接代替作者主页。

## 单条链接

1. 调用 `finance_start_collect_copy`，原样传入 `share_text`，并固定传入 `collection_name="财经"`。
2. 使用返回的 `task_path` 调用 `finance_poll_task`，直到 `done=true`。不得为同一请求重复启动任务。
3. 成功后读取 `result.pending` 和 `prompt`，由宿主 Agent 逐篇校对和审核广告，再完成下述定稿，禁止调用外部文本 LLM。正常审核结果必须附带 `editorial`，调用 `finance_submit_copy_reviews(context_path, response_text)` 校验并保存原稿及定稿后才算入库完成。
4. 正常内容中的插入广告填写原文 `ad_segments` 并删除；整篇广告标记 `ad`，不入库。展示最终审核文本、分类及入库结果。

## 作者名单

- 查看：调用 `finance_list_source_authors`，把主页、显示名和人数告诉用户。
- 添加：对用户给出的每一行调用 `finance_add_source_author`。`profile_url` 传主页链接，`display_name` 传显示名；没有显示名就传空字符串。
- 未指定显示名时，工具直接查询作者资料获取昵称并保存，不依赖作品列表；读取失败时保存 `sec_user_id`，同时返回原因。不得将空显示名当作正常结果。
- 删除：先查看名单，确认要删的作者，再调用 `finance_remove_source_author`。`author` 传主页链接或 `sec_user_id`。

添加或删除后再次查看名单，把最新结果告诉用户。

## 按数量抓取

用户说抓取 N 个财经稿件时，调用 `finance_start_collect_author_copies`，`count` 传 N，再用 `finance_poll_task` 轮询至 `done=true`。任务完成只表示原始转写已准备，不表示已经入库；必须由宿主 Agent 校对和审核，再通过 `finance_submit_copy_reviews` 提交。

工具会按当前作者人数平分。例如 100 篇、10 位作者，就是每人取 10 条最新作品。已入库的作品会跳过。宿主提交审核后若 `needs_more=true`，沿用 `context_path` 调用 `finance_start_continue_collect_author_copies`、轮询并继续审核，直到 `completed=true` 或候选作品用尽。整篇广告不入库；正文中间的插入广告由宿主删除。除不尽时，先添加的作者多取 1 篇。

完成后展示入库篇数、每位作者的取稿数量、跳过的重复和广告，以及失败原因。

禁止改用浏览器或临时脚本完成下载、转写或入库。MCP 未连接、进程退出或调用失败时，报告具体错误并停止。作者作品列表需要 `.env` 中的 `DY_COOKIES`，缺少时报告该错误，不要改去抓搜索页。

## 内容定稿

宿主 Agent 在存稿时完成，GitHub Action 直接读取定稿制作。

1. 从校对原稿开头连续复制完整黄金钩子为 `db_source_hook`。调用钩子、正文分段改写、断句、话题、标题标签、封面视觉的现有 Prompt 和校验工具；原稿和定稿分开保存。正文保持结构、顺序、观点、数字及信息量；按措辞级改写规则处理，品牌统一为财富研习岛，改写连载指涉，每行最多36字。品牌替换表放入 `replacements`，处理后的钩子为 `source_hook`。
2. 提供 `topic`、12～26字的 `title`、6～16字的 `short_title`、四个不重复且不带井号的 `hashtags`、一至三行 `cover_lines` 和来自标题的 `cover_highlights`。封面断行拼接必须等于标题。话题结合 `finance_get_topics` 和 `finance_list_editorial_drafts(missing_only=false)` 查重。
3. 正常审核记录格式为 `{"aweme_id":"作品ID","kind":"normal","text":"校对原稿","ad_segments":[],"reason":"审核理由","editorial":{"article":"完整断行正文","db_source_hook":"原文钩子","source_hook":"处理后钩子","replacements":[],"topic":"话题","title":"长标题","short_title":"短标题","hashtags":["标签一","标签二","标签三","标签四"],"cover_lines":["标题第一行","标题第二行"],"cover_highlights":["标题重点词"]}}`。
4. 正常原稿缺少定稿时不能作为生产库存。正文不足以成篇时保留待编辑状态，不扩写编造内容。
5. 定稿提交前逐篇通读，由你自己判断两件事：原稿的推销、导流、拉群、卖课内容是否全部删干净（包括没写进 `ad_segments` 的软植入）；作者名、账号名、机构名、课程名、外号是否全部换成财富研习岛。有残留就改定稿再提交，不要用关键词清单或脚本代替判断。
6. 补齐未使用旧稿使用 `finance_list_editorial_drafts` 只读获取原文，宿主逐篇编辑后用 `finance_save_editorial_drafts(records)` 提交；不得改动已使用稿件。
