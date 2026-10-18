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

### 默认：Agent 准备，GitHub Action 执行

主页找剧并发布时，宿主扫描、排序、去重和判断合集覆盖；按需取证仅远程截取短片段，不下载整集。

1. `anime_start_prepare_execution(discovery_path, work_ids, selection_reason)`：冻结来源顺序，仅远程读取第一来源前60秒并转写，返回预览 `manifest_path`。轮询到完成。
2. 宿主根据预览生成一套共用标题、描述和标签；标题、描述、搜索标签和 hashtag 都必须包含“已完结”。封面工具按预计分段数返回独立任务，每张封面自动带 `第N集（共M集）`。
3. `anime_dispatch_github_execution(manifest_path, titles, descriptions, tags, account_group)`：上传执行包和全部分段封面至 R2，启动 main 上的 `publish-anime-youtube.yml`。标题和描述数组各一个元素。授权使用 `ANIME_GITHUB_TOKEN`，也可复用本机 gh 登录。
4. Action 全量下载并核对 ID 和时长；每段拼好并上传完成、取得视频 ID、保存回执、设置该集封面及加入播放列表后，立即拼下一段，不等待 YouTube 转码。全部分段上传完成、取得视频 ID 且回执持久化后写回 D1，立即成功退出，不等待平台转码。回执齐全的重试只补写记录和结果，不重复下载、拼接或上传；处理中不能导致 Action 失败。上传完成与转码完成分别报告。各段标题自动标明集数，并幂等加入以作品名命名的同一公开播放列表。Action 不配置 LLM、Groq 或生图密钥。账号组目标发生变化、来源不符或播放列表授权不足时停止。
5. 返回执行 ID 和工作流链接，无需宿主持续在线。按需 `anime_get_github_execution_result(execution_id)` 查询；`dispatched` 不等于发布成功。

执行包、失败时生成的下载检查点、完整成片、回执和结果保存在 `runs/anime/executions/{执行ID}/`。正常下载按约15分钟或128MB形成独立块，后台只上传新增块；重跑同一 ID 恢复已提交块后从下一条来源继续。每段成片完成后先持久化并发布，平台回执即时保存，下一段失败时不会重复上传已成功段。已有完整成片时直接恢复，复用回执核验，不重新生成文案或封面。GitHub 诊断 artifact 保存七天，R2 缓存不自动删除。托管 Runner 的磁盘和六小时执行时限仍适用，超限时保留已持久化进度并报告。

Action 所需 Secrets：已有 D1 和 R2 配置、`ANIME_PUBLISHING_CREDENTIALS_JSON`（仅动漫账号组引用的 OAuth 客户端和 refresh token）。不覆盖其他业务共用的发布凭据 Secret。手动运行工作流时可选 `verify_auth_only=true`，只读核验 Secret 的 OAuth、频道身份和上传权限，不下载或发布视频。

### 长视频直发：按时间线拆分

用户直接给出一条或多条长视频链接时，不下载整部视频，只远程读取第一来源开头一分钟：

1. `anime_start_prepare_split_execution(share_texts, series_name, selection_reason)`：`share_texts` 按播放顺序给出同一作品的链接；`series_name` 是作品名，同时作为 YouTube 播放列表名；`selection_reason` 必须写明已完结。工具解析每条链接、远程探测时长，返回预览 `manifest_path`、`split_plan`（总时长、段数、每段区间）和来源原标题描述话题。轮询到完成。
2. 宿主依据来源文案和开头转写编写一套共用标题、描述和标签，规则与主页找剧发布一致；标题、描述、搜索标签和 hashtag 都必须包含“已完结”。封面按 `split_plan` 的段数分别生成，标题自动带 `第N集（共M集）`。
3. `anime_dispatch_github_execution` 同样适用：工具按 `selection.json` 里的 `segmentation=duration-split-v1` 生成版本 3 执行包并触发同一工作流。
4. Action 全量下载后按时间线均分成每段不超过三小时，逐段上传、设置封面并加入 `series_name` 播放列表。不同作品分别执行一次，各自进入各自的合集。

段数按总时长除以三小时向上取整，各段等长；切点可以落在来源中间，优先关键帧无损裁切，偏差过大才转码该段。

### 用户指定已有本地完整成片

用户明确授权发布时，调用 `anime_start_transcribe_intro(manifest_path)`，抽取第一段成片前60秒并复用 Groq 转写。宿主根据转写生成独立发布文案，不覆盖来源文案。文案确定后调用 `anime_prepare_youtube_thumbnails(manifest_path, titles)`，titles 只传一个共用标题，工具只从第一段抽一帧作为画风参考。宿主查看这一帧后自己一次生成封面，画风与参考帧一致，标题和画面一起出图，再调用 `anime_save_youtube_thumbnails(context_path, images)`。然后调用 `anime_start_publish_youtube(manifest_path, titles, descriptions, tags, account_group)`，逐段即时公开发布到用户指定的动漫账号组，并上传已保存的封面。发布工具不代替宿主生图。目录从项目布局推导，频道身份与凭据引用从数据库和部署环境读取，不预置个人信息。耗时的转写和发布通过 `anime_poll_task` 轮询。封面准备和保存是同步工具。

标题、描述数组各只传一个元素，所有分段共用文案和第一段封面，标题最多100字符，描述最多5000字符；标签预算420字符以内，给平台去重标记留空间。第一段前一分钟未转写时拒绝发布。工具按文件摘要和频道查询发布记录去重，保存本地平台回执并逐段写回 D1；数据库写回失败时重试复用回执。新增工具尚未在客户端加载时，可用 `ops/anime/run_mcp_tool.py` 通过 MCP stdio 调用。

账号组预检使用 anime_get_production_config：显式账号组优先，其次 ANIME_ACCOUNT_GROUP，最后自动选择数据库中唯一启用且包含 YouTube 成员的动漫组。发布工具允许省略账号组并复用此解析逻辑；多个候选或无可用组时返回候选信息。Docker 调用先加载采集库配置再补充工厂配置，保留显式环境变量，避免同一主页在不同入口使用不同 Cookie。

发布标题与描述均加入适用的观看和类型关键词“一口气看完、完整全集、超长合集、爽文”，不能只放在标签中。完整全集须确认无缺集且已完结，否则改用已更新合集或持续更新；超长合集与爽文须符合实际长度和剧情类型。这些文案关键词允许使用，仍不披露具体时长、拼接过程和来源信息。

标题先写剧名与剧情钩子，最后追加【一口气看完｜完整全集｜超长合集｜爽文】，不得前置关键词影响正文。描述底部也加入 #一口气看完 #完整全集 #超长合集 #爽文；正文、后缀和 hashtag 分别核对适用条件及用户对当前作品的明确要求。

别名与缺集判断由宿主 LLM 综合完整扫描标题执行，关键词只作候选整理。人物姓名替代称谓、改名、错字或仅集号标题均须保留排查。报告缺集前回查完整列表里的缺号及相邻发布时间；重复号需区分误标、补发和不同版本。文字证据不足时只取必要短片段，未核实候选标记待核对；选片原因记录别名证据和未解决缺号。


Action 按约15分钟或128MB形成独立检查点块，在完整来源结束后判断阈值。最多一个后台块加一个当前批次，后台仅上传新增块，上传落后时等待。视频上传成功后提交 block-checkpoint.json；已提交块替代本地原片。重跑恢复已提交块继续下载，普通错误补存尾批次；突然终止只能恢复已提交进度。最终统一拼接，参数一致时仅编码分段边界涉及的小块。新版成功任务登记检查点3天、成片7天的保留计划，由每日 GitHub 清理任务执行；执行包、回执和结果保留，历史文件与失败任务不自动删除，不迁移旧检查点。
