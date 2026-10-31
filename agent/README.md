# 独立 AI Agent

本模块使用 `deepagents.create_deep_agent` 管理模型决策、工具执行和后续推理，通过 `langchain_openai.ChatOpenAI` 接入模型并自主调用项目现有 MCP，不依赖 Codex。原有 MCP 服务和调用方式继续使用。业务数据仍经 MCP 读写现有 D1；本地 SQLite 保存 LangGraph 检查点、工具回执、暂停请求和故障知识；追踪、人工反馈、数据集与实验交给 LangSmith。

## 安装与配置

在项目根目录执行（Python 3.11 及以上）：

```powershell
pip install deepagents langchain-openai langsmith
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

`--servers` 可选 `finance language_learning anime publishing`，只连接任务需要的服务。工具名称、参数结构与描述从 MCP 动态发现。MCP 工具适配为可执行的 `StructuredTool` 后，直接传给 `create_deep_agent(tools=...)`；业务说明进入系统提示词。`agent_request_input` 用于询问日期等缺失信息。

执行控制参数：`--max-steps 60`（每次执行的模型调用次数上限，由框架的 `ModelCallLimitMiddleware` 管理）、`--max-attempts 3`（只读工具最大尝试次数）、`--tool-timeout 180`、`--llm-timeout 180`、`--run-timeout 1800`（每次执行的时间预算，不含 MCP 连接与发现，单位秒）。MCP 初始化和发现使用 `--llm-timeout` 作为请求超时。达到模型调用次数上限、超时或进程中断后，可恢复相同任务；恢复时开始新的执行预算。已完成的命令行任务不能重用 ID。

旧版自定义图的检查点不能在当前 Agent 中恢复，需要新建任务；原有业务产物和回执保留。

## 暂停与人工审批

```powershell
python -m agent pause finance-check-001
python -m agent resume finance-check-001 --response '{}'
```

暂停请求在当前操作结束后的图节点边界生效，不会强行终止当前工具调用。独立部署的远程工作流继续运行；原有 stdio MCP 的本地线程任务仍受 MCP 子进程生命周期约束，退出或进程崩溃可能中断这些后台任务，恢复后应先查询任务文件与实际产物，再决定是否重新启动，不能把图检查点视作媒体计算进程的检查点。

当前工具审批关闭，采集、生产、写库及发布按用户任务直接执行，不需要再次回复同意。审批策略入口为 `agent/approval_policy.py`：在 `APPROVAL_REQUIRED_TOOLS` 添加工具名即可通过 `create_deep_agent(interrupt_on=...)` 启用原生审批。只读分类仍用于重试和回执去重。

缺少日期等业务信息仍通过聊天询问。操作结果不确定时，Agent 使用查询工具核对回执；不能确认时报告状态，不重复执行，也不要求人工授权重试。

实现入口为 `agent/agent.py`，职责分工如下：

- `agent/agent.py`：组合模型、工具、系统提示词和检查点，`create_media_agent` 返回 Deep Agents 实例。
- `agent/llm.py`：创建 `ChatOpenAI`；用量统计使用官方 `UsageMetadataCallbackHandler`。
- `agent/mcp_client.py`：连接 MCP、发现工具并适配为可执行的 `StructuredTool`。
- `agent/middleware.py`：处理业务参数校验、暂停、预算和调用回执；MCP 客户端保存在 `mcp_tools`，框架保留的 `tools` 属性仅用于注册工具列表。
- `agent/streaming.py`：消费框架 `astream` 的消息、工具更新和业务进度，转换为聊天事件。
- `agent/diagnostics/tracing.py`：配置 LangSmith 客户端、追踪项目及输入输出脱敏。
- `agent/diagnostics/evaluation.py`：导入 LangSmith 数据集，用原生评估器运行诊断实验。
- `agent/__main__.py`、`desktop/runtime.py`：运行 Agent，读取结果并交给终端或聊天界面。

核心结构如下：

```python
model = create_chat_model(settings, usage)
agent = create_deep_agent(
    model=model,
    tools=[*registered_tools, agent_request_input],
    system_prompt=system_prompt,
    checkpointer=saver,
)
result = await agent.ainvoke(state, config)
```

Deep Agents 负责完整的模型与工具循环、内置规划及上下文管理。项目中间件处理业务参数校验、暂停、Token 预算和调用回执，不再自行搭建决策与执行节点。检查点使用框架支持的 `AsyncSqliteSaver`，补充业务信息通过 `interrupt/Command` 恢复。同一任务由文件锁禁止并行运行。

工具完成后先保存调用回执，再推进图状态。只读查询按调用 ID 缓存，允许多次轮询；有副作用的工具按工具名与规范化参数去重，避免模型换用调用 ID 重复执行。后台任务返回的 `task_path` 会随工具结果持久化。

外部 API 与本地检查点无法组成事务，因此不承诺跨系统严格一次执行。若副作用执行中超时、报错或崩溃，回执保持不确定状态；恢复后交回 Agent 查询业务记录，不直接重复执行。

操作结果不确定时先查询业务回执，不自动重复副作用。只读请求通过 `ToolRetryMiddleware` 有限重试后将错误交回 LLM；模型请求关闭 SDK 自动重试，失败后保留检查点，由用户恢复任务；读取超时、流中断和输出截断不自动重发。副作用不会自动重试。审批拒绝和工具结果都进入会话，供模型调整下一步。

## Docker

在现有镜像中启用可选依赖，不改变原镜像默认行为：

```powershell
docker build --build-arg INSTALL_AGENT=true -t media-factory-agent .
docker run --rm --env-file .env -v "${PWD}/data:/app/data" -v "${PWD}/cache:/app/cache" media-factory-agent python -m agent run check-001 "查询财经稿件余量" --servers finance
```

后续状态、审批和恢复使用同样的镜像及目录挂载。媒体文件路径必须在容器内有效，生产和发布仍需部署相应系统依赖及凭据。命令行和桌面端共用同一 Agent 构造入口，当前实现面向单机任务。

实现依据：[LangGraph 持久化](https://docs.langchain.com/oss/python/langgraph/persistence)与[人工中断](https://docs.langchain.com/oss/python/langgraph/interrupts)。

## Token 消耗控制

Agent 根据启动工具返回的 `poll_tool` 和 `task_path` 调用查询工具。查询工具内部每 15 秒检查一次，直到完成或失败；等待期间不额外请求模型。上下文压缩由 Deep Agents 管理。

每轮执行的 `--max-llm-tokens` 默认 100000，通过官方用量回调累计模型接口实际返回的输入和输出 Token，达到阈值后停止后续模型请求并保留检查点。这是后续请求的停止阈值，单次响应可能越过阈值，不是严格计费上限。供应商未返回用量时保持未知，不能据此保证费用；重新恢复开始新的执行预算。

故障检索默认使用本地检索词覆盖度重排，不额外请求主模型；设置 `AGENT_RERANK_MODEL` 后才启用生成式模型重排。Embedding 仍使用配置的接口，相同执行内的重复故障检索复用缓存。JSON 格式错误和模型额度错误不请求外部诊断。评估命令仍会调用实际诊断模型，需单独计算消耗。

## LangSmith

在项目 `.env` 中配置：

```dotenv
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=你的LangSmith密钥
LANGSMITH_PROJECT=media-factory
LANGSMITH_ENDPOINT=https://apac.api.smith.langchain.com
```

LangSmith API Key 与模型服务密钥独立，在 LangSmith 设置页创建。上述接口对应亚太组织，页面为 `https://apac.smith.langchain.com`；区域按组织所在的数据区选择，与使用者的物理位置无关。其他区域或企业部署使用对应 `LANGSMITH_ENDPOINT`，管理页入口随接口配置切换。未启用追踪时 Agent 可以运行；启用追踪而没有密钥时会明确报错。桌面管理页显示启用状态，并提供 LangSmith 入口。

任务、模型调用、工具调用和检索链路由 SDK 原生记录；`thread_id` 关联同一聊天，运行结果中的 `run_id` 对应本次原生执行。模型与工具耗时、Token 用量和异常在 LangSmith 查看；模型费用取决于 LangSmith 是否已配置对应模型价格。输入输出上传前脱敏。执行记录和评分不再双写本地 Trace 表；旧本地记录保留，未自动上传。

人工验收、反馈、标注队列、实验比较与指标聚合使用 LangSmith 页面。框架运行完成不能直接等同于业务验收成功；使用实际产物和业务回执进行人工评分。

## 故障诊断数据集与实验

先准备独立文档索引，再将有来源的 JSON 标注集上传为新的 LangSmith 数据集：

```powershell
python ops/desktop/diagnostics_cli.py index --database cache/rag-eval.sqlite --documents cache/diagnostics/documents
python ops/desktop/diagnostics_cli.py upload-cases --dataset media-factory-diagnostics --cases cache/diagnostics/cases.json
python ops/desktop/diagnostics_cli.py rag-eval --database cache/rag-eval.sqlite --dataset media-factory-diagnostics
```

首次上传创建新数据集；后续样本编辑和版本管理在 LangSmith 完成。样本保留 `id`、`query`、`provenance`、`relevant_sources`、`expected_term_groups`、`annotation_source`，不能把评估查询导入文档索引。

`Client.aevaluate` 负责运行样本、保存实验和关联评估反馈。项目只提供来源召回率、来源相关性和诊断关键词命中三个领域评分函数，不再自行管理评估表或汇总报告。关键词命中不代表诊断正确；实际答案的正确性在 LangSmith 进行人工标注。命令返回原生实验链接，不会自动运行生产或发布。

参考：[框架中间件](https://docs.langchain.com/oss/python/langchain/middleware/built-in)、[LangSmith SDK](https://reference.langchain.com/python/langsmith)与[原生评估](https://reference.langchain.com/python/langsmith/evaluation)。
