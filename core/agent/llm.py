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

    async def call(self, messages, tools):
        messages = self.request_messages(messages)
        configuration = llm_configuration()
        async with httpx.AsyncClient(timeout=self.settings.llm_timeout) as client:
            for attempt in range(self.settings.max_attempts):
                started = time.time()
                self._stream_started = False
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
                    if self.observer:
                        await self.observer.event("llm", configuration["model"], {"messages": messages, "response": message}, started, usage=response.json().get("usage"))
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
                        await self.observer.event("llm", configuration["model"], {"error": str(exc), "provider_error": provider_error, "attempt": attempt + 1}, started, "error")
                    retryable = not isinstance(exc, httpx.HTTPStatusError) or (
                        exc.response.status_code == 429 or exc.response.status_code >= 500)
                    if not retryable or self._stream_started or attempt + 1 == self.settings.max_attempts:
                        if provider_error:
                            raise RuntimeError("模型请求失败：" + json.dumps(provider_error, ensure_ascii=False)) from exc
                        raise
                    await asyncio.sleep(2 ** attempt)

    @staticmethod
    def request_messages(messages):
        """检查点保留完整历史，请求只保留最近一组纯轮询交互。"""
        groups = []
        for index, message in enumerate(messages):
            calls = message.get("tool_calls") or []
            if calls and all(call["function"]["name"].endswith("_poll_task") for call in calls):
                end = index + 1
                while end < len(messages) and messages[end].get("role") == "tool":
                    end += 1
                if end - index - 1 == len(calls):
                    groups.append((index, end))
        omitted = {index for start, end in groups[:-1] for index in range(start, end)}
        return [message for index, message in enumerate(messages) if index not in omitted]

    async def stream_call(self, client, configuration, messages, tools, started):
        message = {"role": "assistant", "content": ""}
        calls, usage = {}, {}
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
                    break
                payload = json.loads(raw)
                if payload.get("error"):
                    raise RuntimeError("模型流式返回错误：" + json.dumps(payload["error"], ensure_ascii=False))
                usage = payload.get("usage") or usage
                for choice in payload.get("choices", []):
                    delta = choice.get("delta") or {}
                    if delta.get("content"):
                        self._stream_started = True
                        message["content"] += delta["content"]
                        if self.observer.emit:
                            await self.observer.emit({"kind": "token", "text": delta["content"]})
                    for part in delta.get("tool_calls") or []:
                        call = calls.setdefault(part["index"], {"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                        call["id"] += part.get("id") or ""
                        for key in ("name", "arguments"):
                            call["function"][key] += (part.get("function") or {}).get(key) or ""
        if calls:
            message["tool_calls"] = [calls[index] for index in sorted(calls)]
        if not message["content"] and not calls:
            raise ValueError("模型流式响应为空")
        await self.observer.event("llm", configuration["model"], {"messages": messages, "response": message}, started, usage=usage)
        return message
