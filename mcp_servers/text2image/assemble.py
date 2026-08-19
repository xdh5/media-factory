"""用公有视频原语串起文生图成片：拼镜头、烧字幕、加封面、混 BGM。"""

from __future__ import annotations

from pathlib import Path

from core.tools.video import burn_subtitles, compose_shots, concat_videos, mix_bgm, render_shot

from ._errors import WorkflowStepError
from ._line import Text2ImageLine

_FORBIDDEN_FILENAME_CHARACTERS = '<>:"/\\|?*'
_RESERVED_FILENAMES = {
    "CON", "PRN", "AUX", "NUL",
    *{f"COM{number}" for number in range(1, 10)},
    *{f"LPT{number}" for number in range(1, 10)},
}


def _titled_mp4(output_dir: Path, title: str) -> Path:
    normalized = "".join("_" if character in _FORBIDDEN_FILENAME_CHARACTERS else character for character in title)
    normalized = normalized.strip().rstrip(". ")[:120].rstrip(". ")
    if not normalized:
        raise WorkflowStepError("标题去除非法字符后为空，无法生成成品文件名")
    if normalized.upper() in _RESERVED_FILENAMES:
        normalized = f"_{normalized}"
    return output_dir / f"{normalized}.mp4"


def _compose_item(shot: dict) -> dict:
    item = {"id": shot["id"]}
    segment = str(shot.get("segment_path") or "").strip()
    if segment:
        item["segment_path"] = segment
        return item
    item["image_path"] = shot["image_path"]
    for key in ("audio_path", "audio_start", "audio_end", "duration", "motion"):
        if shot.get(key) is not None:
            item[key] = shot[key]
    return item


def _subtitle_cues(shots: list[dict], shot_results: list[dict]) -> list[dict]:
    by_id = {str(shot.get("id") or "").strip(): shot for shot in shots}
    cues: list[dict] = []
    cursor = 0.0
    for result in shot_results:
        source = by_id.get(str(result["id"])) or {}
        duration = float(result.get("duration") or 0)
        text = str(source.get("subtitle") or "").strip()
        if text:
            cues.append({
                "start": cursor,
                "end": cursor + duration,
                "text": text,
                "language": str(source.get("subtitle_language") or "zh"),
            })
        cursor += duration
    return cues


def assemble_text2image_video(
    line: Text2ImageLine,
    shots: list[dict],
    *,
    cache_dir: str | Path,
    output_dir: str | Path,
    title: str,
    cover_path: str | Path,
    bgm_path: str | Path,
    force_shot_ids: list[str] | None,
) -> dict:
    """文生图成片流水线。失败时转成工作流错误。"""
    cache_root = Path(cache_dir).resolve()
    output_root = Path(output_dir).resolve()
    cache_root.mkdir(parents=True, exist_ok=True)
    output_root.mkdir(parents=True, exist_ok=True)
    try:
        composed = compose_shots(
            [_compose_item(shot) for shot in shots],
            cache_root / "composed.mp4",
            cache_root / "shots",
            size=line.video_size,
            force_shot_ids=force_shot_ids,
        )
        current = Path(composed["output_path"])
        cues = _subtitle_cues(shots, composed["shots"])
        if cues:
            subtitled = burn_subtitles(current, cues, line.video_size, cache_root / "with-subtitles.mp4")
            current = Path(subtitled["output_path"])
        cover_clip = cache_root / "cover-frame.mp4"
        render_shot(cover_path, cover_clip, size=line.video_size, duration=line.cover_frame_seconds)
        with_cover = concat_videos([cover_clip, current], cache_root / "with-cover.mp4")
        return mix_bgm(
            with_cover["output_path"],
            bgm_path,
            _titled_mp4(output_root, title),
            gain=line.bgm_gain,
            mix_gain=line.mix_gain,
            fade_in=line.bgm_fade_in,
            fade_out=line.bgm_fade_out,
        )
    except WorkflowStepError:
        raise
    except Exception as extra:
        raise WorkflowStepError(f"文生图成片失败：{extra}") from extra
