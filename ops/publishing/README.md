# Publisher 账号迁移与验收

在 Factory 根目录运行 `python ops/publishing/export_publisher_accounts.py`，将 Factory 账号配置显式导出到独立 Publisher 的 `data/accounts.json`。已有目录保留时间戳备份，按账号标识合并，凭据正文不导出。Publisher 不导入此脚本、不读取 Factory 接口。

2026-11-28 已完成本机迁移：4个账号组、7条账号配置；原浏览器会话和凭据文件保留。后续账号配置通过 Publisher 的 `configure-accounts` CLI 或 `configure_accounts` MCP 维护，Factory 的业务选择和回执仍由 Factory 自己负责。

本轮验收：

- Electron 主进程及 TypeScript MCP 构建通过，Python 编译及 Ruff 的导入、未定义名称检查通过，Git 空白检查通过。
- 将 Factory 接口配置为不可连接地址，独立 stdio MCP 仍可创建、查询任意有效账号组，返回空账号列表且无官方凭据错误。
- MCP 工具目录包含账号查询、账号配置、登录、登录状态、发布与任务查询；视频字段覆盖封面、原创、分区和 YouTube 参数，文章、微头条通过独立请求 JSON 发布。
- 官方 Python CLI 的 publish 帮助入口正确解析，Electron 转发保留该子命令；官方账号从 Publisher 自有配置解析凭据引用。
- 新账号组识别成功，partition 未显式指定账号组时明确拒绝；微头条图片数组被拒绝，文章旧封面上传实现已删除。
- 发布账号解析仅检查请求涉及的官方平台，不验证无关平台。YouTube 历史去重标记继续按内容摘要识别，新标记使用 Publisher 名称。

没有新增测试文件或依赖，没有实际上传或发布新作品。发布页面和官方接口的端到端验收仍须在下次授权发布时按目标账号真实预检执行。Docker daemon 本机不可用，本轮采用本机构建。
