"""通过百炼 OpenAI 兼容接口调用千问文本模型。"""

from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv

from ._constants import (
    DASHSCOPE_API_KEY_ENV,
    DASHSCOPE_BASE_URL_ENV,
    DASHSCOPE_ENABLE_THINKING_ENV,
    DASHSCOPE_MODEL_ENV,
    DASHSCOPE_VISION_MODEL_ENV,
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    DEFAULT_TEMPERATURE,
    DEFAULT_TIMEOUT_SECONDS,
    MAX_RESPONSE_BYTES,
)
from ._errors import QwenConfigurationError, QwenRequestError, QwenResponseError

__all__ = ["generate_text", "get_qwen_configuration"]

load_dotenv()


def _boolean(value: object, *, name: str) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value or "").strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise QwenConfigurationError(f"{name} 必须是 true 或 false")


def get_qwen_configuration() -> dict:
    """返回包含运行密钥但不负责输出日志的有效配置。"""
    api_key = os.getenv(DASHSCOPE_API_KEY_ENV, "").strip()
    if not api_key:
        raise QwenConfigurationError(
            f"缺少 {DASHSCOPE_API_KEY_ENV}，请在本地 .env 或 GitHub Secrets 中配置"
        )
    base_url = os.getenv(DASHSCOPE_BASE_URL_ENV, "").strip() or DEFAULT_BASE_URL
    model = os.getenv(DASHSCOPE_MODEL_ENV, "").strip() or DEFAULT_MODEL
    vision_model = os.getenv(DASHSCOPE_VISION_MODEL_ENV, "").strip() or model
    thinking_value = os.getenv(DASHSCOPE_ENABLE_THINKING_ENV)
    enable_thinking = _boolean(
        False if thinking_value is None else thinking_value,
        name=DASHSCOPE_ENABLE_THINKING_ENV,
    )
    timeout_seconds = DEFAULT_TIMEOUT_SECONDS
    temperature = DEFAULT_TEMPERATURE
    if not base_url.startswith("https://"):
        raise QwenConfigurationError("千问 base_url 必须使用 https://")
    if not model or not vision_model:
        raise QwenConfigurationError("千问文本模型和视觉模型不能为空")
    if timeout_seconds < 1 or not 0 <= temperature <= 2:
        raise QwenConfigurationError("千问 timeout_seconds 或 temperature 超出允许范围")
    return {
        "api_key": api_key,
        "base_url": base_url.rstrip("/"),
        "model": model,
        "vision_model": vision_model,
        "enable_thinking": enable_thinking,
        "timeout_seconds": timeout_seconds,
        "temperature": temperature,
    }


def _error_payload(raw: bytes, status: int) -> tuple[str, dict]:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return f"千问请求失败（HTTP {status}）", {"status": status}
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict):
        return str(error.get("message") or f"千问请求失败（HTTP {status}）"), {
            "status": status,
            "remote_code": str(error.get("code") or error.get("type") or ""),
        }
    return f"千问请求失败（HTTP {status}）", {"status": status}


def generate_text(
    system_prompt: str,
    user_prompt: str,
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
    json_output: bool = False,
) -> dict:
    """使用配置中的千问文本模型生成内容并返回 Token 用量。"""
    system = str(system_prompt or "").strip()
    user = str(user_prompt or "").strip()
    if not system or not user:
        raise QwenConfigurationError("system_prompt 和 user_prompt 不能为空")
    settings = get_qwen_configuration()
    request_temperature = settings["temperature"] if temperature is None else float(temperature)
    if not 0 <= request_temperature <= 2:
        raise QwenConfigurationError("temperature 必须在 0 到 2 之间")
    body = {
        "model": settings["model"],
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "temperature": request_temperature,
        "enable_thinking": settings["enable_thinking"],
    }
    if max_tokens is not None:
        if isinstance(max_tokens, bool) or int(max_tokens) < 1:
            raise QwenConfigurationError("max_tokens 必须是正整数")
        body["max_tokens"] = int(max_tokens)
    if json_output:
        body["response_format"] = {"type": "json_object"}
    request = Request(
        f"{settings['base_url']}/chat/completions",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {settings['api_key']}",
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
            "X-DashScope-Wait-Timeout": "30",
        },
    )
    try:
        with urlopen(request, timeout=settings["timeout_seconds"]) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        message, details = _error_payload(exc.read(MAX_RESPONSE_BYTES + 1), exc.code)
        raise QwenRequestError(message, details) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise QwenRequestError(f"无法连接千问服务：{exc}") from exc
    if len(raw) > MAX_RESPONSE_BYTES:
        raise QwenResponseError("千问响应超过允许大小，已停止读取")
    try:
        payload = json.loads(raw.decode("utf-8"))
        choice = payload["choices"][0]
        text = str(choice["message"]["content"] or "").strip()
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
        raise QwenResponseError("千问响应格式不正确，缺少 choices[0].message.content") from exc
    if not text:
        raise QwenResponseError("千问返回了空文本")
    usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
    return {
        "text": text,
        "model": str(payload.get("model") or settings["model"]),
        "finish_reason": choice.get("finish_reason"),
        "usage": {
            "prompt_tokens": int(usage.get("prompt_tokens") or 0),
            "completion_tokens": int(usage.get("completion_tokens") or 0),
            "total_tokens": int(usage.get("total_tokens") or 0),
        },
    }
