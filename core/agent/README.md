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
python -m core.agent run finance-check-001 "读取财经生产配置，查询稿件余量并汇总" --servers finance
python -m core.agent status finance-check-001
python -m core.agent resume finance-check-001
```

`--servers` 可选 `finance language_learning anime publishing`，只连接任务需要的服务。服务说明在初始化时注入系统提示词，工具名称、参数结构与描述从 MCP 动态发现。`agent_request_input` 是唯一的 Agent 自有工具，用于询问日期等缺失信息。

执行控制参数：`--max-steps 60`（新任务的 LLM 决策与工具执行累计次数）、`--max-attempts 3`（单次 LLM 请求或只读工具的最大尝试次数）、`--tool-timeout 180`、`--llm-timeout 180`、`--run-timeout 1800`（每次图执行的时间预算，不含 MCP 连接与发现，单位秒）。MCP 初始化和发现使用 `--llm-timeout` 作为请求超时。次数上限跨恢复累计，耗尽后任务结束。超时或进程中断后，可恢复相同任务；已完成的任务不能重用 ID。

## 暂停与人工审批

```powershell
python -m core.agent pause finance-check-001
python -m core.agent resume finance-check-001 --response '{}'
```

暂停请求在当前操作结束后的图节点边界生效，不会强行终止当前工具调用。独立部署的远程工作流继续运行；原有 stdio MCP 的本地线程任务仍受 MCP 子进程生命周期约束，退出或进程崩溃可能中断这些后台任务，恢复后应先查询任务文件与实际产物，再决定是否重新启动，不能把图检查点视作媒体计算进程的检查点。

所有未列入代码中只读目录的 MCP 工具均需逐项审批，包括发布视频、GitHub 发布调度、写库及生产启动。中断信息包含完整工具名、参数和调用 ID。审批只针对该次参数，不接受模型代替人工批准。

```powershell
python -m core.agent resume finance-check-001 --response '{"approved":true}'
python -m core.agent resume finance-check-001 --response '{"approved":false}'
```

模型询问缺失信息时，使用 JSON 字符串或对象回答，例如 `--response '"2026-10-21"'`。PowerShell 旧版可能需要按终端规则转义 JSON 双引号。

## 恢复与副作用

图流程为控制边界 → LLM 决策 → 逐项参数校验及审批 → 工具执行 → 控制边界。采用 LangGraph `AsyncSqliteSaver`、同步持久化模式与 `interrupt/Command`。相同数据库和任务 ID 可以在重启后继续；同一任务由文件锁禁止并行运行。

工具完成后先保存调用回执，再推进图状态。只读查询按调用 ID 缓存，允许多次轮询；有副作用的工具按工具名与规范化参数去重，避免模型换用调用 ID 重复执行。后台任务返回的 `task_path` 会随工具结果持久化。

外部 API 与本地检查点无法组成事务，因此不承诺跨系统严格一次执行。若副作用执行中超时、报错或崩溃，回执保持不确定状态，恢复时必须人工核对业务记录：

```powershell
python -m core.agent resume finance-check-001 --response '{"result":{"task_path":"已核对的实际任务路径"}}'
```

只有确认原操作未执行，才使用 `--response '{"retry":true}'` 明确授权重试。只读请求有限重试后将错误交回 LLM；LLM 请求仅对网络错误、429 和服务端错误有限重试。副作用不会自动重试。审批拒绝和工具结果都进入会话，供模型调整下一步。

## Docker

在现有镜像中启用可选依赖，不改变原镜像默认行为：

```powershell
docker build --build-arg INSTALL_AGENT=true -t media-factory-agent .
docker run --rm --env-file .env -v "${PWD}/data:/app/data" -v "${PWD}/cache:/app/cache" media-factory-agent python -m core.agent run check-001 "查询财经稿件余量" --servers finance
```

后续状态、审批和恢复使用同样的镜像及目录挂载。媒体文件路径必须在容器内有效，生产和发布仍需部署相应系统依赖及凭据。当前实现面向单机任务，不提供聊天客户端、RAG 或分布式调度。

实现依据：[LangGraph 持久化](https://docs.langchain.com/oss/python/langgraph/persistence)与[人工中断](https://docs.langchain.com/oss/python/langgraph/interrupts)。
