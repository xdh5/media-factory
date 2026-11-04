"""消费框架原生消息、工具更新与业务进度流。"""

import json
import time

from langchain.agents.middleware import AgentMiddleware
from langgraph.config import get_stream_writer
from langgraph.errors import GraphBubbleUp

from langchain_core.messages import AIMessageChunk, ToolMessage

from .diagnostics.tracing import agent_tracing


class ActivityMiddleware(AgentMiddleware):
    """通过框架自定义流发送可观察的执行状态，不增加模型调用。"""

    async def abefore_model(self, state, runtime):
        get_stream_writer()({"kind": "status", "text": "模型思考中…"})

    async def awrap_tool_call(self, request, handler):
        writer = get_stream_writer()
        name = request.tool_call["name"]
        started = time.monotonic()
        writer({"kind": "status", "text": f"正在调用工具：{name}…"})
        try:
            result = await handler(request)
        except GraphBubbleUp:
            writer({"kind": "status", "text": f"工具 {name} 已暂停，等待处理"})
            raise
        except Exception:
            writer({"kind": "status", "text": f"工具 {name} 执行失败（{time.monotonic() - started:.1f} 秒）"})
            raise
        status = "失败" if getattr(result, "status", None) == "error" else "完成"
        writer({"kind": "status", "text": f"工具 {name} 执行{status}（{time.monotonic() - started:.1f} 秒）"})
        return result


def tool_event(name, result, status="ok"):
    def artifacts(value):
        if isinstance(value, dict):
            if value.get("type") == "text":
                try:
                    return artifacts(json.loads(value["text"]))
                except ValueError:
                    return []
            return [path for item in value.values() for path in artifacts(item)]
        if isinstance(value, list):
            return [path for item in value for path in artifacts(item)]
        return [value] if isinstance(value, str) and value.lower().endswith((".mp4", ".webm", ".mov", ".png")) else []
    return {"kind": "tool", "name": name, "status": status,
            "payload": {"result": result}, "artifacts": artifacts(result)}


async def stream_agent(agent, graph_input, config, emit=None):
    with agent_tracing():
        async for mode, value in agent.astream(graph_input, config,
                stream_mode=["messages", "updates", "custom"], durability="sync"):
            if emit is None:
                continue
            if mode == "messages":
                message, metadata = value
                if (metadata.get("langgraph_node") == "model"
                        and isinstance(message, AIMessageChunk) and message.text):
                    await emit({"kind": "token", "text": message.text})
            elif mode == "custom":
                await emit(value)
            elif mode == "updates":
                for update in value.values():
                    if not isinstance(update, dict):
                        continue
                    for message in update.get("messages", []):
                        if not isinstance(message, ToolMessage):
                            continue
                        try:
                            result = json.loads(message.content)
                        except (ValueError, TypeError):
                            result = message.content
                        failed = message.status == "error" or isinstance(result, dict) and (
                            result.get("error") or result.get("status") == "failed")
                        await emit(tool_event(message.name, result, "error" if failed else "ok"))
