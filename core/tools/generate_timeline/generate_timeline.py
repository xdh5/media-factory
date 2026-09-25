"""章节时间轴条公开入口。只写 ASS 覆盖图层文件，不烧进视频。"""

from __future__ import annotations

from pathlib import Path

from core.tools.generate_subtitles._fonts import resolve_fontsdir

from ._ass import write_chapter_timeline_ass
from ._errors import InvalidParameterError, TimelineError
from ._titles import fallback_chapter_titles, generate_chapter_titles

__all__ = [
    "generate_chapter_timeline",
    "generate_chapter_titles",
    "fallback_chapter_titles",
    "TimelineError",
    "InvalidParameterError",
]


def _validate_segments(segments: list[dict]) -> list[dict]:
    if not isinstance(segments, list) or not segments:
        raise InvalidParameterError("segments", "segments 必须是至少一个章节对象")
    normalized: list[dict] = []
    previous_end = 0.0
    for index, item in enumerate(segments):
        if not isinstance(item, dict):
            raise InvalidParameterError(f"segments[{index}]", "每个章节必须是对象")
        try:
            start = float(item["start"])
            end = float(item["end"])
        except (KeyError, TypeError, ValueError) as exc:
            raise InvalidParameterError(
                f"segments[{index}]", "每个章节必须包含数字 start 与 end（秒）"
            ) from exc
        if start < 0 or end <= start:
            raise InvalidParameterError(
                f"segments[{index}]", f"时间非法：start={start} end={end}（要求 0<=start<end）"
            )
        if start < previous_end - 1e-6:
            raise InvalidParameterError(f"segments[{index}]", "章节时间必须按顺序且不重叠")
        title = str(item.get("title") or "").strip()
        if not title:
            raise InvalidParameterError(f"segments[{index}].title", "章节标题不能为空")
        normalized.append({"start": start, "end": end, "title": title})
        previous_end = end
    return normalized


def generate_chapter_timeline(
    segments: list[dict],
    output_path: str | Path,
    width: int,
    height: int,
    *,
    position: str = "top",
    style: dict | None = None,
) -> dict:
    """生成章节时间轴条 ASS 覆盖图层。

    segments 每项含 start / end（秒，成片时间轴）与 title（章节标题，一般来自
    generate_chapter_titles）。position 控制横条贴在画面上方还是下方。
    """
    normalized = _validate_segments(segments)
    try:
        canvas_width = int(width)
        canvas_height = int(height)
    except (TypeError, ValueError) as exc:
        raise InvalidParameterError("width/height", "画布宽高必须是整数") from exc
    if canvas_width < 2 or canvas_height < 2 or canvas_width % 2 or canvas_height % 2:
        raise InvalidParameterError(
            "width/height",
            f"画布宽高必须是大于等于 2 的偶数，当前为 {canvas_width}x{canvas_height}",
        )
    destination = Path(output_path).resolve()
    if destination.suffix.lower() != ".ass":
        raise InvalidParameterError("output_path", "输出必须使用 .ass 扩展名")
    destination.parent.mkdir(parents=True, exist_ok=True)
    write_chapter_timeline_ass(
        destination,
        normalized,
        canvas_width,
        canvas_height,
        position=position,
        style=style,
    )
    fontsdir = resolve_fontsdir()
    return {
        "output_path": str(destination),
        "fontsdir": str(fontsdir),
        "width": canvas_width,
        "height": canvas_height,
        "position": position,
        "segment_count": len(normalized),
        "titles": [item["title"] for item in normalized],
    }
