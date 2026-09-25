"""成片风格默认值：字幕版式与片头钩子展示。

财经线（含原心灵鸡汤内容）统一使用这一套展示策略；
业务侧只覆盖真正属于本次生产差异的项（BGM、片头音效、账号组、素材策略）。
改这里即所有生产同时生效。
"""

from __future__ import annotations

# 字幕：karaoke 预设（白字黑边，逐字从左到右扫过金黄色），整屏居中。
# 2026-09-23 用户要求整体字幕 +30%（zh 语言默认 100px → 130px）；
# 2026-09-24 用户要求 -20%（130 → 104）。
DEFAULT_SUBTITLE_STYLE = {"preset": "karaoke", "highlight_color": "#FFD54A", "font_size": 104}

# BGM 增益：2026-09-23 用户要求在财经线 0.84 基础上 -20%。
DEFAULT_BGM_GAIN = 0.672

# 双语字幕（2026-09-23 新增，2026-09-23 晚用户要求移除）：默认关闭。
# 英文字号 = 中文字号 × font_size_ratio；白字黑边静态显示，不参与 karaoke 动画。
# position.follow_chinese：英文不贴底，跟在中文块正下方 gap 像素处，
# 按每条中文实际换行行数（最多 2 行）计算 y，用 \pos 绝对定位。
DEFAULT_SECONDARY_SUBTITLES: dict = {
    "enabled": False,
    "font_size_ratio": 0.4,
    "style": {"primary_color": "#FFFFFF", "outline_color": "#000000", "bold": True, "uppercase": False},
    "position": {"follow_chinese": True, "gap": 25},
}
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

# 章节时间轴条：横条分段展示 AI 生成的段落标题，当前时段高亮、进度色随播放推进。
# 2026-09-23 新增；2026-09-23 晚用户要求移除，默认关闭。
# position = top（贴上方）/ bottom（贴下方）。
DEFAULT_CHAPTER_TIMELINE: dict = {
    "enabled": False,
    "position": "bottom",
    "segment_count": 8,       # 章节数（按镜头时长均分边界，AI 起标题）
    "ai_titles": True,        # False = 用章节开头文字兜底，不调千问
    "font_size": 30,
    "bar_height": 56,
    "margin_horizontal": 0,   # 0 = 紧贴左右边缘
    "margin_vertical_ratio": 0,  # 0 = 紧贴画面上/下边缘，无 padding
}

# 重点句大字（2026-09-23）：「第一，xxx，yyy」这类提示/总结句由 AI 识别（不用关键词匹配），
# 提示词不上大字；内容段每段一行字魂群英体大字（白字黑边、重点词标红 #E30F13），
# 读到哪段哪行带随机入场动画落在大字块中心=画面高度 40% 处、逐行堆叠驻留，本句读完整体消失；
# 大字占用期间普通 karaoke 字幕让位到底部。
# 2026-09-23 用户要求：位置 50% → 40%，字号 -20%（120 → 96）；
# 2026-09-24 用户要求：字号 +10%（96 → 106）。
DEFAULT_EMPHASIS_LINES: dict = {
    "enabled": True,
    "font_size": 106,
    "highlight_color": "#E30F13",
    "animations": ["slam", "fly_right", "pop"],
}
