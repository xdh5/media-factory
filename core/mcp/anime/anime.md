# 动漫拼接 MCP

编排入口：`python -m core.mcp.anime`。

把用户按顺序给出的抖音、快手或其他下载工具已支持的分享链接下载后拼成一条时间线。没有计划发布日期，不上传、不发布。

## 分段

单段最长 3 小时，段与段之间按总时长均分：

| 总时长 | 段数 |
| --- | --- |
| 不超过 3 小时 | 1 |
| 超过 3 小时，不超过 6 小时 | 2 |
| 超过 6 小时，不超过 9 小时 | 3 |
| 更长 | 按每 3 小时向上取整 |

每段时长等于总时长除以段数，因此都不会超过 3 小时。切点可以落在某一条来源视频中间。

## 文案

标题、描述、话题只使用解析结果，不改写。一段里含有多条来源时，按用户给出的顺序逐条保留；话题去重但保持第一次出现的顺序。

## 产物

```text
cache/output/anime/run-*/
├─ sources/       # 按顺序下载的原视频和解析文案
├─ part-1.mp4
├─ part-1.json
├─ part-1.txt
└─ manifest.json
```

## 工具

1. `anime_start_compile(share_texts)`：按数组顺序启动后台拼接，返回 `task_path`。
2. `anime_poll_task(task_path)`：轮询到 `done=true`。成功时 `result.parts` 含每段路径、标题、描述和话题。

完整调用约定见 `.agents/skills/produce-anime-video/SKILL.md`。
