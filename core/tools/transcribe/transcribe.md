# 语音转文字

实现在 `core/tools/transcribe`，**不是 MCP**。工作流与 Agent 只调用公开方法 `transcribe`。只调用 Groq Whisper 做语音识别，不调用文本大模型。文案校对、措辞修改和广告审核交给宿主 Agent。

## 用法

`transcribe(media_path, language="zh")`：把**本地**音视频转成文字。分享链接请先调用 media-collector 子仓库的 `download_video.download`，再用返回的 `video_path`。返回 `text` 和 `raw_text`，两者都是识别原文。

## 配置

`.env` 需要 `GROQ_API_KEY`。
