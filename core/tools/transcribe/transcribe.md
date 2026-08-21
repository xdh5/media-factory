# 语音转文字

实现在 `core/tools/transcribe`，**不是 MCP**。工作流与 Agent 只调用公开方法 `transcribe`。**不做 ASR 错别字校对。**

## 用法

`transcribe(media_path, language="zh")`：把**本地**音视频转成文字。分享链接请先调用 `core.tools.download.download`，再用返回的 `video_path`。返回 `text`（Whisper 原文）和 `segments`。

## 配置

`.env` 需要 `GROQ_API_KEY`。
