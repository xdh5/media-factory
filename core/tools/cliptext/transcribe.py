"""把本地或远程音视频转成 Whisper 原文，不做错别字校对。"""

from __future__ import annotations

import mimetypes
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import requests
from dotenv import load_dotenv

from ._constants import (
    AUDIO_BITRATE,
    AUDIO_SAMPLE_RATE,
    GROQ_ASR_BASE_URL,
    GROQ_ASR_CHUNK_SECONDS,
    GROQ_ASR_MODEL,
    GROQ_CONNECT_TIMEOUT_SECONDS,
    GROQ_READ_TIMEOUT_SECONDS,
    SUPPORTED_LANGUAGES,
)
from ._errors import (
    FFmpegNotFoundError,
    GroqConfigurationError,
    InvalidParameterError,
    TranscriptionError,
)

load_dotenv()

__all__ = ["transcribe_media"]


def _language_code(value: str) -> str:
    language = str(value or "zh").strip().lower()
    if language.startswith(("cmn", "zh")):
        return "zh"
    if language.startswith(("eng", "en")):
        return "en"
    code = language.split("-", 1)[0]
    if code not in SUPPORTED_LANGUAGES:
        raise InvalidParameterError(
            "language",
            f"不支持语言 {value!r}，请使用 {list(SUPPORTED_LANGUAGES)}",
        )
    return code


def _is_remote(value: str) -> bool:
    return value.startswith(("http://", "https://"))


def _remote_headers() -> str:
    return (
        "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "Chrome/123.0 Safari/537.36\r\n"
        "Referer: https://www.douyin.com/\r\n"
    )


def _probe_duration(ffmpeg: str, source: str) -> float | None:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    command = [ffprobe, "-v", "error"]
    if _is_remote(source):
        command.extend(["-headers", _remote_headers()])
    command.extend(
        [
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", source,
        ]
    )
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        return None
    try:
        duration = float((completed.stdout or "").strip())
    except ValueError:
        return None
    return duration if completed.returncode == 0 and duration > 0 else None


def _extract_audio(ffmpeg: str, source: str, output: Path, *, start: float | None = None, length: float | None = None) -> None:
    command = [ffmpeg, "-y"]
    if _is_remote(source):
        command.extend(["-headers", _remote_headers()])
    if start is not None:
        command.extend(["-ss", f"{start:.3f}"])
    command.extend(["-i", source])
    if length is not None:
        command.extend(["-t", f"{length:.3f}"])
    command.extend([
        "-vn", "-ac", "1", "-ar", str(AUDIO_SAMPLE_RATE),
        "-codec:a", "libmp3lame", "-b:a", AUDIO_BITRATE, str(output),
    ])
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
        )
    except subprocess.TimeoutExpired as exc:
        raise TranscriptionError("提取音频超时，请换更短的视频或检查网络") from exc
    if completed.returncode != 0 or not output.is_file() or output.stat().st_size <= 0:
        detail = (completed.stderr or completed.stdout or "").strip()[-1500:]
        raise TranscriptionError(f"提取音频失败：{detail or 'ffmpeg 没有写出音频'}")


def _transcribe_file(audio_path: Path, *, language: str, api_key: str, model: str, base_url: str) -> dict:
    mime_type = mimetypes.guess_type(audio_path.name)[0] or "audio/mpeg"
    try:
        with audio_path.open("rb") as source:
            response = requests.post(
                f"{base_url.rstrip('/')}/audio/transcriptions",
                headers={"Authorization": f"Bearer {api_key}"},
                data=[
                    ("model", model),
                    ("response_format", "verbose_json"),
                    ("temperature", "0"),
                    ("timestamp_granularities[]", "segment"),
                    ("language", language),
                ],
                files={"file": (audio_path.name, source, mime_type)},
                timeout=(GROQ_CONNECT_TIMEOUT_SECONDS, GROQ_READ_TIMEOUT_SECONDS),
            )
    except requests.RequestException as exc:
        raise TranscriptionError(f"Groq Whisper 请求失败：{exc}") from exc
    if not response.ok:
        raise TranscriptionError(f"Groq Whisper 返回 HTTP {response.status_code}：{response.text[:1000]}")
    try:
        return response.json()
    except ValueError as exc:
        raise TranscriptionError("Groq Whisper 返回了无法解析的响应") from exc


def transcribe_media(media_path: str, *, language: str = "zh", filename: str = "") -> dict:
    """识别音视频中的语音。只返回 Whisper 原文，不做错别字校对。"""
    source = str(media_path or "").strip()
    if not source:
        raise InvalidParameterError(
            "media_path",
            "media_path 不能为空。请传本地文件路径，或先调用 parse_link 再用返回的 video_url",
        )
    language_code = _language_code(language)
    if not _is_remote(source) and not Path(source).is_file():
        raise InvalidParameterError(
            "media_path",
            f"本地文件不存在：{source}。远程视频请传 parse_link 返回的 video_url",
        )
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise GroqConfigurationError("缺少 GROQ_API_KEY。请在 .env 填写 Groq API Key 后重试")
    model = os.getenv("GROQ_ASR_MODEL", GROQ_ASR_MODEL).strip() or GROQ_ASR_MODEL
    base_url = os.getenv("GROQ_ASR_BASE_URL", GROQ_ASR_BASE_URL).strip() or GROQ_ASR_BASE_URL
    chunk_seconds = max(60, min(1200, int(os.getenv("GROQ_ASR_CHUNK_SECONDS", str(GROQ_ASR_CHUNK_SECONDS)))))
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise FFmpegNotFoundError()

    duration = _probe_duration(ffmpeg, source)
    display_name = str(filename or "").strip() or (Path(source).name if not _is_remote(source) else "video")
    texts: list[str] = []
    segments: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="cliptext-asr-") as temporary:
        chunk_dir = Path(temporary)
        jobs: list[tuple[Path, float]] = []
        if duration and duration > chunk_seconds:
            offset = 0.0
            index = 0
            while offset < duration:
                chunk_path = chunk_dir / f"chunk-{index:04d}.mp3"
                _extract_audio(
                    ffmpeg, source, chunk_path,
                    start=offset, length=min(chunk_seconds, duration - offset),
                )
                jobs.append((chunk_path, offset))
                offset += chunk_seconds
                index += 1
        else:
            chunk_path = chunk_dir / "chunk-0000.mp3"
            _extract_audio(ffmpeg, source, chunk_path)
            jobs.append((chunk_path, 0.0))
        for chunk_path, offset in jobs:
            payload = _transcribe_file(
                chunk_path, language=language_code, api_key=api_key, model=model, base_url=base_url,
            )
            chunk_text = str(payload.get("text") or "").strip()
            if chunk_text:
                texts.append(chunk_text)
            for item in payload.get("segments") or []:
                text = str(item.get("text") or "").strip()
                if not text:
                    continue
                segments.append({
                    "start": float(item["start"]) + offset if item.get("start") is not None else None,
                    "end": float(item["end"]) + offset if item.get("end") is not None else None,
                    "text": text,
                })
    text = "".join(texts).strip() if language_code == "zh" else " ".join(texts).strip()
    if not text and segments:
        text = "".join(item["text"] for item in segments) if language_code == "zh" else " ".join(
            item["text"] for item in segments
        )
    if not text:
        raise TranscriptionError("Groq Whisper 未返回识别文本。请确认视频有人声，或换 language 后重试")
    if not segments:
        segments = [{"start": None, "end": None, "text": text}]
    return {
        "filename": display_name,
        "language": language_code,
        "text": text,
        "segments": segments,
    }


def run_job(job_type: str, payload: dict) -> dict:
    """后台任务入口：只处理 transcribe。"""
    if job_type != "transcribe":
        raise TranscriptionError(f"不支持的后台任务类型：{job_type}。请使用 transcribe")
    return transcribe_media(
        payload["media_path"],
        language=payload.get("language") or "zh",
        filename=payload.get("filename") or "",
    )
