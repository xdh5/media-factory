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

作者主页找剧新增：

- `anime_start_discover(profile_url, series_name, limit=300)`：复用 media-collector 获取抖音主页作品，最多 1000 条；返回发现记录及按发布时间整理的精简元数据，由宿主自主匹配剧名和集序。
- `anime_start_inspect(discovery_path, work_ids, window_starts=None, cover_reason="")`：复用下载、Groq 转写与千问视觉工具，按需转写 45 秒片段；默认起点 5 秒。封面必须最后兜底，先有片段证据并说明原因，不能默认识别全部封面。
- `anime_start_compile_series(discovery_path, work_ids, selection_reason)`：按宿主选定顺序生产，复用取证下载缓存。单个现成合集直接保留原文件（即使超过三小时也不切分）；多个来源仍按三小时上限均分。

主页流程优先依据标题描述、明确集数、发布时间和时长，再比较必要片段口播，最后才识别封面。开头相同不能证明完整合集，需要结合覆盖范围与结尾。部分合集仅与未覆盖分集组合；缺集、未完结、同名版本冲突和扫描上限须明确报告。没有额外的后台文本模型调用；片段转写与封面兜底分别产生 Groq 和千问服务用量。

上述工具都返回后台任务，统一使用 `anime_poll_task` 轮询。原有显式链接入口保持如下：

1. `anime_start_compile(share_texts)`：按数组顺序启动后台拼接，返回 `task_path`。
2. `anime_poll_task(task_path)`：轮询到 `done=true`。成功时 `result.parts` 含每段路径、标题、描述和话题。

完整调用约定见 `.agents/skills/produce-anime-video/SKILL.md`。

## YouTube 发布扩展

用户明确授权发布时，调用 `anime_start_transcribe_intro(manifest_path)`，抽取每段成片前60秒并复用 Groq 转写。宿主根据转写生成独立发布文案，不覆盖来源文案。文案确定后调用 `anime_prepare_youtube_thumbnails(manifest_path, titles)`，工具只抽一帧作为画风参考。宿主查看这一帧后自己一次生成封面，画风与参考帧一致，标题和画面一起出图，再调用 `anime_save_youtube_thumbnails(context_path, images)`。然后调用 `anime_start_publish_youtube(manifest_path, titles, descriptions, tags, account_group)`，逐段即时公开发布到用户指定的动漫账号组，并上传已保存的封面。发布工具不代替宿主生图。目录从项目布局推导，频道身份与凭据引用从数据库和部署环境读取，不预置个人信息。耗时的转写和发布通过 `anime_poll_task` 轮询。封面准备和保存是同步工具。

标题、描述数组与清单分段对应，标题最多100字符，描述最多5000字符；标签预算420字符以内，给平台去重标记留空间。前一分钟未转写时拒绝发布。工具按文件摘要和频道查询发布记录去重，保存本地平台回执并逐段写回 D1；数据库写回失败时重试复用回执。新增工具尚未在客户端加载时，可用 `ops/anime/run_mcp_tool.py` 通过 MCP stdio 调用。
