"""LangSmith 原生追踪配置，上传前对输入输出、异常和元数据脱敏。"""

from functools import lru_cache
import os

from dotenv import load_dotenv
from langsmith import Client, tracing_context

from ..settings import ROOT
from .redaction import redact


def tracing_settings():
    load_dotenv(ROOT / ".env", override=False)
    return {
        "enabled": os.getenv("LANGSMITH_TRACING", "false").lower() == "true",
        "configured": bool(os.getenv("LANGSMITH_API_KEY")),
        "project": os.getenv("LANGSMITH_PROJECT", "media-factory"),
        "url": "https://smith.langchain.com",
    }


@lru_cache(maxsize=1)
def langsmith_client():
    tracing_settings()
    if not os.getenv("LANGSMITH_API_KEY"):
        raise ValueError("请先配置 LANGSMITH_API_KEY；启用任务追踪还需设置 LANGSMITH_TRACING=true")
    return Client(anonymizer=redact)


def agent_tracing():
    settings = tracing_settings()
    return tracing_context(enabled=settings["enabled"], project_name=settings["project"],
                           client=langsmith_client() if settings["enabled"] else None)
