# 心灵鸡汤 MCP

入口：`python -m core.mcp.psychology_quiz`。

该 MCP 独立负责心灵鸡汤的文章成稿、分镜、正版视频素材搜索、字幕版式和成片记录，不调用 Finance MCP 内部实现。内容来源为用户提供文章：宿主 Agent 按成稿规则压缩到 1000 字左右，保留原文结构、黄金钩子和原话，只改细枝末节；不足 1000 字直接用原文；品牌一律改为财富研习岛。

## 流程

```text
psychology_quiz_get_prompt
→ 宿主 Agent 按文章成稿规则产出 article 与 intro_scene
→ psychology_quiz_save_draft
→ psychology_quiz_start_storyboard
→ psychology_quiz_poll_task
→ psychology_quiz_start_video_search
→ psychology_quiz_poll_task
→ 宿主 Agent 选择候选视频
→ psychology_quiz_start_download_videos
→ psychology_quiz_poll_task
→ psychology_quiz_start_finish_video
→ psychology_quiz_poll_task
```

第一个镜头使用宿主 Agent 生成的写实静态图播放片头动画（场景描述 `intro_scene` 从文章提炼），之后的视频素材调用 `core.tools.stock_video`，按 Pexels、Pixabay、Coverr 三站兜底。素材来源只写入成片清单的 `stock_video_attributions` 和评论文案文件，不显示在视频画面中。

字幕通过 `production_config.subtitle_style` 和 `production_config.subtitle_position` 独立控制；未传时使用公共默认值。

本地产物保存到 `output/psychology_quiz/run-YYYYMMDD/`，并以 `business_line=psychology_quiz`、`content_kind=article` 幂等写入 `production_outputs`。
