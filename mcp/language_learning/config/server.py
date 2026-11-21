"""语言学习 MCP 服务配置。"""

SERVER_NAME = "media-factory-language-learning"

SERVER_INSTRUCTIONS = """图包可直接准备，交互式视频生产须先确认北京时间 publish_date，再占用话题或创建任务。
按 language_learning_get_production_config 和工具回执使用统一提示、配音与生产参数。十个英语词中至少五个在最近一百天未使用。主体图使用真实 Alpha 透明 PNG。
耗时步骤启动后轮询原任务。视频生产只调用 language_learning_start_production，领取词包到 R2 交付全部由 workflow 执行；使用 language_learning_poll_task 查询结果，平台发布走发布服务。"""
