# 统一视频发布 MCP

启动入口：

```bash
python -m core.mcp.publishing
```

## 发布规则

- 必须明确 `business_line`：`finance` 或 `language_learning`。
- 必须明确本地产物的计划发布日期 `publish_date`；没有日期时必须先询问用户。
- 优先读取 D1 `production_outputs` 中仍存在的 `source=local_mcp` 成片；本地缺失时自动把 `source=github_workflow` 的 R2 成片拉回发布缓存。
- 语言学习中文传 `content_kind="en-zh"` 时，同时发布原版 `en-zh` 和问答版 `en-zh-quiz`。
- 语言学习韩语传 `content_kind="en-ko"` 时，同时发布原版 `en-ko` 和问答版 `en-ko-quiz`。
- 平台支持 YouTube、Facebook、Instagram、TikTok、快手、抖音、头条号和视频号。
- `publish_mode=immediate` 时必须明确传 `publish_at=now`；`publish_mode=scheduled` 时必须传带时区的未来 ISO 8601 时间。media-publisher 的抖音、快手、头条号和视频号预约必须由平台官方确认，应用内定时任务不得视为成功。

财经省略发布时间时由公共发布层排北京时间 14:00、18:00 各一篇；只有一篇时排 18:00。当日 14:00 已过时，只安排第二篇在 18:00 发布；两个时段都过期时返回错误，不自动补发。明确只指定 18:00 时只安排一篇，优先第二篇；其他单个预约时间也只安排一篇。明确立即发布仍按用户选择执行。预检返回 `default_publication_plan` 和 `default_schedule_skipped`，实际结果的 `publication_plan` 逐篇列出时间。
- 多平台时间不一致时传 `publish_at_by_platform`；每个值使用 `now` 或带时区的未来 ISO 8601。没有单独配置的平台回退到 `publish_mode` 与 `publish_at`。
- 发布前查询 `publication_records`；相同产物、平台、账号和分段已有记录时跳过。
- 指定单条成片时，预检和发布都传入同一个 `production_id`，避免立即发布同日其他内容。标题使用产物记录，发布文案和封面按分片目录读取，不挪动已有本地视频。
- 每个平台成功发布或成功预约后立即写入 D1，部分平台随后失败也不会丢失前面已经成功的记录。
- Facebook、Instagram、TikTok 需要公网视频地址时，才把本地产物上传 R2 并补充原 `production_outputs` 记录。

## 工具

每轮发布先检查本次所有目标账号。检测异常立即通知用户并展示可用登录入口；只有 `publishing_list_account_groups` 返回 `all_accounts_ready=true` 才先用醒目粗体通知“全部账号已登录，开始发布”，随后自动继续。账号未全部通过前不恢复成片、不上传。发布中需要扫码、验证码或其他用户操作时立即提示。

发布任务在后台串行执行，排队时返回等待状态。登录预检只覆盖本次账号组和选定的平台，使用实际发布时的会话分区、代理和 UA 打开发布页，不上传文件。上传控件就绪为 `connected`，登录页或登录二维码为 `login_required`，页面加载或检测失败为 `error`；后者不能当成过期并要求扫码。抖音、快手和视频号扫码成功后也需要真实发布页验证通过。发布页面连续五分钟无进展时结束并释放浏览器，进度仍在变化时继续等待。超时或渲染进程退出属于结果待核对，先检查平台作品管理再决定是否重发。

- `publishing_list_account_groups`：按 `business_line`、`account_group`、`platforms` 筛选，只并行检测本次使用的浏览器账号。返回真实检测结果和 `checked_at`，默认摘要，`detailed=true` 返回完整字段。
- `publishing_preview`：先验证账号，再并行读取产物和重复项。账号未通过时立即返回原因及明确需要扫码的账号，不启动 R2 成片恢复。正式发布在五分钟内复用产物，账号仍重新经过预检；只有成功的真实页面检测可在三十秒内复用，扫码后清除。正式上传前也再次验证页面。返回精简清单及各阶段耗时。
- `publishing_start_login`：抖音、快手、头条或视频号登录失效时启动扫码，并返回二维码图片路径。
- `publishing_login_status`：轮询扫码结果；等待中继续返回二维码，成功后重新预检或发布。
- `publishing_start_publish`：启动后台发布任务。
- `publishing_poll_task`：将上次的 `revision` 传为 `after_revision` 并设置 `wait_seconds=25`，在服务端等待状态变化，减少无变化时的工具往返。默认省略堆栈和重复明细，`detailed=true` 读取完整任务。结果包含预检与各条发布耗时。
- 账号摘要只在 `login_states` 返回各账号状态，预检摘要不重复列出已由排期和去重计数表达的任务清单；需要原始结构时传 `detailed=true`。
- 视频号上传进度为 0% 连续 90 秒、中途进度连续 180 秒、平台处理连续 300 秒无变化时结束该项并报错；页面已关闭时立即停止等待。进度持续推进时保留大文件上传时间。
- 用户指定首日结束即停时，不启动后续日期或自动补发。观察数据记录阶段耗时、工具调用次数和响应文本量，不将响应文本量冒充实际 token 账单。

## 工程分层

| 目录或文件 | 职责 |
| --- | --- |
| `__main__.py` | stdio 启动入口，不承载业务逻辑 |
| `server.py` | 创建 FastMCP 并注册工具 |
| `tools/` | MCP Tool 注册层 |
| `workflows/` | 账号预检、扫码登录、发布和后台任务编排 |
| `errors/` | MCP 领域错误与错误映射 |
| `config/` | 服务说明、缓存路径和 MCP 标识 |
| `infrastructure/` | 后台任务、D1 与通用发布服务适配入口 |
| `core/tools/publish_media/` | 选片、去重、R2 公网地址和发布记录。平台发送调用矩媒 `publishing` |
| `integrations/media-publisher/python/publishing/` | 账号组、预约时间和各平台发布参数的唯一实现。两个发布 MCP 都调用它 |
| `integrations/media-publisher/python/platform_api/` | YouTube、TikTok、Instagram、Facebook 的官方接口 |

当前没有独立只读 Resource 和可复用 Prompt，因此不创建空的 `resources/`、`prompts/` 目录。业务服务已经由 `core/tools/publish_media/` 提供，不在 MCP 内复制一套 `services/`。
