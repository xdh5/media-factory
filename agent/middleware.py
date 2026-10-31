"""媒体业务的执行边界、参数校验与调用回执中间件。"""

import hashlib
import json
import logging

from jsonschema import validate, ValidationError
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import ToolException
from langgraph.errors import GraphBubbleUp
from langgraph.types import interrupt

from .diagnostics.redaction import redact


class BusinessExecutionMiddleware(AgentMiddleware):
    """在框架执行边界处理暂停、预算及跨系统业务回执。"""

    def __init__(self, tools, journal, settings, task_id, usage, knowledge):
        self.mcp_tools, self.journal, self.settings = tools, journal, settings
        self.task_id, self.usage, self.knowledge = task_id, usage, knowledge
        self.diagnoses = {}
        self.definitions = {item["function"]["name"]: item["function"]["parameters"]
                            for item in tools.definitions()} if tools else {}

    def check_pause(self):
        if self.journal and self.journal.paused(self.task_id):
            interrupt({"kind": "pause", "message": "任务已在操作边界暂停"})
            self.journal.clear_pause(self.task_id)

    async def abefore_model(self, state, runtime):
        self.check_pause()
        used_tokens = sum(item.get("total_tokens", 0) for item in self.usage.usage_metadata.values())
        if used_tokens >= self.settings.max_llm_tokens:
            raise RuntimeError(f"本轮模型已消耗 {used_tokens} Token，达到预算阈值，已保留检查点")

    async def aafter_model(self, state, runtime):
        message = state["messages"][-1]
        if isinstance(message, AIMessage) and (message.invalid_tool_calls or
                message.response_metadata.get("finish_reason") == "length"):
            raise RuntimeError("模型返回不完整的输出或工具参数，已停止执行并保留检查点")

    async def awrap_tool_call(self, request, handler):
        self.check_pause()
        call = request.tool_call
        name, arguments = call["name"], call["args"]
        if name not in self.definitions:
            return await handler(request)

        def reply(value):
            failed = isinstance(value, dict) and (value.get("error") or value.get("status") == "failed")
            return ToolMessage(content=value if isinstance(value, list) else json.dumps(value, ensure_ascii=False), tool_call_id=call["id"],
                               name=name, status="error" if failed else "success")

        try:
            validate(arguments, self.definitions[name])
            if name == "finance_submit_copy_reviews":
                for message in reversed(request.state["messages"]):
                    if not isinstance(message, ToolMessage) or not isinstance(message.content, str):
                        continue
                    try:
                        value = json.loads(message.content)
                    except ValueError:
                        continue
                    if not isinstance(value, dict):
                        continue
                    context = value.get("result") if isinstance(value.get("result"), dict) else value
                    if context.get("context_path") != arguments["context_path"] or "pending" not in context:
                        continue
                    expected = {item["aweme_id"] for item in context["pending"]}
                    actual = [item["aweme_id"] for item in arguments["response_text"]["reviews"]]
                    if set(actual) != expected or len(actual) != len(expected):
                        raise ValueError("审核必须一次覆盖当前全部待审作品，不可拆成部分批次")
                    break
        except (ValidationError, ValueError) as exc:
            return reply({"error": str(exc)[:1000]})

        read_only = self.mcp_tools.read_only(name)
        scope = request.state["operation_scope"]
        canonical = json.dumps([scope, name, arguments], sort_keys=True, ensure_ascii=False)
        key = "read:" + call["id"] if read_only else hashlib.sha256(canonical.encode()).hexdigest()
        previous = self.journal.get(self.task_id, key)
        if previous:
            if previous[0] == "done":
                return reply(previous[1])
            if not read_only:
                return reply({"error": "上次操作结果不确定，不重复执行。请使用查询工具核对实际业务回执。",
                              "previous_error": previous[1]})
        self.journal.save(self.task_id, key, "uncertain")
        try:
            response = await handler(request)
        except GraphBubbleUp:
            raise
        except ToolException as exc:
            error = json.loads(str(exc))
            error["diagnostic_context"] = await self.diagnose(error)
            self.journal.save(self.task_id, key, "done", error)
            return reply(error)
        except Exception as exc:
            error = {"error": f"{type(exc).__name__}: {exc}"}
            error["diagnostic_context"] = await self.diagnose(error)
            self.journal.save(self.task_id, key, "done" if read_only else "uncertain", error)
            return reply(error)
        if response.status == "error":
            result = {"error": response.content}
        else:
            result = response.content if isinstance(response.content, list) else json.loads(response.content)
        failed = isinstance(result, dict) and (result.get("error") or result.get("status") == "failed")
        if failed:
            result["diagnostic_context"] = await self.diagnose(result)
        self.journal.save(self.task_id, key, "done", result)
        return reply(result) if failed else response

    async def diagnose(self, error):
        if self.knowledge is None:
            return []
        query = json.dumps(redact(error), ensure_ascii=False)[:4000]
        if any(marker in query for marker in ("JSONDecodeError", "AllocationQuota.", "Free quota exhausted")):
            return []
        if query not in self.diagnoses:
            try:
                self.diagnoses[query] = await self.knowledge.search(query, k=4)
            except Exception as exc:
                logging.getLogger(__name__).warning("故障知识检索失败：%s", redact(str(exc)))
                self.diagnoses[query] = []
        return self.diagnoses[query]
