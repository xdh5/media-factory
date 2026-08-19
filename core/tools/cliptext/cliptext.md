# 剪辑转文字（公有工具）

实现在 `core/tools/cliptext`。MCP 入口：`python -m mcp_servers.cliptext`。从分享链接解析真实视频地址，再用 Groq Whisper 转成文字。**不做 ASR 错别字校对。** 各业务工作流可直接调用公开的 `parse_link` / `transcribe_media`。

## MCP 工具

1. `cliptext_parse_link(share_text)`：解析抖音/快手/小红书/B 站等分享口令或链接。返回 `platform`、`title`、`video_id`、`video_url`、`cover_url`。
2. `cliptext_transcribe(media_path, language="zh")`：立即返回 `job_id`。`media_path` 可以是本地文件，或上一步的 `video_url`。
3. `cliptext_wait_task(job_id)`：阻塞等到终态；`completed` 后读 `result.text`。单次最多 180 秒，仍在运行再调一次。
4. `cliptext_get_job(job_id)`：瞬时快照，不阻塞。

## 配置

`.env` 需要 `GROQ_API_KEY`。抖音解析失败时再填 `DOUYIN_COOKIE`。
