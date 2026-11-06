"""计算完整剧集边界或长视频时间线的分段。"""

from __future__ import annotations

import math

from .._constants import MAX_PART_SECONDS, SEGMENTATION_DURATION
from .._errors import AnimeError


def part_count(total_seconds: float, max_part_seconds: float = MAX_PART_SECONDS) -> int:
    """按单段上限计算段数。刚好落在 3、6、9 小时边界时不额外多切一段。"""
    if total_seconds <= 0:
        raise AnimeError("视频总时长无效")
    if max_part_seconds <= 0:
        raise AnimeError("单段时长上限无效")
    return max(1, math.ceil((total_seconds - 0.05) / max_part_seconds))


def part_ranges(
    episode_durations: list[float],
    max_part_seconds: float = MAX_PART_SECONDS,
) -> list[tuple[float, float]]:
    """以三小时估算段数，再选择最接近均分目标的完整剧集边界。"""
    if not episode_durations or any(not math.isfinite(value) or value <= 0 for value in episode_durations):
        raise AnimeError("分段需要有效的完整剧集时长")
    boundaries = [0.0]
    for duration in episode_durations:
        boundaries.append(boundaries[-1] + duration)
    total_seconds = boundaries[-1]
    count = min(len(episode_durations), part_count(total_seconds, max_part_seconds))
    ranges: list[tuple[float, float]] = []
    previous = 0
    for index in range(1, count):
        # 为后续每段至少留一集；切点只能取整集边界，允许为保全剧集略超三小时。
        target = boundaries[previous] + (total_seconds - boundaries[previous]) / (count - index + 1)
        latest = len(episode_durations) - (count - index)
        selected = min(range(previous + 1, latest + 1), key=lambda end: abs(boundaries[end] - target))
        ranges.append((boundaries[previous], boundaries[selected]))
        previous = selected
    ranges.append((boundaries[previous], total_seconds))
    return ranges


def split_ranges(total_seconds: float, max_part_seconds: float = MAX_PART_SECONDS) -> list[tuple[float, float]]:
    """长视频按时间线均分成每段不超过三小时，切点可以落在来源中间。"""
    if not math.isfinite(total_seconds) or total_seconds <= 0:
        raise AnimeError("拆分需要有效的视频总时长")
    count = part_count(total_seconds, max_part_seconds)
    each = total_seconds / count
    return [(index * each, (index + 1) * each if index + 1 < count else total_seconds)
            for index in range(count)]


def planned_part_count(sources: list[dict], segmentation: str) -> int:
    """按冻结来源时长给出预计段数；长视频直发按时间线均分。"""
    durations = [float(item["duration_seconds"]) for item in sources]
    if segmentation == SEGMENTATION_DURATION:
        return len(split_ranges(sum(durations)))
    return len(part_ranges(durations))
