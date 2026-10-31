"""向宿主提供成片字幕、重点句与章节定稿输入。"""

from pathlib import Path

from core.tools.generate_emphasis_lines.generate_emphasis_lines import _build_sentences, _display_text
from core.tools.generate_emphasis_lines._detect import _SYSTEM_PROMPT, _build_prompt
from core.tools.generate_final_video.generate_final_video import _subtitle_cues, subtitle_plain_text
from ..errors import WorkflowStepError
from .save_draft import load_draft
from .storyboard import load_prepared_tts, parse_storyboard
from .production_config import _production_config
from .video_layers import _with_display_text, _auto_hook_lines, chapter_editorial_input


def get_video_editorial_input(draft_path: str, storyboard_text: str, production_config: dict) -> dict:
    """复用合成阶段的分镜、钩子和显示文本规则，不请求模型。"""
    _, draft = load_draft(draft_path, "财经稿件")
    settings = _production_config(production_config)
    tts = load_prepared_tts(Path(draft["cache_dir"]))
    shots = parse_storyboard(storyboard_text, tts["timeline"])
    subtitle_shots = [{"id": shot["id"], "subtitle": shot["subtitle"],
                       "subtitle_lines": shot.get("subtitle_lines") or []} for shot in shots]
    rows = subtitle_shots[0]["subtitle_lines"]
    hook_lines = settings["hook_lines"]
    if hook_lines is None:
        hook_lines = _auto_hook_lines(rows, str(draft.get("source_hook") or ""))
    for row in rows[:max(0, hook_lines)]:
        row["position"] = settings["hook_subtitle_position"]
    cues = _subtitle_cues(_with_display_text(subtitle_shots), shots)
    candidates = [(index, _display_text(cue["text"]), cue.get("ends_sentence"))
                  for index, cue in enumerate(cues)
                  if "position" not in cue and str(cue.get("language") or "zh") == "zh"
                  and _display_text(cue["text"])]
    sentences, _ = _build_sentences(candidates)
    segments, chapters = chapter_editorial_input(shots, settings["chapter_timeline"])
    texts = list(dict.fromkeys(subtitle_plain_text(cue["text"]) for cue in cues
                              if "position" not in cue and str(cue.get("language") or "zh") == "zh"))
    return {
        "draft_path": draft_path,
        "system_prompt": _SYSTEM_PROMPT,
        "emphasis_prompt": _build_prompt(list(enumerate(sentences))),
        "subtitle_texts": texts,
        "sentences": sentences,
        "chapters": [{**segment, "text": text} for segment, text in zip(segments, chapters)],
        "required_output": {
            "emphasis_lines": "groups：按 emphasis_prompt 定稿；无重点句传 []",
            "secondary_subtitles": "translations：中文原文到英文译文的对象，逐条对应 subtitle_texts，简短口语化",
            "chapter_timeline": "titles：与 chapters 等长的非空短标题数组，每项最多 6 字",
        },
        "instruction": "由宿主完成定稿，将结果分别合并到 production_config 对应对象后传给下载自动合成或成片工具。保留统一生产配置；不得为了省略定稿关闭图层。",
    }


def validate_video_editorial(draft_path: str, storyboard_text: str, production_config: dict) -> None:
    """在下载和渲染前校验宿主定稿，缺失时直接返回可修正的参数错误。"""
    from core.tools.generate_emphasis_lines._detect import validate_emphasis_groups
    inputs = get_video_editorial_input(draft_path, storyboard_text, production_config)
    settings = _production_config(production_config)
    emphasis = settings["emphasis_lines"]
    if emphasis.get("enabled", True):
        groups = emphasis.get("groups")
        if not isinstance(groups, list) or len(validate_emphasis_groups({"groups": groups}, inputs["sentences"])) != len(groups):
            raise WorkflowStepError("emphasis_lines.groups 必须包含宿主定稿的完整重点句、断行和逐行重点词；无重点句传 []")
    secondary = settings["secondary_subtitles"]
    if secondary.get("enabled", True) and inputs["subtitle_texts"]:
        translations = secondary.get("translations")
        if not isinstance(translations, dict) or any(not isinstance(translations.get(text), str) or not translations[text].strip() for text in inputs["subtitle_texts"]):
            raise WorkflowStepError("secondary_subtitles.translations 必须包含全部中文原文对应的英文译文")
    if inputs["chapters"]:
        titles = settings["chapter_timeline"].get("titles")
        if not isinstance(titles, list) or len(titles) != len(inputs["chapters"]) or any(not isinstance(title, str) or not 1 <= len(title.strip()) <= 6 for title in titles):
            raise WorkflowStepError("chapter_timeline.titles 必须与章节等长，每项为 1 到 6 字的宿主标题")
