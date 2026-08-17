"""按 mood 匹配或按 id 精确选择内置背景音乐。

返回 BGM 的 id / 展示名 / 文件绝对路径，供后续视频合成阶段混音用。
选择失败时错误 details 会给出可用情绪或 ID，Agent 可直接修正后重试。
"""

from __future__ import annotations

from pathlib import Path

from ._constants import (
    BGM_LIBRARY,
    SUPPORTED_MOODS,
)
from ._errors import (
    BGMFileNotFoundError,
    BGMIDNotFoundError,
    BGMNotFoundError,
    InvalidParameterError,
)

__all__ = ["select_bgm"]


def _validate_mood(mood: str) -> None:
    if not isinstance(mood, str) or not mood.strip():
        raise InvalidParameterError("mood", "mood 不能为空字符串，必须从支持的枚举中选一个")
    if mood not in SUPPORTED_MOODS:
        raise InvalidParameterError(
            "mood",
            f"mood='{mood}' 不在支持枚举 {SUPPORTED_MOODS}，请选最接近的一项再调用",
        )


def _validate_id(bgm_id: str) -> None:
    if not isinstance(bgm_id, str) or not bgm_id.strip():
        raise InvalidParameterError("id", "id 不能为空，必须传入曲库中的 BGM ID")


def _result(bgm: dict, matched_mood: str | None) -> dict:
    """构造与输出 Schema 一致的选曲结果。"""
    return {
        "id": bgm["id"],
        "name": bgm["name"],
        "path": bgm["path"],
        "matched_mood": matched_mood,
    }


def select_bgm(mood: str | None = None, id: str | None = None) -> dict:
    """按情绪匹配或按 ID 精确选择一首 BGM。

    返回 dict（可直接 json.dumps）：
    {"id": "ambient_piano",
     "name": "氛围钢琴循环（SoulProdMusic）",
     "path": "/app/core/capabilities/bgm/static/xxx.mp3",
     "matched_mood": "peacefulness"}

    选择规则：
    1. mood 和 id 必须且只能传入一个。
    2. 传 id 时精确选择，matched_mood 为 null。
    3. 传 mood 时按 BGM_LIBRARY 声明顺序选择第一首匹配曲目。

    抛错：
    - InvalidParameterError：参数为空、同时传入或 mood 不在枚举。
    - BGMIDNotFoundError：id 在曲库中不存在。
    - BGMNotFoundError：所有 BGM 都不满足 mood，
      details 里列出全部支持的 mood 以及每首曲的 moods，
      方便 Agent 立刻修正重试。
    """
    if mood is None and id is None:
        raise InvalidParameterError("mood/id", "mood 和 id 必须传入一个")
    if mood is not None and id is not None:
        raise InvalidParameterError("mood/id", "mood 和 id 不能同时传入，请只保留一个")

    if id is not None:
        _validate_id(id)
        for bgm in BGM_LIBRARY:
            if bgm["id"] != id:
                continue
            if not Path(bgm["path"]).is_file():
                raise BGMFileNotFoundError(bgm_id=id, path=bgm["path"])
            return _result(bgm, None)
        raise BGMIDNotFoundError(bgm_id=id)

    _validate_mood(mood)

    for bgm in BGM_LIBRARY:
        if mood not in bgm["moods"]:
            continue

        # 校验文件是否真的存在（防止打包漏 static/ 时静默出空路径）
        if not Path(bgm["path"]).is_file():
            continue

        return _result(bgm, mood)

    raise BGMNotFoundError(mood=mood)
