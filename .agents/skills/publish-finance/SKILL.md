---
name: publish-finance
description: 使用统一发布 MCP 把指定计划发布日期的本地财经成片发布或预约到指定账号组；适用于“发布财经视频”“把某天财经内容发到这些平台”等请求，不用于生产视频。
---

# 发布财经视频

使用 `python -m core.mcp.publishing`，不得直接运行发布脚本或绕过数据库预检。

## 必须确认的信息

发布前必须从用户请求中得到以下信息；缺少任何一项都要先追问：

- 产物计划发布日期 `publish_date`，格式 `YYYY-MM-DD`。这一天用于读取 `output/finance/run-YYYYMMDD/` 对应的已落库本地产物，不是预约时间。
- 账号组。先调用 `publishing_list_account_groups(business_line="finance")` 展示可用名称，禁止猜账号。
- 平台列表。
- 发布方式与时间：立即发布必须由用户明确说“立即/现在”，预约发布必须有具体日期、时间和时区。

平台别名可按用户习惯理解：`ytb/yt`、`fb`、`ig`、`tk`、`ks`，以及抖音、快手、百家号、头条号、视频号。

## 执行

1. 调用 `publishing_preview`，传 `business_line="finance"`、`content_kind="finance"` 和用户确认的日期、账号组及平台。
2. 预检必须显示本地成片、账号路由和数据库重复项；没有可发布内容时停止并说明原因。
3. 用户要求立即发布时调用 `publishing_start_publish`，传 `publish_mode="immediate"`、`publish_at="now"`、`publish_confirmed=true`。
4. 用户要求预约发布时，传 `publish_mode="scheduled"` 和带时区的未来 ISO 8601 `publish_at`，例如 `2026-08-26T18:00:00+08:00`。
5. 用 `publishing_poll_task` 轮询至 `done=true`。逐平台成功或预约成功后 MCP 会立即写入 `publication_records`；不得再手工重复入库。
