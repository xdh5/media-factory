"""财经配音、字幕文本与分镜解析。"""

from __future__ import annotations
import re, json
from pathlib import Path
from tools.generate_tts import generate_tts, generate_tts_fish
from tools.generate_tts.generate_tts_azure import generate_tts_azure
from workflows.finance.parameters import (
    MATERIAL_STRATEGIES,
    MCP_ID,
    STORYBOARD_CONTEXT_FILE_NAME,
)
from workflows.finance.errors.exceptions import AgentOutputFormatError, WorkflowStepError
from workflows.finance.tools.drafts import bare_text, load_draft


# 兼容旧分镜里的【】重点标记：去掉标记后与 karaoke 逐词动画一致，不再单独上色。
SUBTITLE_EMPHASIS_STYLE = {"font_size": 104, "primary_color": "#FFD54A"}
_COMMA_BREAK = set("，,")
_TRAILING_PUNCTUATION = re.compile(r"[，。！？、；：,.!?;:…]+$")


def _without_emphasis_marks(text: str) -> str:
    return str(text or "").strip().replace("【", "").replace("】", "")


def display_subtitle_text(text: str) -> str:
    """去掉重点括号和句尾标点，保留句子中间的标点。"""
    cleaned = _without_emphasis_marks(text)
    return _TRAILING_PUNCTUATION.sub("", cleaned).rstrip()


def parse_emphasis_segments(text: str) -> list[tuple[str, bool]]:
    """按【】切成 (原文片段, 是否重点)。括号本身不进入片段。"""
    raw = str(text or "")
    segments: list[tuple[str, bool]] = []
    index = 0
    while index < len(raw):
        char = raw[index]
        if char == "【":
            close = raw.find("】", index + 1)
            if close < 0:
                raise ValueError("重点标记【没有对应的】")
            inner = raw[index + 1:close]
            if "【" in inner or "】" in inner:
                raise ValueError("重点标记【】不能嵌套")
            if not inner.strip():
                raise ValueError("【】内不能为空")
            segments.append((inner, True))
            index = close + 1
            continue
        if char == "】":
            raise ValueError("重点标记】没有对应的【")
        next_mark = raw.find("【", index)
        if next_mark < 0:
            next_mark = len(raw)
        close = raw.find("】", index)
        if 0 <= close < next_mark:
            raise ValueError("重点标记】没有对应的【")
        segments.append((raw[index:next_mark], False))
        index = next_mark
    return segments


def ends_sentence(text: str) -> bool:
    """判断 TTS 台词原文是否收束了一个完整句子（不以逗号结尾）。"""
    cleaned = str(text or "").strip()
    return bool(cleaned) and cleaned[-1] not in _COMMA_BREAK


def display_subtitle_cue(text: str) -> str | list[dict]:
    """去标点后的屏上文本；有【】时返回带重点样式的分段。"""
    rendered: list[tuple[str, bool]] = []
    for chunk, emphasized in parse_emphasis_segments(str(text or "").strip()):
        shown = _without_emphasis_marks(chunk)
        if shown:
            rendered.append((shown, emphasized))
    if not rendered:
        return ""
    last_text, last_emphasized = rendered[-1]
    last_text = _TRAILING_PUNCTUATION.sub("", last_text).rstrip()
    if last_text:
        rendered[-1] = (last_text, last_emphasized)
    else:
        rendered.pop()
    if not rendered:
        return ""
    if not any(emphasized for _, emphasized in rendered):
        return "".join(chunk for chunk, _ in rendered)
    spans: list[dict] = []
    for chunk, emphasized in rendered:
        span: dict = {"text": chunk}
        if emphasized:
            span["style"] = dict(SUBTITLE_EMPHASIS_STYLE)
        spans.append(span)
    return spans


def _tts_config(config: dict) -> tuple[str, str]:
    voice = str(config.get("voice") or "").strip()
    rate = str(config.get("rate") or "").strip()
    if not voice:
        raise WorkflowStepError("tts_config.voice 不能为空")
    if not rate:
        raise WorkflowStepError("tts_config.rate 不能为空")
    return voice, rate


def compose_tts(article: str, cache_root: Path, tts_config: dict, ssml: list[str] | None = None) -> dict:
    voice, rate = _tts_config(tts_config)
    script = [{"text": line_text, "voice": voice} for line_text in (line.strip() for line in article.splitlines()) if line_text]
    if not script:
        raise WorkflowStepError("定稿正文没有可配音的台词")
    if ssml is not None:
        for line, markup in zip(script, ssml, strict=True):
            line['ssml'] = markup
    if voice.startswith('azure:'):
        from workflows.finance.tools.prepared_outro import append_outro
        result = generate_tts_azure(script[:-1], cache_root / 'narration.wav', rate=rate)
        return append_outro(result, script[-1]['text'], voice)
    engine = generate_tts_fish if voice.lower().startswith("fish:") else generate_tts
    return engine(
        script,
        cache_root / "narration.wav",
        rate=rate,
    )


def parse_storyboard(value: str, timeline: list[dict]) -> list[dict]:
    """按定稿行顺序关联画面、关键词和配音时间轴。"""
    rows = [row.strip() for row in value.splitlines() if row.strip()]
    if len(rows) != len(timeline):
        raise AgentOutputFormatError("分镜行数必须与定稿正文行数一致")
    shots = []
    for row, line in zip(rows, timeline):
        description, keywords = (field.strip() for field in row.split("|", 1))
        selected = [line]
        line_ids = [line["id"]]
        start, end = selected[0]["start"], selected[-1]["end"]
        shots.append({
            "id": f"shot-{len(shots) + 1:03d}", "line_ids": line_ids,
            "audio_start": start, "audio_end": end, "duration": round(end - start, 6),
            "description": description, "keywords": keywords,
            "subtitle": "".join(row["text"] for row in selected),
            "subtitle_lines": [{"text": row["text"], "start": round(row["start"] - start, 6),
                                "end": round(row["end"] - start, 6),
                                "ends_sentence": ends_sentence(row["text"])} for row in selected],
        })
    return shots


def resolve_material_strategy(value: str) -> str:
    """校验素材策略取值。"""
    strategy = str(value or "").strip()
    if strategy not in MATERIAL_STRATEGIES:
        raise WorkflowStepError(
            f"material_strategy 必须是 {'、'.join(MATERIAL_STRATEGIES)} 之一",
            {"material_strategy": strategy},
        )
    return strategy


def prepare_storyboard(draft_path: str | Path, *, tts_config: dict, material_strategy: str) -> dict:
    strategy = resolve_material_strategy(material_strategy)
    resolved_draft, draft = load_draft(draft_path, "财经稿件")
    for key in ("article", "cache_dir", "topic_record_id"):
        if not draft.get(key):
            raise WorkflowStepError(f"财经稿件缺少字段：{key}")
    cache_root = Path(draft["cache_dir"]).resolve()
    tts_result = compose_tts(str(draft["article"]), cache_root, tts_config, draft.get('ssml'))
    context_path = cache_root / STORYBOARD_CONTEXT_FILE_NAME
    context = {
        "status": "ready_to_search",
        "line": MCP_ID,
        "material_strategy": strategy,
        "draft_path": str(resolved_draft),
        "storyboard_text": draft["storyboard"],
        "timeline": tts_result["timeline"],
        "tts_path": tts_result["output_path"],
        "tts_duration": tts_result["total_duration"],
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
            "分镜上下文没有完整配音文件。请重新调用 finance_start_production",
            {"tts_path": str(tts_path)},
        )
    if not isinstance(timeline, list) or not timeline:
        raise WorkflowStepError("分镜上下文缺少有效 timeline，请重新调用 finance_start_production")
    return {
        "tts_path": tts_path,
        "timeline": timeline,
        "tts_duration": context.get("tts_duration"),
    }
