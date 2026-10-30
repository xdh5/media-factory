"""消费框架原生消息、工具更新与业务进度流。"""

import json

from langchain_core.messages import AIMessageChunk, ToolMessage

from .diagnostics.redaction import redact
from .diagnostics.tracing import agent_tracing


def tool_event(name, result, status="ok"):
    def artifacts(value):
        if isinstance(value, dict):
            return [path for item in value.values() for path in artifacts(item)]
        if isinstance(value, list):
            return [path for item in value for path in artifacts(item)]
        return [value] if isinstance(value, str) and value.lower().endswith((".mp4", ".webm", ".mov")) else []
    return {"kind": "tool", "name": name, "status": status,
            "payload": {"result": redact(result)}, "artifacts": artifacts(result)}


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
