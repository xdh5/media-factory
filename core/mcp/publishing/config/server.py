"""统一发布 MCP 服务配置。"""

SERVER_NAME = "media-factory-publishing"

SERVER_INSTRUCTIONS = (
    "统一视频发布 MCP。必须明确业务线、产物计划发布日期、账号组、平台和发布方式。"
    "立即发布使用 immediate + now，预约发布使用 scheduled + 带时区的未来 ISO 8601 时间。"
    "优先使用本地产物，本地缺失时允许从 GitHub Workflow 的 R2 产物恢复。"
    "先检查本次账号组和目标平台的真实发布页，全部通过后才恢复成片或发布。"
    "Cookie 存在不代表登录有效；login_required 才需要扫码，检测失败不可说成账号过期。"
    "账号异常立即通知并提供登录入口；all_accounts_ready=true 后先用醒目粗体提示全部账号已登录，开始发布，再自动执行。"
    "发布前查询 publication_records 去重，成功或预约成功后逐条写回数据库。"
    "抖音、快手、头条或视频号登录失效时返回二维码，并轮询扫码结果。"
    "耗时发布必须调用 publishing_start_publish，再用 publishing_poll_task 轮询。"
    "财经未指定时间时默认北京时间14点、18点各一篇；只有一篇或14点已过时只排18点一篇。"
    "财经仅指定一个预约时间时只安排一篇；明确立即发布时使用immediate和now。"
)
