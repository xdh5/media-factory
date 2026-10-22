"""调用 OpenAI 兼容的 Tool Calling 接口。"""

import asyncio
import json
import time
import httpx

from .settings import llm_configuration


class ToolCallingLLM:
    def __init__(self, settings, observer=None, streaming=False):
        self.settings = settings
        self.observer = observer
        self.streaming = streaming
        self._stream_started = False
        self.used_tokens = 0
        self.stream_usage = {}

    def record_usage(self, usage):
        usage = usage or {}
        self.used_tokens += (usage.get("prompt_tokens") or 0) + (usage.get("completion_tokens") or 0)

    async def call(self, messages, tools):
        if self.used_tokens >= self.settings.max_llm_tokens:
            raise RuntimeError(f"本轮模型已记录消耗 {self.used_tokens} Token，达到 {self.settings.max_llm_tokens} Token 预算阈值，已停止后续模型请求并保留检查点")
        messages = self.request_messages(messages)
        configuration = llm_configuration()
        async with httpx.AsyncClient(timeout=self.settings.llm_timeout) as client:
            for attempt in range(self.settings.max_attempts):
                started = time.time()
                self._stream_started = False
                self.stream_usage = {}
                try:
                    if self.observer and self.streaming:
                        return await self.stream_call(client, configuration, messages, tools, started)
                    response = await client.post(
                        configuration["base_url"] + "/chat/completions",
                        headers={"Authorization": "Bearer " + configuration["api_key"]},
                        json={"model": configuration["model"], "messages": messages,
                              "tools": tools, "tool_choice": "auto",
                              "parallel_tool_calls": False},
                    )
                    response.raise_for_status()
                    message = response.json()["choices"][0]["message"]
                    usage = response.json().get("usage")
                    self.record_usage(usage)
                    truncated = response.json()["choices"][0].get("finish_reason") == "length"
                    if self.observer:
                        await self.observer.event("llm", configuration["model"], {"messages": messages, "response": message, "usage": usage,
                            "truncated": truncated}, started, "error" if truncated else "ok", usage=usage)
                    if truncated:
                        raise RuntimeError("模型输出达到长度上限，未执行不完整的工具参数；已停止自动重试并保留检查点")
                    return {key: message[key] for key in ("role", "content", "tool_calls")
                            if key in message}
                except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                    provider_error = None
                    if isinstance(exc, httpx.HTTPStatusError):
                        try:
                            provider_error = exc.response.json().get("error")
                        except ValueError:
                            provider_error = exc.response.text[:2000]
                    if self.observer:
                        await self.observer.event("llm", configuration["model"], {"error": str(exc), "provider_error": provider_error,
                            "attempt": attempt + 1, "usage": self.stream_usage or None}, started, "error", usage=self.stream_usage)
                    self.record_usage(self.stream_usage)
                    # 读取超时或断流时服务端可能已经计费，只自动重试建立连接失败。
                    retryable = isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout)) or (isinstance(exc, httpx.HTTPStatusError) and (
                        exc.response.status_code == 429 or exc.response.status_code >= 500))
                    if not retryable or self._stream_started or attempt + 1 == self.settings.max_attempts:
                        if provider_error:
                            raise RuntimeError("模型请求失败：" + json.dumps(provider_error, ensure_ascii=False)) from exc
                        raise
                    await asyncio.sleep(2 ** attempt)

    @staticmethod
    def request_messages(messages):
        """检查点保留完整历史，移除重复等待消息和已有新版状态的待审原文。"""
        groups = []
        for index, message in enumerate(messages):
            calls = message.get("tool_calls") or []
            if calls and all(call["function"]["name"].endswith("_poll_task") for call in calls):
                end = index + 1
                while end < len(messages) and messages[end].get("role") == "tool":
                    end += 1
                results = []
                for item in messages[index + 1:end]:
                    try:
                        results.append(json.loads(item.get("content") or "{}"))
                    except ValueError:
                        break
                if end - index - 1 == len(calls) and len(results) == len(calls) and all(
                    isinstance(item, dict) and item.get("done") is False and not item.get("error")
                    and item.get("status") not in {"failed", "cancelled"} for item in results):
                    groups.append((index, end))
        omitted = {index for start, end in groups[:-1] for index in range(start, end)}
        latest_context = {}
        contexts = {}
        for index, item in enumerate(messages):
            if item.get("role") != "tool":
                continue
            try:
                value = json.loads(item.get("content") or "{}")
            except ValueError:
                continue
            if not isinstance(value, dict):
                continue
            context = value.get("result") if isinstance(value.get("result"), dict) else value
            if context.get("context_path") and "pending" in context:
                contexts[index] = (value, context)
                latest_context[context["context_path"]] = index
        result = []
        for index, message in enumerate(messages):
            if index in omitted:
                continue
            if index in contexts:
                value, context = contexts[index]
                if latest_context[context["context_path"]] != index:
                    compact = {key: value for key, value in context.items() if key not in {"pending", "prompt"}}
                    compact["历史待审正文"] = "使用后续同一 context_path 的最新状态，完整原文保存在检查点"
                    value = {**value, "result": compact} if context is not value else compact
                    message = {**message, "content": json.dumps(value, ensure_ascii=False)}
            # 完整工具参数保留在检查点和追踪；已处理的大段审核正文不重复发给模型。
            if message.get("tool_calls") and index + 1 < len(messages) and messages[index + 1].get("role") == "tool":
                calls = []
                for call in message["tool_calls"]:
                    if len(call["function"]["arguments"]) > 2000:
                        call = {**call, "function": {**call["function"], "arguments": json.dumps({"历史参数": "已执行，完整参数保存在检查点；结果见对应工具消息"}, ensure_ascii=False)}}
                    calls.append(call)
                message = {**message, "tool_calls": calls}
            result.append(message)
        return result

    async def stream_call(self, client, configuration, messages, tools, started):
        message = {"role": "assistant", "content": ""}
        calls, usage = {}, {}
        complete = False
        truncated = False
        async with client.stream("POST", configuration["base_url"] + "/chat/completions",
            headers={"Authorization": "Bearer " + configuration["api_key"]},
            json={"model": configuration["model"], "messages": messages, "tools": tools,
                  "tool_choice": "auto", "parallel_tool_calls": False, "stream": True,
                  "stream_options": {"include_usage": True}}) as response:
            if response.is_error:
                await response.aread()
                response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                raw = line[5:].strip()
                if raw == "[DONE]":
                    complete = True
                    break
                payload = json.loads(raw)
                if payload.get("error"):
                    raise RuntimeError("模型流式返回错误：" + json.dumps(payload["error"], ensure_ascii=False))
                usage = payload.get("usage") or usage
                self.stream_usage = usage
                for choice in payload.get("choices", []):
                    if choice.get("finish_reason") is not None:
                        complete = True
                        truncated = truncated or choice["finish_reason"] == "length"
                    delta = choice.get("delta") or {}
                    if delta.get("reasoning_content"):
                        self._stream_started = True
                    if delta.get("content"):
                        self._stream_started = True
                        message["content"] += delta["content"]
                        if self.observer.emit:
                            await self.observer.emit({"kind": "token", "text": delta["content"]})
                    for part in delta.get("tool_calls") or []:
                        self._stream_started = True
                        call = calls.setdefault(part["index"], {"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                        call["id"] += part.get("id") or ""
                        for key in ("name", "arguments"):
                            call["function"][key] += (part.get("function") or {}).get(key) or ""
        if not complete or truncated:
            self.record_usage(usage)
            error = "模型输出达到长度上限，未执行不完整的工具参数" if truncated else "模型流在完成前中断"
            await self.observer.event("llm", configuration["model"], {"error": error, "response": message, "usage": usage or None}, started, "error", usage=usage)
            raise RuntimeError(error + "，已停止自动重试并保留检查点")
        if calls:
            message["tool_calls"] = [calls[index] for index in sorted(calls)]
        if not message["content"] and not calls:
            raise ValueError("模型流式响应为空")
        self.record_usage(usage)
        await self.observer.event("llm", configuration["model"], {"messages": messages, "response": message, "usage": usage}, started, usage=usage)
        return message
