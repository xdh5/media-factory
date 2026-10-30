# Media Factory Windows 绿色版

## 运行与持久化

完整交付目录包含 `MediaFactory.exe`、Electron 资源、内嵌 Python、原版 Open WebUI、项目源码和 FFmpeg。无需安装 Python、Node.js 或 Docker，不创建服务，不修改系统环境变量，不需要管理员权限。不要只复制 EXE，必须保留同目录资源。

双击 `MediaFactory.exe` 会先显示启动提示，随后打开原版 Open WebUI。项目内启动自动读取现有 `.env`，不弹配置窗口；模型列表显示实际使用的 `qwen3.7-plus`，同一个 Agent 自主调用财经、语言学习、动漫及发布工具即可。关闭主聊天窗口会退出客户端并回收它启动的服务、MCP、浏览器发布进程和 FFmpeg；不会终止其他软件启动的 Python 进程。

默认数据目录为 `%APPDATA%\MediaFactory`，与程序目录分离。可通过启动进程的 `MEDIA_FACTORY_HOME` 指定另一个可写目录。升级时替换程序目录，保留数据目录。

数据目录内容：

- `config.env`：模型及业务凭据，只保存在本机，不回显配置值。
- `agent.sqlite`：Agent 检查点、调用回执、暂停请求和故障知识。
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
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=你的LangSmith密钥
LANGSMITH_PROJECT=media-factory
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
```

故障知识需要 Embedding 接口，默认复用百炼密钥和兼容接口；其他模型服务可配置 `AGENT_EMBEDDING_API_KEY`、`AGENT_EMBEDDING_BASE_URL` 和 `AGENT_EMBEDDING_MODEL`。重排默认使用本地检索词覆盖度，设置 `AGENT_RERANK_MODEL` 后才调用指定兼容模型。首次导入知识和正常模型请求需要联网，不会自动下载本地大模型。

视频生产、云端工作流和平台发布仍需要原业务凭据及授权。浏览器发布适配器沿用项目已有 media-publisher 源码与运行资源，构建机会一并复制；OAuth、扫码登录和平台账号授权不会预置。工具审批当前关闭，发布按用户任务执行。

## 聊天、审批和恢复

Open WebUI 将聊天 ID 转发到本地 OpenAI 兼容网关。每个聊天与实际模型映射到固定 LangGraph 任务；普通后续消息延续原有历史。流式回复包含真实文本增量和工具执行状态。

当前不启用工具审批，采集、生产和发布不再要求逐步确认。以后可在 `agent/approval_policy.py` 配置工具名单，通过 Deep Agents 的 `interrupt_on` 原生审批。缺少业务信息时仍在当前聊天询问。

`/恢复` 从最近检查点继续；暂停时直接回复“继续”。结果不确定的操作停止自动重试，避免重复发布，需要先核对实际业务结果。

等待审批时本地 MCP 会话保持长驻。关闭整个客户端或进程崩溃仍可能中断原业务的本地后台线程，重启后先检查实际产物和远端状态。图检查点不等于媒体计算进程快照。

工具返回本地视频后，聊天提供签名预览链接。仅允许预览本工作区 `cache` 内的视频文件，支持 HTTP Range，不暴露任意本地文件。

## 故障诊断、记忆和评估

管理窗口可导入项目文档、录入脱敏历史错误、执行混合检索，并在实际验证后保存长期解决方案。检索采用分块、远端 Embedding、SQLite FTS5、RRF 融合和本地检索词覆盖度重排（仅显式配置 `AGENT_RERANK_MODEL` 时调用模型重排）。Agent 工具报错会自主检索相关故障经验，将来源和诊断上下文交回模型。该知识库不承担选题去重或历史文案管理。

模型或 Embedding 接口不可用时，已有索引保留可用的 FTS 或混合检索结果，并明确标注降级原因；不会将降级结果记作模型重排成功。首次建立向量索引仍需要有效的 Embedding 配置。

执行链路、模型用量、耗时、异常、人工反馈、数据集与实验由 LangSmith 管理。管理页提供启用状态和入口；同一聊天按 `thread_id` 关联。输入输出上传前脱敏。未启用时不写本地 Trace；旧本地执行记录保留，未自动上传。模型费用依赖 LangSmith 对应模型价格配置。

人工验收和诊断正确性在 LangSmith 标注。RAG 实验通过原生 `Client.aevaluate` 执行，项目提供来源召回率、来源相关性和关键词命中的领域评分；关键词命中不等同于答案正确，不自动转换为验收标签。

源码运行示例：

```powershell
python ops/desktop/diagnostics_cli.py index --database cache/rag-eval.sqlite --documents cache/diagnostics/documents
python ops/desktop/diagnostics_cli.py upload-cases --dataset media-factory-diagnostics --cases cache/diagnostics/cases.json
python ops/desktop/diagnostics_cli.py rag-eval --database cache/rag-eval.sqlite --dataset media-factory-diagnostics
```

首次上传使用新的数据集名称，后续通过 LangSmith 管理样本和版本。评估使用独立文档索引，不混入待评估错误查询；命令返回原生实验链接。桌面管理页也可上传样本并启动实验。项目不携带历史知识、运行日志或验收标签。

## 从源码构建

构建机需要 Windows x64、Python 3.12，以及可访问官方 Python、Electron 和 PyPI 下载服务的网络。先在 `integrations/media-publisher` 准备 `npm ci` 和 `npm run build:dir`，并准备 PATH 中的 `ffmpeg.exe` 与同目录 `ffprobe.exe`。这些要求只适用于构建机。

```powershell
powershell -ExecutionPolicy Bypass -File ops/desktop/build_portable.ps1
```

输出目录为 `dist/MediaFactory`，不生成 Setup 安装包。构建脚本会校验 Electron SHA256、打包内嵌 Python、安装实际依赖并验证 Open WebUI 和网关导入。`--prepare-only` 仅准备资源，不是完整构建，也不能视为可用交付。

原版 Open WebUI 使用其发行包自带前端，未修改核心 UI；保留原品牌与许可证。Electron、Open WebUI、FFmpeg、Python 和 media-publisher 的许可证随各自资源保留，分发时需遵守其许可要求。

实现依据：[Open WebUI 配置](https://docs.openwebui.com/reference/env-configuration/)、[Electron 手动分发](https://github.com/electron/electron/blob/main/docs/tutorial/application-distribution.md)、[Python 内嵌发行版](https://www.python.org/downloads/release/python-31210/)。

桌面 Agent 默认复用项目已有百炼密钥，使用 `qwen3.7-plus`，通过独立 `AGENT_*` 配置绑定真实模型，不改变各业务工具的生产模型配置。业务 MCP 不作为模型显示；Agent 可调用全部现有 MCP 工具，工具审批当前关闭。

新聊天首页的大标题显示“Media Factory”；模型选择器保留真实模型名，例如 `qwen3.7-plus`。该显示由桌面容器的 `branding.js` 定制，不修改原版 Open WebUI 的核心前端文件或模型标识。

Agent 使用 Deep Agents 原生模型与工具循环，MCP 工具直接注册到 `tools`；查询工具内部每 15 秒检查进度，等待期间不调用模型。消息和工具进度使用框架原生 `astream`，只读重试使用 `ToolRetryMiddleware`。每轮已记录用量达到 100000 Token 时停止后续模型请求并保存检查点；单次响应可能越过阈值。标题、标签、推荐追问、自动补全及查询改写的自动模型请求均关闭。
