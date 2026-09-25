"""章节时间轴条默认样式与常量。

时间轴条 = 一条贴在画面顶部或底部的横条，按章节分段展示 AI 生成的段落标题；
当前时段标题高亮，进度色随播放时间从左到右推进。
"""

from __future__ import annotations

TIMELINE_POSITIONS = ("top", "bottom")

# 段落标题字体：与正文 karaoke 字幕同款普推黑体（static/font/PUTUI-Regular.ttf）。
TIMELINE_DEFAULT_FONT_FAMILY = "PUTUI"

DEFAULT_TIMELINE_STYLE: dict = {
    "font": TIMELINE_DEFAULT_FONT_FAMILY,
    # 段落标题字号（像素，1920x1080 下）。
    "font_size": 30,
    # 横条高度（像素）。
    "bar_height": 56,
    # 横条左右留白（像素，0 = 紧贴左右边缘）。
    "margin_horizontal": 0,
    # 横条贴边距离 = 画布高度 × 该系数（top: 条顶 = ratio*高度；bottom: 条底 = 高度*(1-ratio)）。
    # 0 = 紧贴画面上/下边缘，无 padding。
    "margin_vertical_ratio": 0,
    # 横条底色与不透明度（0~1，1 = 实心）。
    "track_color": "#0A0A0A",
    "track_opacity": 0.60,
    # 未激活段落标题颜色。
    "title_color": "#D8D8D8",
    # 当前时段标题高亮颜色（加粗）。
    "active_color": "#FFD54A",
    # 进度推进色与不透明度（横条内从左往右扫过的那层颜色，浅灰）。
    "progress_color": "#D9D9D9",
    "progress_opacity": 0.45,
    # 段落分隔线颜色与不透明度。
    "separator_color": "#FFFFFF",
    "separator_opacity": 0.50,
    # 分隔线宽度（像素）。
    "separator_width": 2,
}

# 章节标题约束：给千问生成与兜底截断用。
TITLE_MIN_CHARS = 1
TITLE_MAX_CHARS = 6

# AI 生成失败时的兜底前缀。
FALLBACK_TITLE_PREFIX = "第"
