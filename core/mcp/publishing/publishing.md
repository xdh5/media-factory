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
- `publish_mode=immediate` 时必须明确传 `publish_at=now`；`publish_mode=scheduled` 时必须传带时区的未来 ISO 8601 时间。MatrixMedia 的抖音、快手、头条号和视频号预约必须由平台官方确认，应用内定时任务不得视为成功。
- 多平台时间不一致时传 `publish_at_by_platform`；每个值使用 `now` 或带时区的未来 ISO 8601。没有单独配置的平台回退到 `publish_mode` 与 `publish_at`。
- 发布前查询 `publication_records`；相同产物、平台、账号和分段已有记录时跳过。
- 每个平台成功发布或成功预约后立即写入 D1，部分平台随后失败也不会丢失前面已经成功的记录。
- Facebook、Instagram、TikTok 需要公网视频地址时，才把本地产物上传 R2 并补充原 `production_outputs` 记录。

## 工具

- `publishing_list_account_groups`：列数据库账号组，并尽量附带 MatrixMedia 本机登录账号。
- `publishing_preview`：只读查看产物、路由和重复项。
- `publishing_start_matrixmedia_login`：抖音、快手或视频号登录失效时启动扫码，并返回二维码图片路径。
- `publishing_matrixmedia_login_status`：轮询扫码结果；等待中继续返回二维码，成功后重新预检或发布。
- `publishing_start_publish`：启动后台发布任务。
- `publishing_poll_task`：轮询后台任务。
