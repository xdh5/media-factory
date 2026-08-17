"""优先使用当前 Agent 能力、失败三次后使用方舟兜底的生图功能。"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from io import BytesIO
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse
from uuid import uuid4

import requests
from dotenv import load_dotenv
from PIL import Image

from ._constants import (
    AGENT_GENERATION_ATTEMPTS,
    ARK_IMAGE_ENDPOINT,
    ARK_IMAGE_MODEL,
    DEFAULT_OUTPUT_DIRECTORY,
    IMAGE_CACHE_VERSION,
)
from ._errors import (
    AIConfigurationError,
    AIGenerationError,
    AgentGenerationError,
    ImageGenerationError,
    InvalidParameterError,
    ReferenceImageError,
)
from ._select_style import _select_style

__all__ = ["generate_image"]

load_dotenv()

AgentImageGenerator = Callable[[dict], object]
_agent_image_generator: AgentImageGenerator | None = None


def _ark_image_model() -> str:
    """读取方舟生图模型；未配置时使用项目默认模型。"""
    return os.getenv("VOLC_ARK_IMAGE_MODEL", ARK_IMAGE_MODEL).strip() or ARK_IMAGE_MODEL


def _set_agent_image_generator(generator: AgentImageGenerator | None) -> None:
    """由宿主注入当前 Agent 的生图适配器，不暴露给 Agent Tool Schema。"""
    global _agent_image_generator
    if generator is not None and not callable(generator):
        raise TypeError("当前 Agent 生图适配器必须可调用")
    _agent_image_generator = generator


def _parse_size(size: str) -> tuple[int, int, str]:
    matched = re.fullmatch(r"\s*(\d+)\s*[xX×]\s*(\d+)\s*", str(size or ""))
    if not matched:
        raise InvalidParameterError("size", "size 必须使用 WIDTHxHEIGHT 格式，例如 2560x1440")
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


def _build_prompt(prompt: str, style: dict, radio: str, size: str) -> str:
    return (
        f"{prompt.strip()}\n\n"
        f"画风要求：{style['description']}\n"
        f"严格参考随附图片的画法、笔触、材质、光影和配色，但不要复制参考图中的人物、物体或构图。\n"
        f"画面比例：{radio}；输出尺寸：{size}。"
    )


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _cache_key(prompt: str, style: dict, radio: str, size: str) -> str:
    reference_path = Path(style["reference_image_path"])
    payload = {
        "cache_version": IMAGE_CACHE_VERSION,
        "fallback_model": _ark_image_model(),
        "prompt": prompt,
        "style": style["id"],
        "reference_sha256": _hash_file(reference_path),
        "radio": radio,
        "size": size,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _read_cache(image_path: Path, metadata_path: Path, width: int, height: int, cache_key: str) -> dict | None:
    if not image_path.is_file() or not metadata_path.is_file():
        return None
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        with Image.open(image_path) as image:
            image.verify()
            image_size = image.size
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        return None
    required_metadata = {"provider", "model", "style", "radio", "size"}
    if (
        metadata.get("cache_key") != cache_key
        or image_size != (width, height)
        or not required_metadata.issubset(metadata)
    ):
        return None
    return {
        "output_path": str(image_path),
        "provider": metadata["provider"],
        "model": metadata["model"],
        "style": metadata["style"],
        "radio": metadata["radio"],
        "size": metadata["size"],
        "agent_attempts": 0,
        "cache_hit": True,
        "cache_key": cache_key,
    }


def _write_cache_metadata(metadata_path: Path, result: dict) -> None:
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = metadata_path.with_name(f".{metadata_path.stem}-{uuid4().hex}.tmp.json")
    temporary.write_text(
        json.dumps(
            {key: result[key] for key in ("cache_key", "provider", "model", "style", "radio", "size")},
            ensure_ascii=False,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    temporary.replace(metadata_path)


def _read_remote_image(url: str) -> bytes:
    try:
        response = requests.get(url, timeout=(20, 180))
        response.raise_for_status()
        return response.content
    except requests.RequestException as exc:
        raise AgentGenerationError(f"当前 Agent 返回的图片地址下载失败：{exc}") from exc


def _result_bytes(result: object) -> bytes:
    if isinstance(result, bytes):
        return result
    if isinstance(result, Path):
        if not result.is_file():
            raise AgentGenerationError(f"当前 Agent 返回的图片不存在：{result}")
        return result.read_bytes()
    if isinstance(result, str):
        value = result.strip()
        if value.startswith("data:image/") and "," in value:
            try:
                return base64.b64decode(value.split(",", 1)[1], validate=True)
            except ValueError as exc:
                raise AgentGenerationError("当前 Agent 返回了无效的图片 Data URL") from exc
        parsed = urlparse(value)
        if parsed.scheme in {"http", "https"}:
            return _read_remote_image(value)
        return _result_bytes(Path(value))
    if isinstance(result, dict):
        for key in ("path", "image_path", "image_url", "url"):
            if result.get(key):
                return _result_bytes(result[key])
        for key in ("b64_json", "base64", "data"):
            if isinstance(result.get(key), str) and result[key]:
                try:
                    return base64.b64decode(result[key], validate=True)
                except ValueError as exc:
                    raise AgentGenerationError(f"当前 Agent 返回的 {key} 不是有效 Base64") from exc
    raise AgentGenerationError(
        "当前 Agent 生图适配器必须返回图片字节、本地路径、图片 URL、Data URL 或包含这些字段的字典"
    )


def _save_image(
    image_bytes: bytes,
    output_path: Path,
    width: int,
    height: int,
    source: str,
    error_type: type[AgentGenerationError] | type[AIGenerationError] = AgentGenerationError,
) -> None:
    try:
        with Image.open(BytesIO(image_bytes)) as image:
            image.load()
            if image.size != (width, height):
                raise error_type(
                    f"{source} 返回尺寸为 {image.width}x{image.height}，要求尺寸为 {width}x{height}"
                )
            converted = image.convert("RGB")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = output_path.with_name(f".{output_path.stem}-{uuid4().hex}.tmp.png")
            converted.save(temporary, format="PNG", optimize=True)
            temporary.replace(output_path)
    except (AgentGenerationError, AIGenerationError):
        raise
    except (OSError, ValueError) as exc:
        raise error_type(f"{source} 返回的内容不是有效图片") from exc


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


def _generate_with_ai(prompt: str, reference_path: Path, size: str) -> bytes:
    api_key = os.getenv("VOLC_ARK_API_KEY", "").strip()
    if not api_key:
        raise AIConfigurationError("缺少环境变量 VOLC_ARK_API_KEY，无法使用方舟生图兜底")
    endpoint = os.getenv("VOLC_ARK_IMAGE_URL", ARK_IMAGE_ENDPOINT).strip() or ARK_IMAGE_ENDPOINT
    payload = {
        "model": _ark_image_model(),
        "prompt": prompt,
        "image": [_reference_data_url(reference_path)],
        "size": size,
        "sequential_image_generation": "disabled",
        "response_format": "b64_json",
        "watermark": False,
    }
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


def generate_image(
    prompt: str,
    style: str,
    radio: str,
    size: str,
    *,
    force_regenerate: bool = False,
    cache_dir: str | Path | None = None,
) -> dict:
    """生成图片；Agent 无生图能力时直走方舟，有能力时失败三次再走方舟。"""
    if not isinstance(prompt, str) or not prompt.strip():
        raise InvalidParameterError("prompt", "prompt 必须是非空字符串")
    if not isinstance(force_regenerate, bool):
        raise InvalidParameterError("force_regenerate", "force_regenerate 必须是布尔值")
    if cache_dir is not None and (not isinstance(cache_dir, (str, Path)) or not str(cache_dir).strip()):
        raise InvalidParameterError("cache_dir", "cache_dir 必须是非空路径或不传")
    width, height, normalized_radio, normalized_size = _validate_dimensions(radio, size)
    selected_style = _select_style(style)
    final_prompt = _build_prompt(prompt, selected_style, normalized_radio, normalized_size)
    output_root = Path(
        cache_dir if cache_dir is not None else os.getenv("IMAGE_OUTPUT_DIRECTORY", DEFAULT_OUTPUT_DIRECTORY)
    ).resolve()
    cache_key = _cache_key(final_prompt, selected_style, normalized_radio, normalized_size)
    output_path = output_root / f"{cache_key}.png"
    metadata_path = output_root / f"{cache_key}.json"
    if not force_regenerate:
        cached = _read_cache(output_path, metadata_path, width, height, cache_key)
        if cached:
            return cached
    agent_request = {
        "prompt": final_prompt,
        "referenced_image_paths": [selected_style["reference_image_path"]],
        "radio": normalized_radio,
        "size": normalized_size,
    }

    failures: list[str] = []
    agent_attempts = 0
    if _agent_image_generator is not None:
        for attempt in range(1, AGENT_GENERATION_ATTEMPTS + 1):
            agent_attempts = attempt
            try:
                image_bytes = _result_bytes(_agent_image_generator(agent_request))
                _save_image(image_bytes, output_path, width, height, "当前 Agent")
                result = {
                    "output_path": str(output_path),
                    "provider": "current_agent",
                    "model": "current_agent",
                    "style": selected_style["id"],
                    "radio": normalized_radio,
                    "size": normalized_size,
                    "agent_attempts": attempt,
                    "cache_hit": False,
                    "cache_key": cache_key,
                }
                _write_cache_metadata(metadata_path, result)
                return result
            except Exception as exc:
                failures.append(f"第 {attempt} 次：{type(exc).__name__}: {exc}")

    try:
        image_bytes = _generate_with_ai(final_prompt, Path(selected_style["reference_image_path"]), normalized_size)
        _save_image(image_bytes, output_path, width, height, "方舟", AIGenerationError)
    except ImageGenerationError as exc:
        exc.details["agent_failures"] = failures
        raise
    result = {
        "output_path": str(output_path),
        "provider": "volc_ark",
        "model": _ark_image_model(),
        "style": selected_style["id"],
        "radio": normalized_radio,
        "size": normalized_size,
        "agent_attempts": agent_attempts,
        "cache_hit": False,
        "cache_key": cache_key,
    }
    _write_cache_metadata(metadata_path, result)
    return result
