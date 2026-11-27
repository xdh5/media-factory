"""复用项目数据 API 鉴权和错误，不直接连接 Cloudflare 管理接口。"""

from tools.database.client import _request


def knowledge_request(operation: str, **body) -> dict:
    """所有知识操作均由受鉴权 Worker 执行。"""
    return _request("POST", f"/v1/knowledge/{operation}", body=body)
