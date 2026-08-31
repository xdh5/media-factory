---
name: publish-korean
description: 使用统一发布 MCP 把指定计划发布日期的本地韩语学习成片发布到指定账号组；适用于“发布韩语视频”“把某天韩语内容发出去”等请求，不用于中文学习视频或生产视频。
---

# 发布韩语视频

使用 `python -m core.mcp.publishing`，固定读取 `business_line="language_learning"`、`content_kind="en-ko"` 的本地成片。`content_kind="en-ko"` 会同时发布原版分段和问答版 `en-ko-quiz`，不要只发其中一种。

标题与文件名沿用成片：`韩语｜饺子的韩语怎么说？` 这种格式。作品描述只发 hashtag，不要短标题或其它正文。

发布 MCP 访问 Cloudflare D1 时，优先使用系统 `curl`；仅在系统 `curl` 不可用或无法建立连接时回退到 Python 客户端。不得为此绕过 D1 预检、去重或发布记录写入。

## 日期和时间门禁

- 用户必须说清楚产物计划发布日期 `publish_date`；没有明确日期时必须先追问，禁止默认今天或从当前目录猜测。
- 如果用户只指定“某天发布”，该日统一以北京时间 16:00 为目标：
  - 当前北京时间早于该日 16:00：预约到该日 `16:00:00+08:00`。
  - 当前北京时间已达到或超过该日 16:00：立即发布，使用 `publish_mode="immediate"`、`publish_at="now"`。
- 用户明确给出其他具体时间时遵从用户时间；未来时间使用预约发布，明确要求现在发送时使用立即发布。
- 账号组和平台列表也必须明确。账号组通常是“韩语”，但仍需调用 `publishing_list_account_groups(business_line="language_learning")` 核实，禁止凭名称猜账号路由。

## 执行

1. 调用 `publishing_preview`，传 `business_line="language_learning"`、`content_kind="en-ko"`、用户指定的 `publish_date`、账号组和平台。预检应同时列出原版和问答版。
2. 没有本地成片、缺少账号路由或所有目标已有数据库记录时停止，不得重复发布。
3. 按上面的北京时间 16:00 规则调用 `publishing_start_publish`，并传 `publish_confirmed=true`。
4. 用 `publishing_poll_task` 轮询至完成。MCP 会在每个平台成功发布或成功预约后写入 `publication_records`，不得再次手工记录。
5. MatrixMedia 会在上传前对抖音、快手、百家号、头条号和视频号读取真实发布页；不能只依据 Cookie 或 `connected` 判断登录成功。
6. 真实发布页检测失败时立即停止本次发布：
   - 抖音或视频号：调用 MatrixMedia `login`，抖音必须传 `force=true`；二维码不得只放在工具输出或执行记录中。最终回复必须使用返回的 `qr_path` 写入 Markdown 图片 `![登录二维码](绝对路径)`，并附同一路径的可点击文件链接，然后立即结束当前对话。只有用户明确回复“好了”后才调用 `login_status`，登录成功后重新预检并重试发布。
   - 快手、百家号或头条号：明确报告登录失败，请用户在 MatrixMedia GUI 重新登录；禁止继续等待上传超时或自动重试。
