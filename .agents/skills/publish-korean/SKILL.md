---
name: publish-korean
description: 发布或预约指定计划日期的韩语学习成片，包含原版与问答版。
---

# 发布韩语成片

业务线用 `language_learning`，内容类型 `en-ko`（原版和问答版），默认账号组 `korean`。日期缺失或有歧义时询问。默认北京时间 16:00，未到则预约，已过则立即发布；用户指定时刻和时区优先。

1. 用 `publishing_list_account_groups` 选择启用平台，按用户要求限缩范围。按发布 MCP 的规则完成真实登录预检及提示后再继续。
2. 用 `publishing_preview` 核对成片，跳过已发布或已预约项。无待发产物则报告。
3. 单日用 `publishing_start_publish` 并轮询原任务；多日用 `publishing_start_batch`，需要监控时每 3 分钟查 `publishing_batch_status`。
4. 按平台报告结果。需要用户处理时立即提示，提交结果不明先查回执。
