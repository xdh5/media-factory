---
name: publish-korean
description: 使用统一发布 MCP 把指定计划发布日期的韩语学习成片发布到指定账号组；适用于“发布韩语视频”“把某天韩语内容发出去”等请求，不用于中文学习视频或生产视频。
---

# 发布韩语视频

使用 `publishing` MCP，传 `business_line="language_learning"`、`content_kind="en-ko"`，由 MCP 同时选择原版与问答版。产物查找、R2 恢复、去重、账号路由和记录写入交给 MCP，不直接运行发布脚本。

## 用户信息与默认时间

- 必须明确产物计划发布日期 `publish_date`，不能默认今天或根据当前目录猜测。
- 账号组与平台必须明确，并通过 `publishing_list_account_groups` 核实，传 `business_line="language_learning"`、`account_group="korean"`，使用默认摘要。韩语成片的账号组名称是 `korean`。
- 用户只指定某天发布时，以该日北京时间 16:00 为目标；尚未到该时刻则预约，已到或超过则立即发布。
- 用户明确指定其他具体时间时遵从其要求；明确要求现在发送时立即发布。

## 执行与交付

1. 调用 `publishing_preview`，检查待发布的原版、问答版及数据库重复项。没有可发布内容时说明原因并停止。
2. 根据上述时间规则调用 `publishing_start_publish`，用 `publishing_poll_task` 每 15～30 秒轮询同一任务至完成，回传上次 `revision` 作为 `after_revision`，只展示状态变化；客户端超时不重复启动。预检和轮询保持默认摘要，只有诊断具体问题时才读取 `detailed=true`。
3. 登录检测失败时按 MCP 返回值恢复。抖音、快手、头条或视频号需要扫码时，调用登录工具；二维码不能只留在工具输出，必须用 `qr_path` 展示 Markdown 图片并附可点击文件链接。轮询扫码成功后重新预检再发布。
4. 展示逐平台成功、预约或失败结果，不重复手工入库。
5. 查找工具时只筛选 `publishing` 名称，先输出名称，再读取所需工具说明，不输出其他业务线的工具描述。
