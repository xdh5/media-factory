"""重点句大字图层常量。

2026-09-23 新增：正文里「第一，xxx，yyy」这类提示/总结句，
提示词不上大字，内容段逐行以字魂群英体大字落在画面中央，
白字黑边、重点词标红（开头封面钩子的红 #E30F13），
入场动画从封装动画库里随机挑一种；本句读完后大字整体消失。
"""

from __future__ import annotations

DETECTION_CACHE_FILE_NAME = "emphasis-detection.json"

# 大字样式：字魂群英体（同开头钩子标题），白字黑边；重点词在行内标红。
# 2026-09-23 用户要求字号 -20%（120 → 96）；2026-09-24 用户要求 +10%（96 → 106）。
EMPHASIS_FONT_FAMILY = "zihunqunyingti"
EMPHASIS_FONT_SIZE = 106
EMPHASIS_PRIMARY_COLOR = "#FFFFFF"
EMPHASIS_HIGHLIGHT_COLOR = "#E30F13"  # 与封面/钩子标题的红一致
EMPHASIS_OUTLINE_COLOR = "#000000"
EMPHASIS_OUTLINE = 6
EMPHASIS_BOLD = False

# 版式：整块大字垂直居中（2026-09-24 用户要求：多行堆叠后 40% 偏上，改回居中 50%），
# 水平居中，新行依次向下堆叠；每行的最终落点按组内总行数提前算好，出现先后不跳动。
# 居中后块顶 padding（占 1080 高，字号 106、行距 148）：
#   1 行 ≈ 45%、2 行 ≈ 38%、3 行 ≈ 31%（6 行 ≈ 11%）。
EMPHASIS_CENTER_RATIO = 0.5
EMPHASIS_LINE_HEIGHT = 1.4  # 行距 = 字号 × 该系数
# 重点字幕单行最多约 14 个全角字；超长内容最多拆成两行，并按语义边界换行。
# 同一重点句画面最多堆叠 5 行，放不下的后续 cue 保留为普通字幕。
EMPHASIS_MAX_LINE_WIDTH = 28  # 逻辑宽：全角字计 2，ASCII 字符计 1
EMPHASIS_MAX_WRAPPED_LINES = 2
EMPHASIS_MAX_VISIBLE_LINES = 5

# 入场动画库：每行大字进场时随机挑一种；生产可用配置覆盖列表。
EMPHASIS_ANIMATIONS = ("slam", "fly_right")
EMPHASIS_ANIMATION_DURATION = 0.28  # 秒，入场动画时长

# 2026-09-24 用户要求：大字驻留期间普通 karaoke 字幕直接不展示（旧版让位到底部已废弃），
# 通过给 cue 打 hidden 标记由 generate_final_video 过滤字幕层实现。
