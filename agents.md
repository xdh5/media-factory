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
3. 调试产物和一次性兼容方案用过了必须删掉

## MCP
1. 所有 MCP 入口放在 `core/mcp/`（包名为 `core.mcp`，不挡住官方 `mcp` SDK），与 `core/tools` 分开；禁止在 tools 包内再写 FastMCP。文生图、语言学习都是独立 MCP。视频下载在 `core/tools/download`，语音转文字在 `core/tools/transcribe`，直接调用公开方法，不要做成 MCP。

## core
1. `tools/` 下每个工具模块统一使用 `_constants.py`、`_errors.py`、`_schema.py` + 功能文件的结构。
2. 新增或修改功能时，必须同步检查 `_schema.py`、`_errors.py`、`_constants.py` 是否需要更新。
3. Schema 要与真实输入输出保持一致，错误信息必须具体、可理解，并尽量告诉 Agent 应该如何修正。
4. 遇到需求优先看能不能复用或修改 `tools/`；新增 `tools/` 需要和用户汇报后再改。
5. MCP 与 Agent 只能调用 `tools/` 各包 `__init__.py` 公开的方法与异常；禁止 import 或调用 `_` 开头的模块、文件、函数。下划线仅供该包内部使用。

## 制作管线
1. 本地 MCP 成片统一保存在 `output/{业务线}/run-YYYYMMDD/`，其中 `YYYYMMDD` 是北京时间计划发布日期，只表示日期、不包含具体发布时间；精确发布时间继续使用带时区的 `publish_at`。本地制作产物默认只保存在本机，GitHub Workflow 产物才自动交付 R2。
2. 每个实际成片成功后必须幂等写入 D1 `production_outputs`：本地来源使用 `source=local_mcp` 并保存 `local_path`，GitHub 来源使用 `source=github_workflow` 且仅在 R2 交付成功后保存 `r2_url`；禁止把 GitHub Runner 临时路径当作本地产物。本地产物按需上传 R2 时只补充原记录的 `r2_url`，不得改变来源。
3. 语言学习 Prompt 放在 `core/mcp/language_learning/prompts/`；财经 MCP 的标题标签与分镜 Prompt 放在 `core/mcp/finance/prompts/`；财经正文范文与业务参数放在 `.agents/skills/finance`，TTS 与发布参数放在 `.agents/skills/learn_Chinese_and_Korean`，对应 MCP 只负责编排。耗时步骤必须通过 MCP 的 `*_start_*` + `*_poll_task` 后台任务轮询（实现见 `core/mcp/_task_runner.py`），禁止同步调用以免 Cursor MCP 客户端超时。
4. 每个 MCP 必须使用共用话题去重 `get_topic` / `update` 做去重与占坑，禁止另起一套主题库。
5. 发布与清缓存分开：发布成功后必须再向用户确认是否删除本次生产文件，确认后调用共用 `clear_run`（`core.tools.clear_cache`，MCP 封装为 `*_clear_run`）；不得把清缓存写进发布工具的返回或自动删除。
6. 财经与语言学习合并为每周生产 Workflow：每周六北京时间 12:00 串行生产下周周一至周日的财经与语言内容；单日或单个产品失败不得阻断后续日期。每轮生产结束 3 分钟后按 D1 的 `production_outputs` 与 `publication_records` 健康检查，仅重新生成缺失产品或补发缺失平台，最多重试 3 次。财经只生产并交付 R2；语言生产完成后自动在 YouTube、TikTok、Facebook、Instagram 预约发布。周六计划执行后手动触发且未指定目标周时，检查下周七天并只补齐数据库缺口。原每日生产命令保留但不再配置定时调度；发布 Workflow 仅允许手动触发，用于指定日期补发或重试。
7. 语言学习手动发布 Workflow 只复用 `source=github_workflow` 的 R2 成片，统一预约到计划发布日期北京时间 16:00；发布前按平台查询同日发布记录，只补发尚未记录的 YouTube、TikTok、Facebook、Instagram，失败时重试最多 3 次。禁止在 Workflow 中复制或绕过对应工具实现。视频业务编排必须通过对应 MCP Tool，跨 Job 的 R2 成片交付可调用 `core.tools.r2_storage` 公开方法；禁止直接导入 MCP 内部实现。
8. 交互式生产的文本生成、词表生成、分镜生成与图片视觉验收由宿主 Agent 完成；GitHub Action 没有宿主 Agent 时，允许生产 Runner 调用千问文本、千问视觉和千问兜底生图完成同等步骤，MCP 本身仍禁止直接调用千问文本或千问视觉模型。
9. 交互式生产财经或语言学习视频前，用户必须明确北京时间计划发布日期；未说明日期时 Agent 必须先询问，禁止默认当天、创建 run、开始生产或写入产物表。统一发布使用独立 `core.mcp.publishing`：必须明确业务线、产物日期、账号组、平台及立即/预约方式；发布前查 D1 去重，发布或预约成功后逐条写入 `publication_records`。
