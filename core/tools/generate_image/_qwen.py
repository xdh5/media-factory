"""千问生图，以及尺寸校验、存图等内部实现。"""

from __future__ import annotations

import base64
import json
import os
from io import BytesIO
from pathlib import Path

import requests
from dotenv import load_dotenv
from PIL import Image

from ._constants import QWEN_IMAGE_ENDPOINT, QWEN_IMAGE_MODEL
from ._errors import AIConfigurationError, AIGenerationError, ReferenceImageError
from ._image import _fit_image, _parse_size, _write_png

load_dotenv()


def _qwen_image_model() -> str:
    """读取千问生图模型；未配置时使用项目默认模型。"""
    return os.getenv("DASHSCOPE_IMAGE_MODEL", QWEN_IMAGE_MODEL).strip() or QWEN_IMAGE_MODEL


def _save_image(image_bytes: bytes, output_path: Path, width: int, height: int) -> dict:
    try:
        with Image.open(BytesIO(image_bytes)) as image:
            image.load()
            fitted = _fit_image(image, width, height)
            has_alpha = "A" in fitted.getbands()
            alpha_extrema = fitted.getchannel("A").getextrema() if has_alpha else (255, 255)
            _write_png(fitted.copy(), output_path)
    except (OSError, ValueError) as exc:
        raise AIGenerationError("千问返回的内容不是有效图片") from exc
    return {
        "mode": fitted.mode,
        "has_alpha": has_alpha,
        "alpha_extrema": [int(alpha_extrema[0]), int(alpha_extrema[1])],
        "has_transparency": bool(has_alpha and alpha_extrema[0] < 255),
    }


def _reference_data_url(reference_path: Path) -> str:
    if not reference_path.is_file():
        raise ReferenceImageError(f"风格参考图不存在：{reference_path}")
    try:
        with Image.open(reference_path) as source:
            output = BytesIO()
            source.convert("RGB").save(output, format="JPEG", quality=92, optimize=True)
    except (OSError, ValueError) as exc:
        raise ReferenceImageError(f"风格参考图不是有效图片：{reference_path}") from exc
    return f"data:image/jpeg;base64,{base64.b64encode(output.getvalue()).decode('ascii')}"


def _qwen_image_bytes(payload: dict) -> bytes:
    choices = payload.get("output", {}).get("choices") or []
    content = choices[0].get("message", {}).get("content") if choices and isinstance(choices[0], dict) else None
    if not isinstance(content, list):
        raise AIGenerationError("千问响应中没有生成图片")
    image_url = next(
        (item.get("image") for item in content if isinstance(item, dict) and isinstance(item.get("image"), str)),
        "",
    )
    if not image_url:
        raise AIGenerationError("千问响应中没有可用的图片地址")
    try:
        response = requests.get(image_url, timeout=(20, 180))
        response.raise_for_status()
        return response.content
    except requests.RequestException as exc:
        raise AIGenerationError(f"千问结果图片下载失败：{exc}") from exc


def _generate_with_ai(prompt: str, reference_paths: list[Path], size: str) -> bytes:
    api_key = os.getenv("DASHSCOPE_API_KEY", "").strip()
    if not api_key:
        raise AIConfigurationError("缺少环境变量 DASHSCOPE_API_KEY，无法使用千问生图")
    endpoint = os.getenv("DASHSCOPE_IMAGE_URL", QWEN_IMAGE_ENDPOINT).strip() or QWEN_IMAGE_ENDPOINT
    content = [{"image": _reference_data_url(path)} for path in reference_paths]
    content.append({"text": prompt})
    payload = {
        "model": _qwen_image_model(),
        "input": {"messages": [{"role": "user", "content": content}]},
        "parameters": {
            "n": 1,
            "prompt_extend": True,
            "watermark": False,
            "size": size.replace("x", "*"),
        },
    }
    try:
        response = requests.post(
            endpoint,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            timeout=(20, 600),
        )
        response.raise_for_status()
        return _qwen_image_bytes(response.json())
    except requests.HTTPError as exc:
        details = response.text.strip()[:2000]
        raise AIGenerationError(
            f"千问生图请求失败（HTTP {response.status_code}）：{details or '服务端没有返回错误详情'}"
        ) from exc
    except requests.RequestException as exc:
        raise AIGenerationError(f"千问生图网络请求失败：{type(exc).__name__}: {exc}") from exc
    except (ValueError, json.JSONDecodeError) as exc:
        raise AIGenerationError("千问返回的响应不是有效 JSON") from exc
