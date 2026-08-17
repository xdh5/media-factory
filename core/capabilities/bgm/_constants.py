"""BGM（背景音乐）常量配置。

- BGM_LIBRARY：曲库，select_bgm 按 mood 从里面匹配。
- BGM_FILE_DIR：static 目录实际路径，运行时直接读。
- 混音参数：渲染视频时 BGM 与对白/BGM 衔接的默认音量与淡入淡出时长。
"""

from __future__ import annotations

from pathlib import Path

# ---- 曲库根目录（同级 static/，随代码打包进镜像）----
_BGM_FILE_DIR = Path(__file__).resolve().parent / "static"


def _p(filename: str) -> str:
    """把 static 下的文件名解析为绝对路径字符串。"""
    return str(_BGM_FILE_DIR / filename)


# ---- 可匹配的情绪全集（Agent 拿这个做枚举修正）----
# 情绪使用 GEMS-9（Geneva Emotional Music Scale）九维模型，
# 避免把“专注”“励志”等使用场景误当成音乐情绪。
MOOD_DESCRIPTIONS = {
    "wonder": "惊奇与敬畏",
    "transcendence": "超然与沉浸",
    "tenderness": "温柔与亲密",
    "nostalgia": "怀旧与追忆",
    "peacefulness": "宁静与放松",
    "power": "力量与崇高",
    "joyful_activation": "愉悦与活力",
    "tension": "紧张与不安",
    "sadness": "悲伤与低落",
}
SUPPORTED_MOODS = list(MOOD_DESCRIPTIONS)


# ---- BGM 曲库 ----
# 每首曲对应：id / name / moods / filename / path
# 匹配顺序就是列表顺序，Agent 想改优先级只需重排列表。
BGM_LIBRARY: list[dict] = [
    {
        "id": "cinematic_inspirational_piano",
        "name": "电影感励志钢琴氛围（Music for Creators）",
        "moods": ["wonder", "tenderness", "peacefulness"],
        "filename": "cinematic-inspirational-piano-ambient-128209.mp3",
        "path": _p("cinematic-inspirational-piano-ambient-128209.mp3"),
    },
    {
        "id": "ambient_piano",
        "name": "氛围钢琴循环（SoulProdMusic）",
        "moods": ["joyful_activation", "wonder", "peacefulness"],
        "filename": "ambient-piano-144861.mp3",
        "path": _p("ambient-piano-144861.mp3"),
    },
    {
        "id": "ambient_techno",
        "name": "氛围极简 Techno（Musinova）",
        "moods": ["transcendence", "peacefulness"],
        "filename": "ambient-minimal-techno-538526.mp3",
        "path": _p("ambient-minimal-techno-538526.mp3"),
    },
]

# ---- 渲染时默认混音参数（供视频合成阶段取用）----
BGM_FIXED_GAIN = 0.28            # BGM 固定音量（对白优先，整体压低）
BGM_FADE_IN_SECONDS = 1.0        # 片段起始淡入时长
BGM_FADE_OUT_SECONDS = 2.0       # 片段结尾淡出时长
