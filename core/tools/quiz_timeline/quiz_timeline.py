"""生成心灵鸡汤选项卡片与可视化时间轴的 ASS 图层。"""

from __future__ import annotations

from pathlib import Path

from ._constants import (
    ASS_HEADER,
    OPTION_LABELS,
    TIMELINE_BOTTOM_TOP,
    TIMELINE_HEIGHT,
    TIMELINE_LEFT,
    TIMELINE_RIGHT,
    TIMELINE_TOP_TOP,
)
from ._errors import QuizTimelineInputError


def _time(seconds: float) -> str:
    value = max(0.0, float(seconds))
    hours = int(value // 3600)
    minutes = int((value % 3600) // 60)
    whole_seconds = int(value % 60)
    centiseconds = int(round((value - int(value)) * 100))
    if centiseconds >= 100:
        whole_seconds += 1
        centiseconds = 0
    if whole_seconds >= 60:
        minutes += whole_seconds // 60
        whole_seconds %= 60
    if centiseconds >= 100:
        minutes += centiseconds // 100
        centiseconds %= 100
    if minutes >= 60:
        hours += minutes // 60
        minutes %= 60
    return f"{hours}:{minutes:02d}:{whole_seconds:02d}.{centiseconds // 10:02d}"


def _validate_stages(stages: list[dict], name: str, duration: float) -> list[dict]:
    if not isinstance(stages, list) or len(stages) != 4:
        raise QuizTimelineInputError(f"{name} 必须包含 A、B、C、D 四段")
    normalized = []
    for expected, stage in zip(OPTION_LABELS, stages):
        if not isinstance(stage, dict) or str(stage.get("label") or "") != expected:
            raise QuizTimelineInputError(f"{name} 必须按 A、B、C、D 顺序提供")
        start, end = float(stage.get("start") or 0), float(stage.get("end") or 0)
        if start < 0 or end <= start or end > duration + 0.2:
            raise QuizTimelineInputError(f"{name}.{expected} 的时间范围无效")
        normalized.append({"label": expected, "start": start, "end": min(end, duration)})
    return normalized


def _validate_chapters(chapters: list[dict], duration: float) -> list[dict]:
    if not isinstance(chapters, list) or len(chapters) < 2:
        raise QuizTimelineInputError("chapters 至少需要两个章节")
    normalized = []
    previous_end = 0.0
    for index, chapter in enumerate(chapters, start=1):
        if not isinstance(chapter, dict):
            raise QuizTimelineInputError(f"chapters[{index}] 必须是对象")
        title = " ".join(str(chapter.get("title") or "").split())
        start = float(chapter.get("start") or 0)
        end = float(chapter.get("end") or 0)
        if not title:
            raise QuizTimelineInputError(f"chapters[{index}].title 不能为空")
        if start < 0 or end <= start or end > duration + 0.2:
            raise QuizTimelineInputError(f"chapters[{index}] 的时间范围无效")
        if abs(start - previous_end) > 0.2:
            raise QuizTimelineInputError(f"chapters[{index}] 必须紧接上一个章节")
        normalized.append({"title": title, "start": start, "end": min(end, duration)})
        previous_end = end
    if abs(normalized[-1]["end"] - duration) > 0.2:
        raise QuizTimelineInputError("最后一个章节必须结束于视频总时长")
    return normalized


def _chapter_events(chapters: list[dict], duration: float, position: str) -> list[str]:
    width = TIMELINE_RIGHT - TIMELINE_LEFT
    top = TIMELINE_BOTTOM_TOP if position == "bottom" else TIMELINE_TOP_TOP
    bottom = top + TIMELINE_HEIGHT
    lines = []
    for active_index, active in enumerate(chapters):
        start_time, end_time = _time(active["start"]), _time(active["end"])
        for index, chapter in enumerate(chapters):
            left = round(TIMELINE_LEFT + width * chapter["start"] / duration)
            right = round(TIMELINE_LEFT + width * chapter["end"] / duration)
            fill = "&H202B42&" if index == active_index else "&H171717&"
            alpha = "&H35&" if index == active_index else "&H55&"
            drawing = (
                rf"{{\an7\pos(0,0)\p1\bord0\shad0\1c{fill}\1a{alpha}}}"
                f"m {left} {top} l {right} {top} {right} {bottom} {left} {bottom}"
            )
            lines.append(
                f"Dialogue: 3,{start_time},{end_time},QuizChapter,,0,0,0,,{drawing}"
            )
            center_x = round((left + right) / 2)
            center_y = round((top + bottom) / 2)
            title = chapter["title"].replace("{", "｛").replace("}", "｝")
            text = rf"{{\an5\pos({center_x},{center_y})}}{title}"
            lines.append(
                f"Dialogue: 4,{start_time},{end_time},QuizChapter,,0,0,0,,{text}"
            )
            if index:
                separator = (
                    rf"{{\an7\pos(0,0)\p1\bord0\shad0\1c&HFFFFFF&\1a&H80&}}"
                    f"m {left - 1} {top + 10} l {left + 1} {top + 10} "
                    f"{left + 1} {bottom - 10} {left - 1} {bottom - 10}"
                )
                lines.append(
                    f"Dialogue: 5,{start_time},{end_time},QuizChapter,,0,0,0,,{separator}"
                )
    return lines


def _panel_text(option_stages: list[dict], result_stages: list[dict], now: float) -> str:
    options = [stage["label"] for stage in option_stages if now >= stage["end"]]
    results = [stage["label"] for stage in result_stages if now >= stage["end"]]
    option_text = "  ".join(f"【{label}】" for label in options)
    result_text = "  ".join(f"{label}结果✓" for label in results)
    return option_text + (f"\\N{result_text}" if result_text else "")


def generate_quiz_timeline_ass(
    output_path: str | Path,
    duration: float,
    option_stages: list[dict],
    result_stages: list[dict],
    chapters: list[dict],
    *,
    position: str = "bottom",
) -> dict:
    """生成章节时间轴，以及随朗读进度累积出现的选项和结果。"""
    try:
        total = float(duration)
    except (TypeError, ValueError) as exc:
        raise QuizTimelineInputError("duration 必须是正数") from exc
    if total <= 0:
        raise QuizTimelineInputError("duration 必须大于0")
    options = _validate_stages(option_stages, "option_stages", total)
    results = _validate_stages(result_stages, "result_stages", total)
    normalized_chapters = _validate_chapters(chapters, total)
    if position not in {"bottom", "top"}:
        raise QuizTimelineInputError("position 只能是 bottom 或 top")
    boundaries = sorted({0.0, total, *(item["start"] for item in options), *(item["start"] for item in results), *(item["end"] for item in results)})
    lines = [ASS_HEADER.rstrip("\n"), *_chapter_events(normalized_chapters, total, position)]
    for start, end in zip(boundaries, boundaries[1:]):
        if end <= start:
            continue
        now = start + 0.001
        tag = r"{\an1\pos(70,920)}" if position == "bottom" else r"{\an7\pos(70,105)}"
        panel_text = _panel_text(options, results, now)
        if panel_text:
            panel = tag + panel_text
            lines.append(f"Dialogue: 5,{_time(start)},{_time(end)},QuizPanel,,0,0,0,,{panel}")
    destination = Path(output_path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "output_path": str(destination),
        "duration": total,
        "option_stages": options,
        "result_stages": results,
        "chapters": normalized_chapters,
        "position": position,
    }
