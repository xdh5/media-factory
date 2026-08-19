## 语言要求
1. 所有注释、Markdown 和项目提示词必须使用中文。

## 构建要求
<!-- 1. 只使用 Docker 构建，不得使用本机的 `npm`、Vite 或 Python 重新构建。 -->
2. 未经用户允许禁止擅自推送到github
3. 兼容旧数据、备份旧数据时需要和用户确认是否需要备份

## 测试要求
1. 不得自行编写测试用例。
2. 不得运行耗费token且用时超过3分钟的额外测试。

## MCP
1. 所有 MCP 入口放在 `mcp_servers/`（不能叫 `mcp/`，会挡住官方 `mcp` SDK），与 `core/tools`、`workflows` 分开；禁止在 tools 或工作流包内再写 FastMCP。语言学习、剪辑转文字、文生图管线都是 MCP，不是 `workflows/` 业务线。
2. 已经提供 MCP 的能力只能通过对应 MCP Tool 调用，禁止创建或运行临时 Python、PowerShell、批处理或其他脚本直接导入 MCP 或工作流内部函数。
3. MCP 未连接、进程退出或调用超时时，必须停止当前工作流向用户报告具体错误；禁止绕过 MCP 直接读写数据库、缓存、任务文件或调用内部实现来继续执行。
4. 调试 MCP 只允许检查配置、启动状态和服务日志，不得用本地脚本代替 MCP 完成业务步骤。

## core
1. `tools/` 和 `capabilities` 下每个工具模块统一使用 `_constants.py`、`_errors.py`、`_schema.py` + 功能文件的结构。
2. 新增或修改功能时，必须同步检查 `_schema.py`、`_errors.py`、`_constants.py` 是否需要更新。
3. Schema 要与真实输入输出保持一致，错误信息必须具体、可理解，并尽量告诉 Agent 应该如何修正。
4. 遇到需求优先看能不能 `tools/` 和 `capabilities` ，修改 `tools/` 和 `capabilities`，或者新增`tools/` 和 `capabilities` 需要和用户汇报后再修改。
5. 写propmt的时候需要把公用propmt拼接业务私有propmt，不得公用propmt已经写了的部分私有propmt还反复写。
6. 工作流与 Agent 只能调用 `tools/`、`capabilities/` 各包 `__init__.py` 公开的方法与异常；禁止 import 或调用 `_` 开头的模块、文件、函数。下划线仅供该包内部使用。

## 工作流
1. 工作流只提供文生图业务线配置与私有 Prompt/资源（如 `finance`、`life_copy`）；对外入口是文生图 MCP。耗时步骤必须走共用后台任务 `enqueue_job`（MCP 立即返回 `job_id`），禁止在提交工具里同步卡住配音、生图提交、视频合成等长步骤。宿主拿到 `job_id` 后调用 `wait_task`（MCP 封装为 `*_wait_task`）阻塞等到终态；`*_get_job` 只做瞬时快照。状态以 SQLite 为准，完成通知走 Redis Stream。
2. 每个工作流必须使用共用话题历史 `get_topic` / `update` 做去重与占坑，禁止另起一套主题库。
3. 发布与清缓存分开：发布成功后必须再向用户确认是否删除本次生产文件，确认后调用共用 `clear_run`（MCP 封装为 `*_clear_run`）；不得把清缓存写进发布工具的返回或自动删除。
