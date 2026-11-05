"""创建 OpenAI 兼容模型，模型调用追踪交给 LangSmith。"""

from langchain_openai import ChatOpenAI

from .settings import llm_configuration


def create_chat_model(settings, usage=None, streaming=False, read_only=False, tools_enabled=True):
    # 状态查询只读取检查点，不需要配置密钥，也不会请求模型。
    configuration = {"model": "checkpoint-reader", "api_key": "checkpoint-reader"} if read_only else llm_configuration()
    return ChatOpenAI(
        **configuration,
        timeout=settings.llm_timeout,
        max_retries=0,
        streaming=streaming,
        stream_usage=True,
        use_responses_api=False,
        model_kwargs={"parallel_tool_calls": False} if tools_enabled else {},
        callbacks=[usage] if usage else None,
    )
