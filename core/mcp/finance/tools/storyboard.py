"""财经分镜 Prompt 生成、TTS 与分镜解析。"""

from __future__ import annotations

import json
from pathlib import Path

from core.tools.generate_tts import generate_tts

from .._constants import MCP_ID, STORYBOARD_CONTEXT_FILE_NAME, VIDEO_RADIO, VIDEO_SIZE
from .._errors import AgentOutputFormatError, WorkflowStepError
from .narration import display_subtitle_text, parse_emphasis_segments, split_narration_lines
from .prompts import build_metadata_prompt, build_storyboard_prompt
from .save_draft import load_draft


def _tts_config(config: dict) -> tuple[str, str, bool]:
    voice = str(config.get("voice") or "").strip()
    rate = str(config.get("rate") or "").strip()
    if not voice:
        raise WorkflowStepError("tts_config.voice 不能为空")
    if not rate:
        raise WorkflowStepError("tts_config.rate 不能为空")
    trim = config.get("trim_trailing_silence")
    if not isinstance(trim, bool):
        raise WorkflowStepError("tts_config.trim_trailing_silence 必须是布尔值")
    return voice, rate, trim


def compose_tts(article: str, cache_root: Path, tts_config: dict) -> dict:
    voice, rate, trim = _tts_config(tts_config)
    script = [{"text": line_text, "voice": voice} for line_text in split_narration_lines(article)]
    if not script:
        raise WorkflowStepError("正文切句后没有可配音的句子")
    return generate_tts(
        script,
        cache_root / "narration.wav",
        rate=rate,
        trim_trailing_silence=trim,
    )


def _parse_motion(value: str) -> dict:
    parts = [part.strip() for part in value.split("^")]
    if len(parts) != 8:
        raise AgentOutputFormatError(f"动效参数必须包含 8 个 ^ 分隔值：{value}")
    try:
        numbers = [float(part) for part in parts]
    except ValueError as exc:
        raise AgentOutputFormatError(f"动效参数必须全部是数字：{value}") from exc
    if numbers[6] != 0 or numbers[7] != 0:
        raise AgentOutputFormatError("分镜淡入和淡出必须固定为 0")
    return {
        "zoom_from": numbers[0],
        "zoom_to": numbers[1],
        "pan_from_x": numbers[2],
        "pan_from_y": numbers[3],
        "pan_to_x": numbers[4],
        "pan_to_y": numbers[5],
    }


def _parse_subtitle_marks(value: str, timeline_by_id: dict) -> dict[str, str]:
    """读取 SUB|台词ID|带【】的屏上文本。"""
    marks: dict[str, str] = {}
    for row in value.splitlines():
        if "|" not in row:
            continue
        fields = [field.strip() for field in row.split("|", 2)]
        if len(fields) != 3 or fields[0].upper() != "SUB":
            continue
        line_id, annotated = fields[1], fields[2]
        if line_id not in timeline_by_id:
            raise AgentOutputFormatError(f"字幕标注包含未知台词 ID：{line_id}")
        if line_id in marks:
            raise AgentOutputFormatError(f"台词 {line_id} 的字幕标注重复")
        try:
            parse_emphasis_segments(annotated)
        except ValueError as extra:
            raise AgentOutputFormatError(f"台词 {line_id} 的重点标记无效：{extra}") from extra
        expected = display_subtitle_text(str(timeline_by_id[line_id].get("text") or ""))
        actual = display_subtitle_text(annotated)
        if actual != expected:
            raise AgentOutputFormatError(
                f"台词 {line_id} 去【】后必须与配音原文一致",
                {"expected": expected, "actual": actual},
            )
        marks[line_id] = annotated
    return marks


def parse_storyboard(value: str, timeline: list[dict]) -> list[dict]:
    timeline_by_id = {item["id"]: item for item in timeline}
    subtitle_marks = _parse_subtitle_marks(value, timeline_by_id)
    shots: list[dict] = []
    used_ids: list[str] = []
    for row in value.splitlines():
        if "|" not in row:
            continue
        fields = [field.strip() for field in row.split("|", 4)]
        if len(fields) != 5 or fields[2].upper() != "IMAGE":
            continue
        line_ids = [item.strip() for item in fields[0].split(",") if item.strip()]
        if not line_ids or any(line_id not in timeline_by_id for line_id in line_ids):
            raise AgentOutputFormatError(f"分镜包含未知台词 ID：{fields[0]}")
        indices = [list(timeline_by_id).index(line_id) for line_id in line_ids]
        if indices != list(range(indices[0], indices[0] + len(indices))):
            raise AgentOutputFormatError(f"同一镜头只能合并相邻台词：{fields[0]}")
        selected = [timeline_by_id[line_id] for line_id in line_ids]
        start = selected[0]["start"]
        end = selected[-1]["end"]
        line_texts = [
            subtitle_marks.get(item["id"], item["text"])
            for item in selected
        ]
        shots.append({
            "id": f"shot-{len(shots) + 1:03d}",
            "line_ids": line_ids,
            "audio_start": start,
            "audio_end": end,
            "duration": round(end - start, 6),
            "subtitle": "".join(line_texts),
            "subtitle_lines": [
                {
                    "text": subtitle_marks.get(item["id"], item["text"]),
                    "start": round(item["start"] - start, 6),
                    "end": round(item["end"] - start, 6),
                }
                for item in selected
            ],
            "prompt": fields[3],
            "motion": _parse_motion(fields[4]),
        })
        used_ids.extend(line_ids)
    expected_ids = [item["id"] for item in timeline]
    if not shots or used_ids != expected_ids:
        raise AgentOutputFormatError(
            "分镜必须按顺序且不重不漏地覆盖全部台词 ID",
            {"expected_ids": expected_ids, "actual_ids": used_ids},
        )
    missing_subs = [line_id for line_id in expected_ids if line_id not in subtitle_marks]
    if missing_subs:
        raise AgentOutputFormatError(
            "必须为每一句台词写 SUB|台词ID|屏上文本（没有重点也要原样抄写、不加【】）",
            {"missing_ids": missing_subs},
        )
    return shots


def prepare_storyboard(draft_path: str | Path, *, tts_config: dict) -> dict:
    resolved_draft, draft = load_draft(draft_path, "财经稿件")
    for key in ("article", "cache_dir", "topic_record_id"):
        if not draft.get(key):
            raise WorkflowStepError(f"财经稿件缺少字段：{key}")
    cache_root = Path(draft["cache_dir"]).resolve()
    tts_result = compose_tts(str(draft["article"]), cache_root, tts_config)
    prompt = build_storyboard_prompt(tts_result["timeline"], radio=VIDEO_RADIO, size=VIDEO_SIZE)
    context_path = cache_root / STORYBOARD_CONTEXT_FILE_NAME
    context = {
        "status": "awaiting_storyboard",
        "line": MCP_ID,
        "draft_path": str(resolved_draft),
        "storyboard_prompt": prompt,
        "timeline": tts_result["timeline"],
        "tts_path": tts_result["output_path"],
        "tts_duration": tts_result["total_duration"],
        "tts_loudness": tts_result["loudness"],
    }
    context_path.write_text(json.dumps(context, ensure_ascii=False, indent=2), encoding="utf-8")
    context["context_path"] = str(context_path)
    return context


def load_prepared_tts(cache_root: str | Path) -> dict:
    """读取 prepare_storyboard 已落盘的完整配音与时间轴，不再次调用 generate_tts。"""
    _, context = load_draft(Path(cache_root) / STORYBOARD_CONTEXT_FILE_NAME, "分镜上下文")
    tts_path = Path(str(context.get("tts_path") or "")).resolve()
    timeline = context.get("timeline")
    if not tts_path.is_file():
        raise WorkflowStepError(
            "分镜上下文没有完整配音文件。请重新调用 finance_prepare_storyboard",
            {"tts_path": str(tts_path)},
        )
    if not isinstance(timeline, list) or not timeline:
        raise WorkflowStepError("分镜上下文缺少有效 timeline，请重新调用 finance_prepare_storyboard")
    return {
        "tts_path": tts_path,
        "timeline": timeline,
        "tts_duration": context.get("tts_duration"),
        "tts_loudness": context.get("tts_loudness"),
    }
