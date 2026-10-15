---
name: collect-finance-copy
description: 使用财经 MCP 收集财经文案：保存单条抖音链接，维护财经作者名单，或按作者平分抓取指定数量的最新口播。适用于“收集财经文案”“把这个抖音链接转写入库”“添加财经作者”“查看作者名单”“抓取100个财经稿件”等请求。不用于制作成片。
---

# 收集财经文案

只通过 `finance` MCP 完成。下载和作者作品列表由该 MCP 调用 media-collector 子仓库，不要改到工厂的 `core/tools`。分类固定为“财经”。用户要求保存或抓取即表示授权下载、转写并写入财经文案库，无需再次确认。

作者名单保存在数据库里，可以随时增加、删除和查看，不是一次性导入。

## 作者怎么提供

每行一位作者。先写抖音作者主页链接，需要显示名时在链接后加一个空格再写名字。

```text
https://www.douyin.com/user/MS4wLjABAAAA... 显示名
https://www.douyin.com/user/MS4wLjABAAAA...
```

短链也可以，但必须能跳到作者主页。不要用单条作品链接代替作者主页。

## 单条链接

1. 调用 `finance_start_collect_copy`，原样传入 `share_text`，并固定传入 `collection_name="财经"`。
2. 使用返回的 `task_path` 调用 `finance_poll_task`，直到 `done=true`。不得为同一请求重复启动任务。
3. 成功后展示转写文本、分类和入库结果。

## 作者名单

- 查看：调用 `finance_list_source_authors`，把主页、显示名和人数告诉用户。
- 添加：对用户给出的每一行调用 `finance_add_source_author`。`profile_url` 传主页链接，`display_name` 传显示名；没有显示名就传空字符串。
- 删除：先查看名单，确认要删的作者，再调用 `finance_remove_source_author`。`author` 传主页链接或 `sec_user_id`。

添加或删除后再次查看名单，把最新结果告诉用户。

## 按数量抓取

用户说抓取 N 个财经稿件时，调用 `finance_start_collect_author_copies`，`count` 传 N，再用 `finance_poll_task` 轮询至 `done=true`。

工具会按当前作者人数平分。例如 100 篇、10 位作者，就是每人取 10 条最新作品。已入库的作品会跳过，并继续往下取，直到凑够或该作者没有更多作品。整篇广告不入库；正文中间的插入广告会删掉后再入库。除不尽时，先添加的作者多取 1 篇。

完成后展示入库篇数、每位作者的取稿数量、跳过的重复和广告，以及失败原因。

禁止改用浏览器或临时脚本完成下载、转写或入库。MCP 未连接、进程退出或调用失败时，报告具体错误并停止。作者作品列表需要 `.env` 中的 `DY_COOKIES`，缺少时报告该错误，不要改去抓搜索页。
