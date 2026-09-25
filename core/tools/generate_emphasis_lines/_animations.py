r"""重点句大字的入场动画库。

每个动画是一个纯函数：给定落点坐标与动画时长，返回一段 ASS 覆盖标签。
标签拼在行文本前，\move 负责位移、\fscx/\fscy + \t 负责挤压回弹。
新增动画时在 ANIMATIONS 里注册即可，选取方按名称随机挑。
"""

from __future__ import annotations

from ._constants import EMPHASIS_ANIMATION_DURATION


def _slam(x: int, y: int, duration: float) -> str:
    """砸落：从画面上方狠狠砸到落点，落地瞬间横向拉伸回弹。"""
    drop = 320
    ms = round(duration * 1000)
    settle = round(ms * 0.65)
    bounce = round(ms * 1.0)
    rest = round(ms * 1.35)
    return (
        rf"\move({x},{y - drop},{x},{y},0,{ms})"
        rf"\fscx124\fscy78"
        rf"\t(0,{settle},\fscx100\fscy100)"
        rf"\t({settle},{bounce},\fscx107\fscy107)"
        rf"\t({bounce},{rest},\fscx100\fscy100)"
    )


def _fly_right(x: int, y: int, duration: float) -> str:
    """飞入：从画面右侧嗖地飞进落点，带轻微加速收尾的缩小回正。"""
    offset = 900
    ms = round(duration * 1000)
    return (
        rf"\move({x + offset},{y},{x},{y},0,{ms})"
        rf"\fscx88\fscy88"
        rf"\t(0,{ms},\fscx100\fscy100)"
    )


def _pop(x: int, y: int, duration: float) -> str:
    """弹出：原地从小到大弹出来，带过冲回弹。"""
    ms = round(duration * 1000)
    overshoot = round(ms * 0.7)
    rest = round(ms * 1.2)
    return (
        rf"\pos({x},{y})"
        rf"\fscx40\fscy40"
        rf"\t(0,{overshoot},\fscx112\fscy112)"
        rf"\t({overshoot},{rest},\fscx100\fscy100)"
    )


ANIMATIONS = {
    "slam": _slam,
    "fly_right": _fly_right,
    "pop": _pop,
}

SUPPORTED_ANIMATIONS = tuple(ANIMATIONS)


def entrance_tags(name: str, x: int, y: int, duration: float = EMPHASIS_ANIMATION_DURATION) -> str:
    r"""按名称取入场动画标签；未知名称回退为静止 \pos。"""
    builder = ANIMATIONS.get(str(name or "").strip())
    if builder is None:
        return rf"\pos({x},{y})"
    return builder(int(x), int(y), float(duration))
