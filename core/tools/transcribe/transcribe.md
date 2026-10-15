# 语音转文字

实现在 `core/tools/transcribe`，**不是 MCP**。工作流与 Agent 只调用公开方法 `transcribe`。中文识别后会再调用一次模型，只补标点并改错别字。

## 用法

`transcribe(media_path, language="zh")`：把**本地**音视频转成文字。分享链接请先调用 media-collector 子仓库的 `download_video.download`，再用返回的 `video_path`。返回 `text`（中文为校对后正文）和 `raw_text`（识别原文）。

## 配置

`.env` 需要 `GROQ_API_KEY`。
