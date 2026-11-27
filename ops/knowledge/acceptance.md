# 知识库业务验收记录

验收日期：2026-11-28（北京时间）。验收采用实际服务和隔离知识库操作，没有新增测试文件、测试依赖或测试任务。

## 部署与环境

- D1 迁移：`0043_independent_knowledge.sql`，本地与远程均执行成功。
- Worker：`media-factory-data-api`，最终部署版本 `3b2ab767-0646-49ec-b4cb-a3c61b6f9635`。
- Vectorize：`media-knowledge-v1`、`media-knowledge-v2`，均为 1024 维、cosine，首次写入前各建立六个元数据索引。
- 真实 Embedding：兼容接口调用 `@cf/baai/bge-m3`，文档与查询均确认 1024 维。显式复用本机 Wrangler OAuth 文件；凭据不入库、不提交。现有普通 Cloudflare Token 没有 AI 权限，DashScope 返回免费额度限制，因此未将其作为已通过的服务。
- 两个实际 profile 使用同一个真实模型，分别采用不同物理索引和切片参数；已验证重建、激活及回切。没有将本次验收描述为不同模型之间的效果比较。
- `uv sync --locked --no-editable --extra rag --extra mcp --extra publishing --reinstall-package media-factory` 完成；Python 语法、Ruff、JSON、Node 语法、锁文件及 Git 空白检查通过。Worker 构建与部署通过。本机 Docker daemon 不可用，本轮未完成 Docker 镜像构建。

## 实际操作结果

| 项目 | 观察结果 |
| --- | --- |
| 独立 MCP | ProjectMCP stdio 客户端发现全部 12 个工具；实际调用原文 CRUD、分页、检索、同步及状态 |
| 去重 | 同库重复新增返回既有 ID，`duplicate=true`；初始化经验再次导入同样返回既有 ID |
| 并发更新 | 文档从 revision 1 更新至 2、3；旧 expected_revision 更新返回冲突 |
| 版本回查 | 更新尚未同步时，旧向量仍存在，但旧片段检索结果为零 |
| 分类与隔离 | 同名正文分别入两个隔离库；只返回目标库。业务线、平台、阶段组合匹配；错误分类返回空结果 |
| 故障恢复 | 显式使用缺少凭据的配置，任务进入 failed；恢复真实配置并 retry_failed 后成功 submitted、ready |
| 重复同步与旧任务 | 再同步没有重复建片段；旧任务晚完成只处理旧 revision，当前 revision 仍 pending；失效租约重复提交被拒绝 |
| 重建中变更 | 目标 profile 注册后新增、更新、删除均生成两套配置任务；未完成及集合代次变化时拒绝激活 |
| 激活与回切 | 新 profile 全部当前版本 ready 后激活，实际命中 revision 3；旧 profile 尚未全部 ready 时拒绝回切，水位确认后回切成功 |
| 中文与表情 | 含多段中文、换行及表情的实际文档完成多片段写入，原文位置校验通过 |
| 已验证经验约束 | publisher-errors 缺少 evidence 的写入被拒绝；verified=false 过滤返回空结果，不放宽为已验证记录 |
| 删除 | 墓碑建立后立即检索为空；向量删除水位确认后清除原文、标题、元数据及片段 |
| 发布独立性 | 清空知识配置仍能加载发布服务，未导入知识模块；原账号预检、目标范围、去重和独立回执规则保留 |

隔离库 `rag-acceptance-20261127` 的全部 17 个任务及 `rag-isolation-20261127` 的全部 5 个任务最终均为 ready；五条临时文档全部为墓碑，正文长度为零、元数据为空。Vectorize 实际计数最终为主索引 3、次索引 0，剩余片段属于正式经验库。库及无原文的审计墓碑保留，未增加自动删除知识库的管理功能。

## 正式发布经验

正式库 `publisher-errors` 保留三条经验，索引均为 ready。通过真实 MCP 按 `finance + 平台 + 阶段` 分别检索命中：

| 经验 | 文档 ID | 本次检索分数 |
| --- | --- | --- |
| 视频号封面组件就绪与直接编辑 | `843e8a61-07d0-47d2-8f3f-a7be1026dcab` | 0.55737597 |
| 视频号 iframe 官方预约 | `3f8e600b-85bd-4e44-aa99-de1674f55943` | 0.58620614 |
| 头条文章无封面发布与回执判断 | `c241b91b-f45c-4281-a12f-7927ccbc9440` | 0.78095067 |

视频号依据独立发布记录 2385–2387 及实际 CLI 成功日志；头条依据三篇作品 ID 及实际发布接口回执。没有将头条文章官方预约或失败的修复尝试标为已验证。

本轮通过独立 stdio 客户端验收，不代表当前聊天已自动接入新的 MCP。宿主接入方式见 README。
