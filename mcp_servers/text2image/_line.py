"""文生图业务线配置。"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from pathlib import Path

from ._errors import WorkflowStepError

_LINE_MODULES = {
    "finance": "workflows.finance",
    "life_copy": "workflows.life_copy",
}


@dataclass(frozen=True)
class Text2ImageLine:
    id: str
    visual_style: str
    video_size: str
    video_radio: str
    bgm_id: str
    bgm_gain: float
    mix_gain: float
    bgm_fade_in: float
    bgm_fade_out: float
    tts_voice: str
    tts_rate: str
    tts_trim_trailing_silence: bool
    cover_frame_seconds: float
    topic_deduplication_days: int
    matrixmedia_account_group: str
    article_prompt_path: Path
    examples_dir: Path
    hooks_path: Path
    shot_image_rules_path: Path
    extra_reference_image_path: Path | None
    intro: str = "slide_in_shutter"
    intro_sfx_path: Path | None = None
    use_image_library: bool = False


def list_line_ids() -> list[str]:
    return list(_LINE_MODULES)


def load_line(line_id: str) -> Text2ImageLine:
    normalized = str(line_id or "").strip()
    module_name = _LINE_MODULES.get(normalized)
    if module_name is None:
        available = "、".join(list_line_ids())
        raise WorkflowStepError(f"未知文生图工作流线：{line_id!r}。当前可用：{available}")
    module = import_module(module_name)
    data = dict(module.get_line())
    data.setdefault("intro", "slide_in_shutter")
    data.setdefault("intro_sfx_path", None)
    data.setdefault("use_image_library", False)
    allowed = {item.name for item in Text2ImageLine.__dataclass_fields__.values()}
    return Text2ImageLine(**{key: value for key, value in data.items() if key in allowed})
