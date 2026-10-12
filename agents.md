## 语言要求
1. 所有注释、Markdown 和项目提示词必须使用中文。

## 构建要求
1. 只使用 Docker 构建，不得使用本机的 `npm`、Vite 或 Python 重新构建。
2. 兼容旧数据、备份旧数据时需要和用户确认是否需要备份

## Git 提交规范
1. 提交信息必须以变更类型前缀开头，格式为 `<类型>: <中文说明>`。
2. 新增功能使用 `add:`，修复问题使用 `fix:`，仅修改文档使用 `docs:`，代码重构使用 `refactor:`，构建或维护类改动使用 `chore:`。
3. 新增完整功能时应该提交到github。

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