"""对视频素材施加雾面磨砂玻璃感（黑位抬升 + 降对比褪色 + 轻微模糊）并重编码。

用于心灵鸡汤文章成片：正文素材视频在拼接前做雾面处理，
画面像蒙了层薄雾（发白、降对比、微褪色、轻糊），既提升字幕可读性，
也带来磨砂玻璃质感。输出编码参数与 generate_final_video 的 copy 拼接约定一致
（libx264/veryfast/crf21/yuv420p/30fps），拼接前无需转码。
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

from ._constants import (
    SOFT_BLUR_BLACK_LIFT,
    SOFT_BLUR_BRIGHTNESS,
    SOFT_BLUR_CODEC,
    SOFT_BLUR_CONTRAST,
    SOFT_BLUR_CRF,
    SOFT_BLUR_FPS,
    SOFT_BLUR_MIN_TIMEOUT_SECONDS,
    SOFT_BLUR_PIXEL_FORMAT,
    SOFT_BLUR_PRESET,
    SOFT_BLUR_PROBE_TIMEOUT_SECONDS,
    SOFT_BLUR_SATURATION,
    SOFT_BLUR_SIGMA,
    SOFT_BLUR_TIMEOUT_PER_SECOND,
    SOFT_BLUR_VERSION,
    SOFT_BLUR_WORKERS,
)
from ._errors import SoftBlurError, SoftBlurTimeoutError

__all__ = ["apply_soft_blur", "blur_video_segments", "SoftBlurError"]


def _probe_duration(path: Path) -> float:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise SoftBlurError("未找到 ffprobe 可执行文件")
    try:
        completed = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=SOFT_BLUR_PROBE_TIMEOUT_SECONDS,
        )
        duration = float((json.loads(completed.stdout or "{}").get("format") or {}).get("duration") or 0)
    except subprocess.TimeoutExpired as exc:
        raise SoftBlurTimeoutError(f"读取媒体信息超时：{path}") from exc
    except (ValueError, json.JSONDecodeError, OSError) as exc:
        raise SoftBlurError(f"无法读取媒体信息：{path}。{exc}") from exc
    if completed.returncode != 0 or duration <= 0:
        raise SoftBlurError(f"无法读取媒体时长：{path}。{(completed.stderr or '')[-600:]}")
    return duration


def _signature(source: Path, params: dict) -> str:
    digest = hashlib.sha256()
    with source.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    payload = {
        "version": SOFT_BLUR_VERSION,
        "params": params,
        "source": {"size": source.stat().st_size, "sha256": digest.hexdigest()},
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _frost_filter(params: dict) -> str:
    """雾面磨砂滤镜链：黑位抬升（雾感）-> 降对比/褪色/提亮 -> 轻微高斯模糊。"""
    return (
        f"colorlevels=rimin={params['black_lift']}:gimin={params['black_lift']}:bimin={params['black_lift']},"
        f"eq=contrast={params['contrast']}:saturation={params['saturation']}:brightness={params['brightness']},"
        f"gblur=sigma={params['sigma']}"
    )


def _blur_one(source: Path, output: Path, params: dict) -> dict:
    """单素材磨砂重编码，带签名缓存与原子替换。"""
    metadata_path = output.with_suffix(".json")
    signature = _signature(source, params)
    if metadata_path.is_file() and output.is_file():
        try:
            cached = json.loads(metadata_path.read_text(encoding="utf-8"))
            if cached.get("signature") == signature and _probe_duration(output) > 0:
                return {"source": str(source), "output": str(output), "cached": True}
        except (OSError, ValueError, json.JSONDecodeError, SoftBlurError):
            pass

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise SoftBlurError("未找到 ffmpeg 可执行文件")
    duration = _probe_duration(source)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f"softblur-{output.stem}-", dir=output.parent) as temporary:
        temporary_output = Path(temporary) / "output.mp4"
        command = [
            ffmpeg, "-nostdin", "-hide_banner", "-y",
            "-i", str(source),
            "-vf", _frost_filter(params),
            "-an", "-fps_mode", "cfr", "-r", str(SOFT_BLUR_FPS),
            "-c:v", SOFT_BLUR_CODEC, "-preset", SOFT_BLUR_PRESET, "-crf", str(SOFT_BLUR_CRF),
            "-pix_fmt", SOFT_BLUR_PIXEL_FORMAT,
            "-movflags", "+faststart", str(temporary_output),
        ]
        timeout = max(SOFT_BLUR_MIN_TIMEOUT_SECONDS, duration * SOFT_BLUR_TIMEOUT_PER_SECOND)
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise SoftBlurTimeoutError(f"磨砂处理超时（{timeout:.0f}秒）：{source}") from exc
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()[-2000:]
            raise SoftBlurError(f"磨砂处理失败：{source}。{detail}")
        _probe_duration(temporary_output)
        temporary_output.replace(output)

    metadata_tmp = metadata_path.with_suffix(".json.tmp")
    metadata_tmp.write_text(
        json.dumps({"signature": signature, "params": params}, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    metadata_tmp.replace(metadata_path)
    return {"source": str(source), "output": str(output), "cached": False}


def apply_soft_blur(
    source_path: str | Path,
    output_path: str | Path,
    *,
    sigma: float = SOFT_BLUR_SIGMA,
    black_lift: float = SOFT_BLUR_BLACK_LIFT,
    contrast: float = SOFT_BLUR_CONTRAST,
    saturation: float = SOFT_BLUR_SATURATION,
    brightness: float = SOFT_BLUR_BRIGHTNESS,
) -> dict:
    """对单个视频施加雾面磨砂感，返回 {"source", "output", "cached"}。"""
    source = Path(source_path).resolve()
    if not source.is_file():
        raise SoftBlurError(f"源视频不存在：{source}")
    params = {
        "sigma": float(sigma),
        "black_lift": float(black_lift),
        "contrast": float(contrast),
        "saturation": float(saturation),
        "brightness": float(brightness),
    }
    return _blur_one(source, Path(output_path).resolve(), params)


def blur_video_segments(
    segments: dict[str, str | Path],
    cache_dir: str | Path,
    *,
    sigma: float = SOFT_BLUR_SIGMA,
    black_lift: float = SOFT_BLUR_BLACK_LIFT,
    contrast: float = SOFT_BLUR_CONTRAST,
    saturation: float = SOFT_BLUR_SATURATION,
    brightness: float = SOFT_BLUR_BRIGHTNESS,
    workers: int = SOFT_BLUR_WORKERS,
    progress: Callable[[str], None] | None = None,
) -> dict[str, str]:
    """批量磨砂：segments 为 {shot_id: 视频路径}，返回 {shot_id: 磨砂后路径}。

    结果缓存在 cache_dir，签名（源文件哈希 + 滤镜参数）不变则直接复用。
    """
    params = {
        "sigma": float(sigma),
        "black_lift": float(black_lift),
        "contrast": float(contrast),
        "saturation": float(saturation),
        "brightness": float(brightness),
    }
    cache_root = Path(cache_dir).resolve()
    cache_root.mkdir(parents=True, exist_ok=True)
    jobs: list[tuple[str, Path, Path]] = []
    for shot_id, source in segments.items():
        source_path = Path(str(source)).resolve()
        if not source_path.is_file():
            raise SoftBlurError(f"素材不存在：{shot_id} -> {source_path}")
        digest = hashlib.sha256(shot_id.encode("utf-8")).hexdigest()[:12]
        output = cache_root / f"{Path(source_path).stem}-softblur-{digest}.mp4"
        jobs.append((str(shot_id), source_path, output))

    results: dict[str, str] = {}
    worker_count = max(1, min(int(workers), len(jobs)))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {executor.submit(_blur_one, source, output, params): (shot_id, output) for shot_id, source, output in jobs}
        for future in as_completed(futures):
            shot_id, output = futures[future]
            future.result()
            results[shot_id] = str(output)
            if progress:
                progress(f"磨砂处理 {len(results)}/{len(jobs)}")
    return results
