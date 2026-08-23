"""通过百炼 OpenAI 兼容接口调用千问视觉模型。"""

from __future__ import annotations

import base64
import json
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from PIL import Image, ImageOps

from core.tools.qwen_text import get_qwen_configuration

from ._constants import (
    DEFAULT_MAX_IMAGE_WIDTH,
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
    DEFAULT_TIMEOUT_SECONDS,
    JPEG_QUALITY,
    MAX_RESPONSE_BYTES,
)
from ._errors import QwenVisionConfigurationError, QwenVisionRequestError, QwenVisionResponseError

__all__ = ["analyze_image"]


def _image_data(image_path: str | Path, max_image_width: int) -> tuple[str, dict]:
    path = Path(image_path).resolve()
    if not path.is_file():
        raise QwenVisionConfigurationError(f"视觉模型输入图片不存在：{path}")
    try:
        with Image.open(path) as source:
            normalized = ImageOps.exif_transpose(source).convert("RGBA")
            canvas = Image.new("RGBA", normalized.size, (255, 255, 255, 255))
            canvas.alpha_composite(normalized)
            image = canvas.convert("RGB")
    except Exception as exc:
        raise QwenVisionConfigurationError(f"视觉模型输入不是有效图片：{path}") from exc
    if image.width > max_image_width:
        height = max(1, round(image.height * max_image_width / image.width))
        image = image.resize((max_image_width, height), Image.Resampling.LANCZOS)
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}", {"width": image.width, "height": image.height}


def _error_payload(raw: bytes, status: int) -> tuple[str, dict]:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return f"千问视觉请求失败（HTTP {status}）", {"status": status}
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict):
        return str(error.get("message") or f"千问视觉请求失败（HTTP {status}）"), {
            "status": status,
            "remote_code": str(error.get("code") or error.get("type") or ""),
        }
    return f"千问视觉请求失败（HTTP {status}）", {"status": status}


def analyze_image(
    image_path: str | Path,
    system_prompt: str,
    user_prompt: str,
    *,
    max_image_width: int = DEFAULT_MAX_IMAGE_WIDTH,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    json_output: bool = False,
) -> dict:
    """分析一张本地图片并返回文本、模型和 Token 用量。"""
    system = str(system_prompt or "").strip()
    user = str(user_prompt or "").strip()
    if not system or not user:
        raise QwenVisionConfigurationError("system_prompt 和 user_prompt 不能为空")
    if max_image_width < 64 or max_tokens < 1:
        raise QwenVisionConfigurationError("max_image_width 或 max_tokens 超出允许范围")
    try:
        settings = get_qwen_configuration()
    except Exception as exc:
        raise QwenVisionConfigurationError(f"读取千问配置失败：{exc}") from exc
    image_url, image_size = _image_data(image_path, int(max_image_width))
    body = {
        "model": settings["vision_model"],
        "messages": [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_url}},
                    {"type": "text", "text": user},
                ],
            },
        ],
        "stream": False,
        "temperature": DEFAULT_TEMPERATURE,
        "enable_thinking": False,
        "max_tokens": int(max_tokens),
    }
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
    timeout = int(settings.get("timeout_seconds") or DEFAULT_TIMEOUT_SECONDS)
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        message, details = _error_payload(exc.read(MAX_RESPONSE_BYTES + 1), exc.code)
        raise QwenVisionRequestError(message, details) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise QwenVisionRequestError(f"无法连接千问视觉服务：{exc}") from exc
    if len(raw) > MAX_RESPONSE_BYTES:
        raise QwenVisionResponseError("千问视觉响应超过允许大小，已停止读取")
    try:
        payload = json.loads(raw.decode("utf-8"))
        choice = payload["choices"][0]
        text = str(choice["message"]["content"] or "").strip()
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
        raise QwenVisionResponseError("千问视觉响应格式不正确，缺少 choices[0].message.content") from exc
    if not text:
        raise QwenVisionResponseError("千问视觉返回了空文本")
    usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
    return {
        "text": text,
        "model": str(payload.get("model") or settings["vision_model"]),
        "finish_reason": choice.get("finish_reason"),
        "image_size": image_size,
        "usage": {
            "prompt_tokens": int(usage.get("prompt_tokens") or 0),
            "completion_tokens": int(usage.get("completion_tokens") or 0),
            "total_tokens": int(usage.get("total_tokens") or 0),
        },
    }
