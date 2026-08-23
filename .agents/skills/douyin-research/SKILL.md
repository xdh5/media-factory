---
name: douyin-research
description: 使用项目抖音研究 MCP 把用户提供的抖音链接下载、转写并按指定分类直接写入数据库；适用于“把这个抖音链接转写入库”“抖音链接归入财经”等请求。不用于抖音关键词搜索或批量爬取。
---

# 抖音链接入库

用户只需提供抖音分享链接或分享文字，以及一个中文分类名。提供这两个参数即表示授权下载、转写并写入该分类，无需再次确认。

只通过 `douyin_research` MCP 完成业务流程：

1. 调用 `douyin_research_start_ingest`，原样传入 `share_text` 和 `collection_name`。
2. 使用返回的 `task_path` 调用 `douyin_research_poll_task`，直到 `done=true`；不得为同一请求重复启动任务。
3. 成功后向用户展示转写文本、分类和入库结果。

该 MCP 只编排项目 `download`、`transcribe` 和 Cloudflare D1 工具。禁止改用 MediaCrawler、浏览器或临时脚本完成下载、转写或入库。

如果 MCP 未连接、进程退出或调用失败，报告具体错误并停止，不得绕过 MCP 直接调用内部实现或读写数据库。
