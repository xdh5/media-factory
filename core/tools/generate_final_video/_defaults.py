"""成片风格默认值：字幕版式与片头钩子展示。

财经线（含原心灵鸡汤内容）统一使用这一套展示策略；
业务侧只覆盖真正属于本次生产差异的项（BGM、片头音效、账号组、素材策略）。
改这里即所有生产同时生效。
"""

from __future__ import annotations

# 字幕：karaoke 预设（白字黑边，逐字从左到右扫过金黄色），整屏居中。
DEFAULT_SUBTITLE_STYLE = {"preset": "karaoke", "highlight_color": "#FFD54A"}
DEFAULT_SUBTITLE_POSITION = {"alignment": 5, "margin_vertical_ratio": 0.5}

# 片头钩子：首个镜头的前 N 行（数据库原稿的黄金钩子）在旧版底部位置逐行出，
# 同一时间段用稿件标题居中做覆盖标题；读完钩子后正文回到 DEFAULT_SUBTITLE_POSITION。
DEFAULT_HOOK_LINES = 3
DEFAULT_HOOK_SUBTITLE_POSITION = {"alignment": 2, "margin_vertical_ratio": 0.1}
# 钩子标题：字魂群英体（2026-09-23 用户指定，商用需授权）、字号 110×1.5=165。
# 字体族名 zihunqunyingti（TTF 内英文族名），需保证 static/font/ 字魂群英体.ttf 在包内。
# 标题体自带粗壮笔画，不再叠加伪粗体；黑/白描边 7px 保证视频底上可读。
DEFAULT_HOOK_TITLE_STYLE = {"font": "zihunqunyingti", "font_size": 165, "bold": False, "outline": 7}
# 标题块位置：margin_vertical_ratio 是整块标题墨迹中心的画布高度占比。
# 2026-09-23 用户要求靠上：0.5（正中）→ 0.4。
DEFAULT_HOOK_TITLE_POSITION = {"alignment": 5, "margin_vertical_ratio": 0.4}
# 标题配色：单行 = 红字黑边；多行 = 按标点断行，第一行字幕黄黑边，其余行红字白边。
DEFAULT_HOOK_TITLE_SINGLE_COLOR = "#E30F13"
DEFAULT_HOOK_TITLE_FIRST_LINE_COLOR = "#FFD54A"
DEFAULT_HOOK_TITLE_OTHER_LINE_COLOR = "#E30F13"
DEFAULT_HOOK_TITLE_DARK_OUTLINE = "#000000"
DEFAULT_HOOK_TITLE_LIGHT_OUTLINE = "#FFFFFF"
DEFAULT_HOOK_TITLE_LINE_HEIGHT = 1.26  # 行高 = 字号 × 该系数，用于多行堆叠定位
