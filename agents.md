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
1. 所有 MCP 入口放在 `core/mcp/`（包名为 `core.mcp`，不挡住官方 `mcp` SDK），与 `core/tools` 分开；禁止在 tools 包内再写 FastMCP。文生图、语言学习都是独立 MCP。视频下载在 `core/tools/download`，语音转文字在 `core/tools/transcribe`，直接调用公开方法，不要做成 MCP。
2. 已经提供 MCP 的能力只能通过对应 MCP Tool 调用，禁止创建或运行临时 Python、PowerShell、批处理或其他脚本直接导入 MCP 内部函数。
3. MCP 未连接、进程退出或调用超时时，必须停止当前制作并向用户报告具体错误；禁止绕过 MCP 直接读写数据库、缓存、任务文件或调用内部实现来继续执行。若已用 `*_start_*` 启动后台任务，可用 `*_poll_task(task_path)` 轮询直至 `done=true`，不得因客户端超时而重复 start 同一步骤。
4. 调试 MCP 只允许检查配置、启动状态和服务日志，不得用本地脚本代替 MCP 完成业务步骤。

## core
1. `tools/` 下每个工具模块统一使用 `_constants.py`、`_errors.py`、`_schema.py` + 功能文件的结构。
2. 新增或修改功能时，必须同步检查 `_schema.py`、`_errors.py`、`_constants.py` 是否需要更新。
3. Schema 要与真实输入输出保持一致，错误信息必须具体、可理解，并尽量告诉 Agent 应该如何修正。
4. 遇到需求优先看能不能复用或修改 `tools/`；新增 `tools/` 需要和用户汇报后再改。
5. MCP 与 Agent 只能调用 `tools/` 各包 `__init__.py` 公开的方法与异常；禁止 import 或调用 `_` 开头的模块、文件、函数。下划线仅供该包内部使用。

## 制作管线
1. 语言学习 Prompt 放在 `core/mcp/language_learning/prompts/`；财经 MCP 的标题标签与分镜 Prompt 放在 `core/mcp/finance/prompts/`；财经正文范文与业务参数放在 `.agents/skills/finance`，TTS 与发布参数放在 `.agents/skills/learn_Chinese_and_Korean`，对应 MCP 只负责编排。耗时步骤必须通过 MCP 的 `*_start_*` + `*_poll_task` 后台任务轮询（实现见 `core/mcp/_task_runner.py`），禁止同步调用以免 Cursor MCP 客户端超时。
2. 每个 MCP 必须使用共用话题去重 `get_topic` / `update` 做去重与占坑，禁止另起一套主题库。
3. 发布与清缓存分开：发布成功后必须再向用户确认是否删除本次生产文件，确认后调用共用 `clear_run`（`core.tools.clear_cache`，MCP 封装为 `*_clear_run`）；不得把清缓存写进发布工具的返回或自动删除。
