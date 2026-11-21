"""语言完整生产任务的 MCP 接口。"""
from workflows.language_learning.production import start_production


def language_learning_start_production(publish_date: str) -> dict:
    """启动语言生产 workflow，查询返回的 task_path 获取交付结果。"""
    return start_production(publish_date)
