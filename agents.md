## 语言要求
1. 所有注释、Markdown 和项目提示词必须使用中文。
2. 目录、文件、函数等命名必须语义完整，需要参考其他文件命名。

## 构建要求
1. 只使用 Docker 构建，不得使用本机的 `npm`、Vite 或 Python 重新构建。
2. 兼容旧数据、备份旧数据时需要和用户确认是否需要备份

## Cloudflare Worker
1. 修改 `ops/cloudflare/d1-data-api` 的源码、迁移或 `wrangler.jsonc` 后，必须在同一轮重新部署，不能只提交代码。
2. 在该目录执行 `npx wrangler deploy`。新增迁移时，先执行 `npx wrangler d1 migrations apply media-factory --remote`，再部署。
3. 部署成功并确认版本号后，本次修改才算完成。

## Git 提交规范
1. 提交信息必须以变更类型前缀开头，格式为 `<类型>: <中文说明>`。
2. 新增功能使用 `add:`，修复问题使用 `fix:`，仅修改文档使用 `docs:`，代码重构使用 `refactor:`，构建或维护类改动使用 `chore:`。
3. 新增完整功能时应该提交到github中main分支。

## 测试要求
1. 不允许增加任何单元测试。
2. 禁止无明确收益的大规模测试扩写

## mcp
1. 参考结构
mcp_server/
├─ server.py或__main__.py  # MCP 注册和启动
├─ tools/                  # Tool 接口
├─ resources/              # Resource 接口
├─ prompts/                # Prompt 定义
├─ workflows/              # 多步骤业务编排
├─ services/               # 业务服务
├─ schemas/                # 输入输出模型
├─ errors/                 # 统一错误
├─ config/                 # 配置
└─ infrastructure/         # 数据库、存储、外部 API

2. 参考结构仅供参考，不需要的部分不要强行添加