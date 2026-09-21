---
name: psychology-quiz-video
description: 使用独立心理测试 MCP 制作财经、成功学与人性类生活情境测试短视频；适用于“做心理测试视频”“做ABCD测试”等请求，不用于传统财经原稿改编。
---

# 心理测试视频

MCP 入口：`python -m core.mcp.psychology_quiz`。写稿、分镜、正版视频素材选择和字幕版式均属于该业务线；禁止调用 Finance MCP 内部实现。

开始交互式生产前，必须让用户明确北京时间计划发布日期 `publish_date`。未明确日期时，不得创建 run、生产或写入产物表。

## 内容

- 第一句必须明确说“心理测试”，用一句夸张但不虚假的承诺制造好奇缺口。
- 必须提供具体生活场景、A/B/C/D 四个合理选项和四段独立结果。
- 结果要像朋友吐槽，写具体动作、群聊、账单、聚餐、快递等生活画面，避免理论术语。
- 禁止医学诊断、发财承诺和人生结局预测。
- 正文不少于300个非空白字符，不设最大长度；每行不超过20字。
- 使用公共话题库做30天查重，并把题目写入 D1 `scenario_quiz_questions`。

## 生产

1. `psychology_quiz_get_prompt` 读取 Prompt 和最近30天话题。
2. 宿主 Agent 写稿；GitHub Action 无宿主 Agent 时允许千问写稿。
3. `psychology_quiz_save_draft` 保存稿件。
4. `psychology_quiz_start_storyboard` 后只轮询同一个 `psychology_quiz_poll_task`。
5. 宿主 Agent 写分镜；A/B/C/D 四个结果必须使用四个独立镜头，VIDEO 行使用英文素材检索词。
6. `psychology_quiz_start_video_search` 后轮询，按 Pexels → Pixabay → Coverr 顺序取得候选。
7. 宿主 Agent 根据 `intro_image_prompt` 生成一张写实的16:9片头静态图；只有片头允许生图，正文禁止生图。
8. 宿主 Agent 选择每个正文镜头的候选后调用 `psychology_quiz_start_download_videos`，继续轮询下载与规范化。
9. 用返回的 `video_manifest_path`、片头图的 `intro_image_path` 调用 `psychology_quiz_start_finish_video` 合成。

片头先用写实静态图播放 `slide_in_shutter` 动画，再切到选中的实拍视频。除这张片头图外，禁止生图或使用静态图库。来源署名不烧进视频；素材清单保留来源页、作者和署名文案，并输出 `attribution-comment.txt` 供发布后写入评论。心理测试成片额外调用 `core.tools.quiz_timeline`：选项读完后按 A→A+B→A+B+C→A+B+C+D 累积显示，结果读完后逐个点亮；同时把整条视频按内容划分为章节，每段显示简短标题，章节宽度必须与真实时长成比例，拖到相应时间位置时正好进入该标题对应内容。章节条可配置在顶部或底部，默认底部；真正拖动仍使用播放器原生进度条。

耗时步骤必须使用 `start + poll`，不得重复启动。

## 字幕

字幕位置和样式通过 `production_config` 独立配置：

```json
{
  "subtitle_style": {
    "font_size": 92,
    "primary_color": "#FFFFFF",
    "outline_color": "#000000",
    "outline": 5,
    "bold": true,
    "max_lines": 2
  },
  "subtitle_position": {
    "alignment": 5,
    "margin_vertical_ratio": 0.5
  }
}
```

心理测试字幕默认放在屏幕正中。屏上字幕自动删除句尾标点，句子中间的逗号、顿号等标点保留；TTS 仍使用原文标点。未传字幕样式时沿用公共样式，不影响其他业务线。

## 固定制作参数

- TTS：`zh-CN-YunjianNeural`、`+20%`、裁剪尾部静音。
- BGM：从 `nothing_to_fare.mp3` 与 `aware.mp3` 中选一首。
- 片头：一张写实生图，使用 `slide_in_shutter` 动画；正文使用正版实拍视频。
- 本地成片目录：`output/psychology_quiz/run-YYYYMMDD/`。
- 本地制作不自动上传 R2；GitHub Workflow 成片才自动交付 R2。
- 成片完成后等待用户确认，禁止自动发布或清缓存。
