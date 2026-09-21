# 视频下载

实现在 `core/tools/download`，**不是 MCP**。工作流与 Agent 只调用公开方法 `download`。

解析引擎移植自 [xingchen-video-download](https://github.com/xingchenyd/xingchen-video-download)，只保留其下载服务（yt-dlp 解析 + 访客 Cookie + 视频号元宝接口），未引入其 FastAPI 服务、前端页面与浏览器扫码登录。

## 用法

`download(share_text, output_path=None)`：解析分享口令或链接，下载到本地。返回 `platform`、`title`、`video_id`、`video_path`、`cover_url`。分轨视频（独立音轨）会自动用 ffmpeg 合并成一个 mp4。默认写到 `data/download/videos/`。

语音转文字请用 `core.tools.transcribe.transcribe`，把这里的 `video_path` 传进去。

## 支持平台

| 平台 | 免配置 | 说明 |
| --- | --- | --- |
| 抖音 | ✅ | 自动获取 ttwid 访客 Cookie |
| 哔哩哔哩 | ✅ | 自动获取 buvid3，最高 1080P |
| 微博 | ✅ | 自动获取访客 Cookie |
| 小红书 | ✅ | 自动获取访客 Cookie |
| YouTube | ✅ | 需网络可达 |
| TikTok | ✅ | 需网络可达 |
| 微信视频号 | ❌ | 需在 `.env` 配置 `SPH_COOKIE`（腾讯元宝 Cookie，失效后重新抓一次） |

## 配置

- 视频号：`.env` 填写 `SPH_COOKIE`（浏览器登录 https://yuanbao.tencent.com/ 后从请求头复制完整 cookie）。
- 会员视频/更高清晰度：把 Netscape 格式 Cookie 导出为 `data/download/cookies/<platform>.txt`（如 `bilibili.txt`），存在时自动优先使用。
