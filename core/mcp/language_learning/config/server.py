"""语言学习 MCP 服务配置。"""

SERVER_NAME = "media-factory-language-learning"

SERVER_INSTRUCTIONS = (
    "语言学习视频编排 MCP。交互式生产前必须先确认北京时间计划发布日期 publish_date；"
    "日期不明确时禁止占用话题、创建 run、生产或落库。Prompt、TTS、发布账号组和固定生产参数"
    "以 language_learning_get_production_config 为唯一标准，Agent 与 GitHub Runner 必须复用。"
    "每期 10 个英语单词中至少 5 个必须未在最近 100 天使用；本 MCP 只负责生产和产物交付，不执行平台发布。"
    "主题图必须为真实 Alpha 透明 PNG；无法生成透明图时必须报错。"
    "耗时步骤必须使用 start + poll_task 轮询。禁止绕过 MCP 自行读写内部文件。"
)
