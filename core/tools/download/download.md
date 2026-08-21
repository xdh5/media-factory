# 视频下载

实现在 `core/tools/download`，**不是 MCP**。工作流与 Agent 只调用公开方法 `download`。

## 用法

`download(share_text, output_path=None)`：解析抖音/快手/小红书/B 站等分享口令或链接，下载到本地。返回 `platform`、`title`、`video_id`、`video_path`、`cover_url`。哔哩哔哩分轨时会合并成一个 mp4。默认写到 `data/download/videos/`。

语音转文字请用 `core.tools.transcribe.transcribe`，把这里的 `video_path` 传进去。

## 配置

抖音下载失败时在 `.env` 填写有效 `DOUYIN_COOKIE`。
