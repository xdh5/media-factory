# 预约发布时间已经过去

实际错误类型为 InvalidPublishRequestError，信息为预约发布时间已经过去。

先核对北京时间和产物计划发布日期，不能通过修改历史生产记录绕过校验。如果用户要立即发布，使用 publish_mode=immediate 与 publish_at=now；如果仍需预约，使用 publish_mode=scheduled，提供带时区的未来 ISO 8601 时间。

发布前继续查询现有 publication_records，已发布或已预约成功的目标不能重复发布。所有真正发布操作仍需人工审批。

依据：core/tools/publish_media 中的发布模式、时间校验和现有发布工作流；历史失败任务已记录同一错误。本次未实际发布。
