# Media Factory Windows 绿色版

## 运行与持久化

完整交付目录包含 `MediaFactory.exe`、Electron 资源、内嵌 Python、原版 Open WebUI、项目源码和 FFmpeg。无需安装 Python、Node.js 或 Docker，不创建服务，不修改系统环境变量，不需要管理员权限。不要只复制 EXE，必须保留同目录资源。

双击 `MediaFactory.exe` 会先显示启动提示，随后打开原版 Open WebUI。项目内启动自动读取现有 `.env`，不弹配置窗口；模型列表显示实际使用的 `deepseek-v4-pro`，同一个 Agent 自主调用财经、语言学习、动漫及发布工具即可。关闭主聊天窗口会退出客户端并回收它启动的服务、MCP、浏览器发布进程和 FFmpeg；不会终止其他软件启动的 Python 进程。

默认数据目录为 `%APPDATA%\MediaFactory`，与程序目录分离。可通过启动进程的 `MEDIA_FACTORY_HOME` 指定另一个可写目录。升级时替换程序目录，保留数据目录。

数据目录内容：

- `config.env`：模型及业务凭据，只保存在本机，不回显配置值。
- `agent.sqlite`：Agent 检查点、调用回执、脱敏 Trace、诊断知识与评估。
- `open-webui`：原版聊天界面的数据库及上传文件。
- `workspace/data`、`workspace/cache`：现有业务模块使用的数据、后台任务文件及成片。
- `logs`：入盘前脱敏的本地服务日志。
- `browser`：桌面窗口的浏览器配置。

已有业务数据和账号凭据需要按原项目路径迁入 `workspace/data`，或者配置项目现有的远端 D1、R2 和账号路由。不会自动复制开发机 `.env`、Cookie、OAuth Token、生产数据库或历史视频到成品。

从当前项目启动时自动复用现有配置，首次复制到用户数据目录，之后保留本地配置。以下仅供迁移到未配置的新电脑时参考，不是日常操作步骤：

```dotenv
DASHSCOPE_BUSINESS_LINE=finance
DASHSCOPE_API_KEY_FINANCE=你的密钥
# 也可改为独立 Agent 模型配置，以下三个必须一起设置。
# AGENT_API_KEY=你的密钥
# AGENT_BASE_URL=https://你的模型服务/v1
# AGENT_MODEL=支持工具调用的模型
AGENT_EMBEDDING_MODEL=text-embedding-v3
```

故障知识需要 Embedding 接口，默认复用百炼密钥和兼容接口；其他模型服务可配置 `AGENT_EMBEDDING_API_KEY`、`AGENT_EMBEDDING_BASE_URL` 和 `AGENT_EMBEDDING_MODEL`。重排默认使用现有文本模型，可用 `AGENT_RERANK_MODEL` 指定更便宜的兼容模型。首次导入知识和正常模型请求需要联网，不会自动下载本地大模型。

视频生产、云端工作流和平台发布仍需要原业务凭据及授权。浏览器发布适配器沿用项目已有 media-publisher 源码与运行资源，构建机会一并复制；OAuth、扫码登录和平台账号授权不会预置。实际发布继续逐次人工审批。

## 聊天、审批和恢复

Open WebUI 将聊天 ID 转发到本地 OpenAI 兼容网关。每个聊天与实际模型映射到固定 LangGraph 任务；普通后续消息延续原有历史。流式回复包含真实文本增量和工具执行状态。

敏感工具执行前在当前聊天展示操作参数。直接回复“同意”或“取消”即可，仅作用于当前聊天正在等待的这一步操作，不需要填写任务 ID 或打开其他窗口。

`/恢复` 从最近检查点继续；暂停时直接回复“继续”。结果不确定的操作停止自动重试，避免重复发布，需要先核对实际业务结果。

等待审批时本地 MCP 会话保持长驻。关闭整个客户端或进程崩溃仍可能中断原业务的本地后台线程，重启后先检查实际产物和远端状态。图检查点不等于媒体计算进程快照。

工具返回本地视频后，聊天提供签名预览链接。仅允许预览本工作区 `cache` 内的视频文件，支持 HTTP Range，不暴露任意本地文件。

## 故障诊断、记忆和评估

管理窗口可导入项目文档、录入脱敏历史错误、执行混合检索，并在实际验证后保存长期解决方案。检索采用分块、远端 Embedding、SQLite FTS5、RRF 融合和模型候选重排。Agent 工具报错会自主检索相关故障经验，将来源和诊断上下文交回模型。该知识库不承担选题去重或历史文案管理。

模型或 Embedding 接口不可用时，已有索引保留可用的 FTS 或混合检索结果，并明确标注降级原因；不会将降级结果记作模型重排成功。首次建立向量索引仍需要有效的 Embedding 配置。

Trace 可查看 LLM 输入输出、工具参数与结果、节点路径、耗时、错误和模型返回的 Token 用量。没有返回 Token 数据时显示缺失，不能推算为零。人工审批和回执复用也会记录。

Agent Evals 区分任务完成率和有证据的验收成功率；没有验收标签时成功率为 `null`。RAG Evals 使用有来源的真实历史错误集，计算按文档来源的 Recall@K、相关性和诊断标签命中率。关键词命中与诊断准确率分别统计：诊断准确率必须对本次实际生成的答案人工复核后计算，尚未复核时为 `null`。测试查询不得导入同一评估索引。

源码运行示例：

```powershell
python ops/desktop/diagnostics_cli.py index --database cache/rag-eval.sqlite
python ops/desktop/diagnostics_cli.py rag-eval --database cache/rag-eval.sqlite --output cache/rag-evaluation.json
python ops/desktop/verify_integration.py
```

## 从源码构建

构建机需要 Windows x64、Python 3.12，以及可访问官方 Python、Electron 和 PyPI 下载服务的网络。先在 `integrations/media-publisher` 准备 `npm ci` 和 `npm run build:dir`，并准备 PATH 中的 `ffmpeg.exe` 与同目录 `ffprobe.exe`。这些要求只适用于构建机。

```powershell
powershell -ExecutionPolicy Bypass -File ops/desktop/build_portable.ps1
```

输出目录为 `dist/MediaFactory`，不生成 Setup 安装包。构建脚本会校验 Electron SHA256、打包内嵌 Python、安装实际依赖并验证 Open WebUI 和网关导入。`--prepare-only` 仅准备资源，不是完整构建，也不能视为可用交付。

原版 Open WebUI 使用其发行包自带前端，未修改核心 UI；保留原品牌与许可证。Electron、Open WebUI、FFmpeg、Python 和 media-publisher 的许可证随各自资源保留，分发时需遵守其许可要求。

实现依据：[Open WebUI 配置](https://docs.openwebui.com/reference/env-configuration/)、[Electron 手动分发](https://github.com/electron/electron/blob/main/docs/tutorial/application-distribution.md)、[Python 内嵌发行版](https://www.python.org/downloads/release/python-31210/)。

桌面 Agent 默认复用项目已有百炼密钥，使用 `deepseek-v4-pro`，通过独立 `AGENT_*` 配置绑定真实模型，不改变各业务工具的生产模型配置。业务 MCP 不作为模型显示；Agent 可调用全部现有 MCP 工具，敏感操作仍在当前聊天确认。
