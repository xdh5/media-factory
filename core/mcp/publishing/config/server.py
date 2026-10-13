"""统一发布 MCP 服务配置。"""

SERVER_NAME = "media-factory-publishing"

SERVER_INSTRUCTIONS = (
    "统一视频发布 MCP。必须明确业务线、产物计划发布日期、账号组、平台和发布方式。"
    "立即发布使用 immediate + now，预约发布使用 scheduled + 带时区的未来 ISO 8601 时间。"
    "优先使用本地产物，本地缺失时允许从 GitHub Workflow 的 R2 产物恢复。"
    "发布前查询 publication_records 去重，成功或预约成功后逐条写回数据库。"
    "抖音、快手、头条或视频号登录失效时返回二维码，并轮询扫码结果。"
    "耗时发布必须调用 publishing_start_publish，再用 publishing_poll_task 轮询。"
)
