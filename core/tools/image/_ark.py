"""方舟生图兜底，以及尺寸校验、存图等内部实现。"""

from __future__ import annotations

import base64
import json
import math
import os
import re
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import requests
from dotenv import load_dotenv
from PIL import Image, ImageOps

from ._constants import ARK_IMAGE_ENDPOINT, ARK_IMAGE_MODEL, ARK_MIN_IMAGE_PIXELS, IMAGE_ASPECT_MAX_PIXEL_ERROR
from ._errors import AIConfigurationError, AIGenerationError, InvalidParameterError, ReferenceImageError

load_dotenv()


def _ark_image_model() -> str:
    """读取方舟生图模型；未配置时使用项目默认模型。"""
    return os.getenv("VOLC_ARK_IMAGE_MODEL", ARK_IMAGE_MODEL).strip() or ARK_IMAGE_MODEL


def _parse_size(size: str) -> tuple[int, int, str]:
    matched = re.fullmatch(r"\s*(\d+)\s*[xX×]\s*(\d+)\s*", str(size or ""))
    if not matched:
        raise InvalidParameterError("size", "size 必须使用 WIDTHxHEIGHT 格式，例如 1920x1080")
    width, height = (int(value) for value in matched.groups())
    if width < 64 or height < 64:
        raise InvalidParameterError("size", "size 的宽高都必须不小于 64 像素")
    return width, height, f"{width}x{height}"


def _parse_radio(radio: str) -> tuple[int, int, str]:
    matched = re.fullmatch(r"\s*(\d+)\s*:\s*(\d+)\s*", str(radio or ""))
    if not matched:
        raise InvalidParameterError("radio", "radio 必须使用 WIDTH:HEIGHT 格式，例如 16:9")
    width, height = (int(value) for value in matched.groups())
    if width <= 0 or height <= 0:
        raise InvalidParameterError("radio", "radio 的两个数字都必须大于 0")
    return width, height, f"{width}:{height}"


def _validate_dimensions(radio: str, size: str) -> tuple[int, int, str, str]:
    width, height, normalized_size = _parse_size(size)
    ratio_width, ratio_height, normalized_radio = _parse_radio(radio)
    if width * ratio_height != height * ratio_width:
        raise InvalidParameterError(
            "radio",
            f"radio={normalized_radio} 与 size={normalized_size} 的宽高比不一致，请修改其中一个",
        )
    return width, height, normalized_radio, normalized_size


def _matches_target_aspect(src_width: int, src_height: int, dst_width: int, dst_height: int) -> bool:
    """允许相对目标画布有 1 像素的宽高比舍入误差。"""
    if src_width <= 0 or src_height <= 0 or dst_width <= 0 or dst_height <= 0:
        return False
    expected = round(src_width * dst_height / dst_width)
    return abs(src_height - expected) <= IMAGE_ASPECT_MAX_PIXEL_ERROR


def _fit_image(image: Image.Image, width: int, height: int) -> Image.Image:
    """缩放到目标尺寸。比例一致时只缩放，不一致时居中裁切，不报尺寸错误。"""
    if image.size == (width, height):
        return image
    if _matches_target_aspect(image.width, image.height, width, height):
        return image.resize((width, height), Image.Resampling.LANCZOS)
    return ImageOps.fit(image, (width, height), method=Image.Resampling.LANCZOS)


def _write_png(image: Image.Image, output_path: Path) -> None:
    """按原色彩模式保存 PNG，不转 RGB，以保留透明通道。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(f".{output_path.stem}-{uuid4().hex}.tmp.png")
    image.save(temporary, format="PNG")
    temporary.replace(output_path)


def _save_image(
    image_bytes: bytes,
    output_path: Path,
    width: int,
    height: int,
    source: str,
) -> None:
    try:
        with Image.open(BytesIO(image_bytes)) as image:
            image.load()
            fitted = _fit_image(image, width, height)
            _write_png(fitted.copy(), output_path)
    except AIGenerationError:
        raise
    except (OSError, ValueError) as exc:
        raise AIGenerationError(f"{source} 返回的内容不是有效图片") from exc


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


def _ark_image_bytes(payload: dict) -> bytes:
    items = payload.get("data") or []
    if not items or not isinstance(items[0], dict):
        raise AIGenerationError("方舟响应中没有生成图片")
    item = items[0]
    if isinstance(item.get("b64_json"), str) and item["b64_json"]:
        try:
            return base64.b64decode(item["b64_json"], validate=True)
        except ValueError as exc:
            raise AIGenerationError("方舟返回了无效的 Base64 图片") from exc
    if isinstance(item.get("url"), str) and item["url"]:
        try:
            response = requests.get(item["url"], timeout=(20, 180))
            response.raise_for_status()
            return response.content
        except requests.RequestException as exc:
            raise AIGenerationError(f"方舟结果图片下载失败：{exc}") from exc
    raise AIGenerationError("方舟响应中没有可用的图片数据")


def _ark_request_size(size: str) -> str:
    """把本地目标尺寸放大到方舟允许的最小像素面积，并保持宽高比。"""
    width, height, normalized = _parse_size(size)
    if width * height >= ARK_MIN_IMAGE_PIXELS:
        return normalized
    ratio_gcd = math.gcd(width, height)
    ratio_width, ratio_height = width // ratio_gcd, height // ratio_gcd
    scale = math.ceil(math.sqrt(ARK_MIN_IMAGE_PIXELS / (ratio_width * ratio_height)))
    return f"{scale * ratio_width}x{scale * ratio_height}"


def _generate_with_ai(prompt: str, reference_paths: Path | list[Path], size: str) -> bytes:
    api_key = os.getenv("VOLC_ARK_API_KEY", "").strip()
    if not api_key:
        raise AIConfigurationError("缺少环境变量 VOLC_ARK_API_KEY，无法使用方舟生图兜底")
    endpoint = os.getenv("VOLC_ARK_IMAGE_URL", ARK_IMAGE_ENDPOINT).strip() or ARK_IMAGE_ENDPOINT
    normalized_reference_paths = [
        path for path in (reference_paths if isinstance(reference_paths, list) else [reference_paths]) if path
    ]
    payload = {
        "model": _ark_image_model(),
        "prompt": prompt,
        "size": _ark_request_size(size),
        "sequential_image_generation": "disabled",
        "response_format": "b64_json",
        "watermark": False,
    }
    if normalized_reference_paths:
        payload["image"] = [_reference_data_url(path) for path in normalized_reference_paths]
    try:
        response = requests.post(
            endpoint,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            timeout=(20, 600),
        )
        response.raise_for_status()
        return _ark_image_bytes(response.json())
    except requests.HTTPError as exc:
        details = response.text.strip()[:2000]
        raise AIGenerationError(
            f"方舟生图请求失败（HTTP {response.status_code}）：{details or '服务端没有返回错误详情'}"
        ) from exc
    except requests.RequestException as exc:
        raise AIGenerationError(f"方舟生图网络请求失败：{type(exc).__name__}: {exc}") from exc
    except (ValueError, json.JSONDecodeError) as exc:
        raise AIGenerationError("方舟返回的响应不是有效 JSON") from exc
