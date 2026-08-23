---
name: douyin-research
description: 使用项目抖音研究 MCP 按用户给定关键词搜索抖音、下载候选视频、转写并在确认后分类入库；适用于“抖音搜索”“爬抖音关键词”“找抖音前几名视频”等请求，即使请求中同时出现财经或其他内容分类。
---

# 抖音内容研究

只通过 `douyin_research` MCP 完成业务流程，禁止改用财经选题、网页搜索或自行总结来代替抖音搜索。

## 参数语义

- `keyword`：用户要求在抖音搜索框中搜索的原始关键词，不得扩写、概括或与分类拼接。
- `collection_name`：用户指定的数据库分类中文名，只在确认入库时用于归类。
- `collection_code`：分类的稳定英文编码。已知映射：`财经` → `finance`，`心灵鸡汤` → `inspiration`。新分类使用简短的小写英文编码，并保留用户给出的中文分类名。
- `limit`：用户未指定时固定为 `5`。

例如用户说“抖音搜索关键词财商认知，财经分类”，必须调用搜索工具并传：

```json
{
  "keyword": "财商认知",
  "collection_code": "finance",
  "collection_name": "财经",
  "limit": 5
}
```

这里实际搜索的只有“财商认知”；“财经”不参与搜索，也不调用财经 MCP 的话题去重。

## 流程

1. 调用 `douyin_research_start_search`，再用其返回的 `task_path` 轮询 `douyin_research_poll_task`，直到 `done=true`。不得重复启动同一搜索。
2. 宿主 Agent 只修正候选转写中的明显错别字并补充标点，不得改写原意。
3. 调用 `douyin_research_review_transcripts` 保存全部修订文本，然后只向用户展示编号和修订后的文字；不展示作者、时间、原文案或链接。
4. 用户明确确认候选编号后，调用 `douyin_research_commit`。只有这一步才把内容和分类关系写入 D1。

如果 MCP 未连接、退出或调用失败，报告具体错误并停止，禁止用其他搜索或内部函数绕过。
