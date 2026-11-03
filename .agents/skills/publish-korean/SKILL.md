---
name: publish-korean
description: 发布或预约韩语学习成片；适用于“发布明天的韩语”“把某天韩语视频发出去”。不制作视频，不发布中文学习内容。
---

# 发布韩语成片

使用 `publishing` MCP，业务线 `language_learning`，内容类型 `en-ko`，同时包含原版与问答版。

## 默认参数

- 账号组：`korean`。
- 平台：该账号组内全部已启用的平台；用户指定平台时只用指定范围。先查配置，不举例猜平台，不要求用户重复提供默认值。
- 日期：按当前时间解析用户指定的“明天、下周二”等；没有日期或表达有歧义时才询问。
- 时间：指定日期的北京时间 16:00；未到则预约，已过则立即发布。用户明确指定时间、时区或立即发布时优先遵从，具体时刻使用带时区 ISO 8601。

## 执行

1. 调用 `publishing_list_account_groups(business_line="language_learning", account_group="korean")`，默认不传 `platforms`，读取真实平台。随后调用 `publishing_start_account_check`，传入本次平台范围，并用 `publishing_poll_task` 查看进度与登录结果。用户指定平台时传该范围。仅在配置缺失或选择确有歧义时询问。
2. 账号需登录时展示账号、平台及二维码或授权入口；检测失败单独说明。全部通过前不恢复成片、不上传、不发布。通过后提示 **全部账号已登录，开始发布**，自动继续。
3. 调用 `publishing_preview` 核对该日期的成片和重复记录；已发布或已预约的跳过，无待发布产物则说明并结束。
4. 单日使用 `publishing_start_publish`，轮询 `publishing_poll_task` 至完成；多日使用 `publishing_start_batch`，每 3 分钟查询 `publishing_batch_status`，直到完成或需要用户处理。
5. 按平台报告真实成功、预约、跳过或失败。登录、验证码和平台限制立即提醒；提交结果不确定时先查回执，不重复发送。

产物查找、R2 恢复、去重和记录写入全部交给 MCP，不执行内部脚本或手工重复入库。
