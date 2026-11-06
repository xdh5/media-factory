---
name: publish-korean
description: 发布或预约指定计划日期的韩语学习成片，包含原版与问答版。
---

# 发布韩语成片

使用 `publishing` MCP，业务线 `language_learning`，内容类型 `en-ko`。

## 默认参数

- 账号组 `korean`。平台用该组全部启用的平台；用户指定时只用指定范围。
- 按当前时间解析指定日期；没有日期或有歧义时才询问。
- 默认北京时间 16:00，未到就预约，已过就立即发布。用户指定时间、时区或立即发布时优先遵从；指定时刻使用带时区 ISO 8601。

## 执行

1. 用 `publishing_list_account_groups` 查平台，再用 `publishing_start_account_check` 和 `publishing_poll_task` 检查本次账号。
2. 需登录时展示平台和二维码或授权入口；检测失败单独说明。全部通过前不恢复成片或上传；通过后提示 **全部账号已登录，开始发布**，自动继续。
3. 用 `publishing_preview` 核对成片，跳过已发布或已预约的项目。无待发布产物时说明并结束。
4. 单日用 `publishing_start_publish` 并轮询 `publishing_poll_task`；多日用 `publishing_start_batch`，每 3 分钟查询 `publishing_batch_status`。
5. 按平台报告成功、预约、跳过或失败。需要用户处理时立即提示；提交结果不明先查回执。
