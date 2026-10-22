# 独立 AI Agent

本模块通过 LLM Tool Calling 自主调用项目现有 MCP，不依赖 Codex。原有 MCP 服务和调用方式继续使用。业务数据仍经 MCP 读写现有 D1；本地 SQLite 只保存 LangGraph 检查点、工具回执和暂停请求。

## 安装与配置

在项目根目录执行（Python 3.10 及以上）：

```powershell
python -m pip install -e ".[agent]"
```

默认复用 `.env` 中现有的百炼配置，包括 `DASHSCOPE_API_KEY`、`DASHSCOPE_BASE_URL`、`DASHSCOPE_MODEL` 和业务线密钥选择规则。模型必须支持 OpenAI 兼容的 `tools` 和 `tool_calls`。

只配置了业务线密钥时，还需设置 `DASHSCOPE_BUSINESS_LINE=finance` 或 `DASHSCOPE_BUSINESS_LINE=language_learning`，选择项目对应的密钥。LLM 所用密钥与本次连接哪些 MCP 服务分别配置。

也可以在 `.env` 或环境变量单独配置以下三个参数：

```dotenv
AGENT_API_KEY=你的密钥
AGENT_BASE_URL=https://你的模型服务/v1
AGENT_MODEL=支持工具调用的模型名称
```

工具继续读取项目现有的 D1、素材、发布账号等配置。不要将密钥放入任务描述。检查点包含任务、工具参数及结果，应保护 `data/agent` 目录。

## 运行

```powershell
$env:DASHSCOPE_BUSINESS_LINE = "finance"
python -m agent run finance-check-001 "读取财经生产配置，查询稿件余量并汇总" --servers finance
python -m agent status finance-check-001
python -m agent resume finance-check-001
```

`--servers` 可选 `finance language_learning anime publishing`，只连接任务需要的服务。工具名称、参数结构与描述从 MCP 动态发现。模型先通过 `agent_load_tools` 按需加载参数定义和对应业务说明，避免每轮发送全部工具；加载状态随检查点保存。`agent_request_input` 用于询问日期等缺失信息。

执行控制参数：`--max-steps 60`（新任务的 LLM 决策与工具执行累计次数）、`--max-attempts 3`（建立连接失败、429、服务端错误或只读工具的最大尝试次数）、`--tool-timeout 180`、`--llm-timeout 180`、`--run-timeout 1800`（每次图执行的时间预算，不含 MCP 连接与发现，单位秒）。MCP 初始化和发现使用 `--llm-timeout` 作为请求超时。次数上限跨恢复累计，耗尽后任务结束。超时或进程中断后，可恢复相同任务；已完成的任务不能重用 ID。

## 暂停与人工审批

```powershell
python -m agent pause finance-check-001
python -m agent resume finance-check-001 --response '{}'
```

暂停请求在当前操作结束后的图节点边界生效，不会强行终止当前工具调用。独立部署的远程工作流继续运行；原有 stdio MCP 的本地线程任务仍受 MCP 子进程生命周期约束，退出或进程崩溃可能中断这些后台任务，恢复后应先查询任务文件与实际产物，再决定是否重新启动，不能把图检查点视作媒体计算进程的检查点。

当前工具审批关闭，采集、生产、写库及发布按用户任务直接执行，不需要再次回复同意。统一扩展入口为 `agent/approval_policy.py`：以后可在 `APPROVAL_REQUIRED_TOOLS` 添加工具名，或在 `requires_approval` 增加参数规则。只读分类仍用于重试和回执去重。

缺少日期等业务信息仍通过聊天询问。操作结果不确定时，Agent 使用查询工具核对回执；不能确认时报告状态，不重复执行，也不要求人工授权重试。

图流程为控制边界 → LLM 决策 → 逐项参数校验及策略入口 → 工具执行 → 控制边界。采用 LangGraph `AsyncSqliteSaver`、同步持久化模式与 `interrupt/Command`。相同数据库和任务 ID 可以在重启后继续；同一任务由文件锁禁止并行运行。

工具完成后先保存调用回执，再推进图状态。只读查询按调用 ID 缓存，允许多次轮询；有副作用的工具按工具名与规范化参数去重，避免模型换用调用 ID 重复执行。后台任务返回的 `task_path` 会随工具结果持久化。

外部 API 与本地检查点无法组成事务，因此不承诺跨系统严格一次执行。若副作用执行中超时、报错或崩溃，回执保持不确定状态；恢复后交回 Agent 查询业务记录，不直接重复执行。

操作结果不确定时先查询业务回执，不自动重复副作用。只读请求有限重试后将错误交回 LLM；LLM 请求仅对连接建立失败、429 和服务端错误有限重试；读取超时、流中断、输出截断及已返回工具参数的流不自动重发。副作用不会自动重试。审批拒绝和工具结果都进入会话，供模型调整下一步。

## Docker

在现有镜像中启用可选依赖，不改变原镜像默认行为：

```powershell
docker build --build-arg INSTALL_AGENT=true -t media-factory-agent .
docker run --rm --env-file .env -v "${PWD}/data:/app/data" -v "${PWD}/cache:/app/cache" media-factory-agent python -m agent run check-001 "查询财经稿件余量" --servers finance
```

后续状态、审批和恢复使用同样的镜像及目录挂载。媒体文件路径必须在容器内有效，生产和发布仍需部署相应系统依赖及凭据。当前实现面向单机任务，不提供聊天客户端、RAG 或分布式调度。

实现依据：[LangGraph 持久化](https://docs.langchain.com/oss/python/langgraph/persistence)与[人工中断](https://docs.langchain.com/oss/python/langgraph/interrupts)。

## Token 消耗控制

启动结果含 `poll_tool` 和 `task_path` 时由程序直接进入轮询，不额外请求模型决定是否查询。后台每 15 秒检查一次，等待窗口内不调用模型；完成与失败回执保留。旧待审上下文仅在收到同一 `context_path` 的新版状态后省略原文；完整历史继续保存在检查点和追踪中。

每轮执行的 `--max-llm-tokens` 默认 100000，累计主 Agent 模型接口实际返回的输入和输出 Token，达到阈值后停止后续模型请求并保留检查点。这是后续请求的停止阈值，单次响应可能越过阈值，不是严格计费上限。供应商未返回用量时保持未知，不能据此保证费用；重新恢复开始新的执行预算。

故障检索默认使用本地检索词覆盖度重排，不额外请求主模型；设置 `AGENT_RERANK_MODEL` 后才启用生成式模型重排。Embedding 仍使用配置的接口，相同执行内的重复故障检索复用缓存。JSON 格式错误和模型额度错误不请求外部诊断。评估命令仍会调用实际诊断模型，需单独计算消耗。
