---
name: publish-finance
description: 使用统一发布 MCP 把指定计划发布日期的本地财经成片发布或预约到指定账号组；适用于“发布财经视频”“把某天财经内容发到这些平台”等请求，不用于生产视频。
---

# 发布财经视频

使用 `python -m core.mcp.publishing`，不得直接运行发布脚本或绕过数据库预检。

## 必须确认的信息

发布前必须从用户请求中得到以下信息；缺少必填项时要先追问：

- 产物计划发布日期 `publish_date`，格式 `YYYY-MM-DD`。这一天用于读取 `output/finance/run-YYYYMMDD/` 对应的已落库本地产物，不是预约时间。
- 账号组。先调用 `publishing_list_account_groups(business_line="finance")` 展示可用名称，禁止猜账号。
- 平台列表可选。用户未指定平台时，默认使用所选账号组中全部启用且当前可用的平台；用户明确指定平台时只发布到指定平台。
- 发布方式与时间：用户明确说“立即/现在”时立即发布；未指定发布时间时，默认预约到产物计划发布日期北京时间 18:00；用户指定其他时间时按用户要求预约，并使用对应时区。

平台别名可按用户习惯理解：`ytb/yt`、`fb`、`ig`、`tk`、`ks`，以及抖音、快手、百家号、头条号、视频号。

## 执行

1. 首先调用 `publishing_list_account_groups(business_line="finance")` 检查所选账号组的视频号成员。若视频号 `login_status` 为在线，继续发布流程；若登录失效，暂停全部发布，调用 MatrixMedia `login(platform="sph", phone=视频号账号引用)`，把返回的二维码直接展示给用户，并用 `login_status` 轮询。只有扫码结果为 `success` 后才能继续；随后必须重新调用 `publishing_list_account_groups` 刷新账号状态。
2. 用户未指定平台时，从刷新后的账号组成员中读取全部启用且当前可用的平台；用户指定平台时使用其指定列表。调用 `publishing_preview`，传 `business_line="finance"`、`content_kind="finance"` 和确认后的日期、账号组及平台列表。
3. 预检必须显示本地成片、账号路由和数据库重复项；没有可发布内容时停止并说明原因。
4. 用户要求立即发布时调用 `publishing_start_publish`，传 `publish_mode="immediate"`、`publish_at="now"`、`publish_confirmed=true`。
5. 用户未指定发布时间时，使用产物计划发布日期当天北京时间 18:00；用户指定其他时间时遵从用户时间。未来时间传 `publish_mode="scheduled"` 和带时区的 ISO 8601 `publish_at`，例如 `2026-08-26T18:00:00+08:00`。若默认时间已经过去，必须先询问用户是立即发布还是改约未来时间。抖音、快手、百家号、头条号和视频号必须立即上传并使用平台官方预约；禁止创建或接受应用内定时队列结果。
6. 用 `publishing_poll_task` 轮询至 `done=true`。逐平台成功或预约成功后 MCP 会立即写入 `publication_records`；不得再手工重复入库。
