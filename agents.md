## 语言要求
1. 所有注释、Markdown 和项目提示词必须使用中文。

## 构建要求
<!-- 1. 只使用 Docker 构建，不得使用本机的 `npm`、Vite 或 Python 重新构建。 -->
2. 未经用户允许禁止擅自推送到github
3. 兼容旧数据、备份旧数据时需要和用户确认是否需要备份

## Git 提交规范
1. 提交信息必须以变更类型前缀开头，格式为 `<类型>: <中文说明>`。
2. 新增功能使用 `add:`，修复问题使用 `fix:`，仅修改文档使用 `docs:`，代码重构使用 `refactor:`，构建或维护类改动使用 `chore:`。
3. 一次提交包含多类改动时，以主要改动类型为准；提交说明必须准确概括实际变更。

## 测试要求
1. 不得自行编写测试用例。
2. 不得运行耗费token且用时超过3分钟的额外测试。

## MCP
1. 所有 MCP 入口放在 `core/mcp/`（包名为 `core.mcp`，不挡住官方 `mcp` SDK），与 `core/tools` 分开；禁止在 tools 包内再写 FastMCP。文生图、语言学习都是独立 MCP。视频下载在 `core/tools/download`，语音转文字在 `core/tools/transcribe`，直接调用公开方法，不要做成 MCP。

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
4. GitHub Actions 默认只创建财经和语言学习视频、构建生产镜像并上传 R2。用户明确启用的语言学习每日定时 Workflow 可以通过语言学习 MCP 调用 YouTube 官方 API及 Zernio 的 TikTok、Facebook、Instagram 发布能力，并发送 Telegram 任务通知；禁止在 Workflow 中复制或绕过对应工具实现。视频业务编排必须通过对应 MCP Tool，跨 Job 的 R2 成片交付可调用 `core.tools.r2_storage` 公开方法；禁止直接导入 MCP 内部实现。
5. 交互式生产的文本生成、词表生成、分镜生成与图片视觉验收由宿主 Agent 完成；GitHub Action 没有宿主 Agent 时，允许生产 Runner 调用千问文本、千问视觉和千问兜底生图完成同等步骤，MCP 本身仍禁止直接调用千问文本或千问视觉模型。
