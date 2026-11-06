"""按镜头分组生成财经章节时间轴和对应图层。"""

from __future__ import annotations

from pathlib import Path

from core.tools.generate_final_video._size import parse_size
from core.tools.generate_timeline import generate_chapter_timeline

from ..config.settings import VIDEO_SIZE
from ..errors import WorkflowStepError


def _chapter_groups(shots: list[dict], count: int) -> list[list[dict]]:
    """把镜头按时长均分成 count 个连续章节组（边界落在镜头边缘）。"""
    target = sum(float(shot["duration"]) for shot in shots) / count
    groups: list[list[dict]] = []
    current: list[dict] = [shots[0]]
    accumulated = float(shots[0]["duration"])
    for shot in shots[1:]:
        if accumulated >= target and len(groups) < count - 1:
            groups.append(current)
            current = []
            accumulated = 0.0
        current.append(shot)
        accumulated += float(shot["duration"])
    if current:
        groups.append(current)
    return [group for group in groups if group]


def render_chapter_layer(
    shots: list[dict],
    settings: dict,
    cache_root: Path,
    progress=None,
) -> list[str]:
    """章节时间轴条图层：横条分段 + 宿主段落标题 + 进度色随播放推进。"""
    chapter = settings["chapter_timeline"]
    segments, _ = chapter_editorial_input(shots, chapter)
    if not segments:
        return []
    titles = chapter.get("titles")
    if not isinstance(titles, list) or len(titles) != len(segments) or any(not isinstance(title, str) or not title.strip() for title in titles):
        raise WorkflowStepError("production_config.chapter_timeline.titles 必须由宿主提供，数量与章节一致")
    for segment, title in zip(segments, titles, strict=True):
        segment["title"] = title
    canvas_width, canvas_height = parse_size(VIDEO_SIZE)
    try:
        layer = generate_chapter_timeline(
            segments,
            cache_root / "chapter-timeline.ass",
            canvas_width,
            canvas_height,
            position=str(chapter["position"]),
            style={
                key: chapter[key]
                for key in (
                    "font_size",
                    "bar_height",
                    "margin_horizontal",
                    "margin_vertical_ratio",
                )
                if key in chapter
            },
        )
    except Exception as exc:
        raise WorkflowStepError(f"生成章节时间轴条失败：{exc}") from exc
    if progress is not None:
        progress(
            "章节时间轴条（{}，{} 段）：{}".format(
                layer["position"], layer["segment_count"], "、".join(layer["titles"])
            )
        )
    return [layer["output_path"]]



def chapter_editorial_input(shots: list[dict], chapter: dict) -> tuple[list[dict], list[str]]:
    """按实际镜头时间轴返回宿主定稿所需的章节正文。"""
    if not chapter.get("enabled") or len(shots) < 2:
        return [], []
    count = max(2, min(int(chapter["segment_count"]), len(shots)))
    groups = _chapter_groups(shots, count)
    if len(groups) < 2:
        return [], []
    segments = []
    chapter_texts = []
    for group in groups:
        start = float(group[0]["audio_start"])
        end = float(group[-1]["audio_end"])
        if end - start < 1.0:
            continue
        segments.append({"start": start, "end": end, "title": ""})
        chapter_texts.append(
            " ".join(str(shot.get("subtitle") or "") for shot in group)
        )
    if len(segments) < 2:
        return [], []
    return segments, chapter_texts
