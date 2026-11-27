# 独立 RAG 知识库

Python 使用 LangChain 的 `Document`、中文递归切片与 `Embeddings` 抽象，自行编排预处理、向量化、过滤检索和结果处理。D1 保存原文及元数据，Vectorize 保存向量；不使用托管 RAG，不生成回答，不依赖 Codex、LangChain Agent 或 Deep Agents 的运行时。

## 安装与启动

```powershell
uv sync --locked --no-editable --extra rag --extra mcp --extra publishing
$env:MEDIA_FACTORY_KNOWLEDGE_CONFIG="C:/项目路径/ops/knowledge/embedding-profiles.example.json"
python -m media_factory_mcp.knowledge
```

保留已有业务依赖时使用以上 extra 组合；仅安装知识服务可只加 `--extra rag`。项目使用 wheel 的包名映射，安装需 `--no-editable`。Docker 选择 `docker build --build-arg INSTALL_KNOWLEDGE=true -t media-factory-knowledge .`，运行时挂载配置及注入环境，以 `python -m media_factory_mcp.knowledge` 启动 stdio。默认镜像不安装 RAG 依赖。

配置由 `MEDIA_FACTORY_KNOWLEDGE_CONFIG` 指向 JSON。`embedding-profiles.example.json` 提供 BGE-M3 的当前/下一切片配置及 DashScope 示例，不包含密钥。端点、模型、维度、距离、切片策略、是否传递 dimensions 参数共同决定不可混用的 profile 标识。修改凭据、超时和批大小不改变标识。

凭据二选一：`api_key_env` 指定环境变量名；或 `credential_file_env` 指定保存 Wrangler OAuth TOML 文件路径的环境变量名。后者只供显式复用本机已有授权，每次向量化重新读文件，不复制凭据到 D1 或版本库。例如本机 `MEDIA_FACTORY_WRANGLER_CONFIG` 指向 Wrangler 的 `config/default.toml`；OAuth 过期需执行 `npx wrangler whoami` 刷新授权并重新调用。无人值守部署宜改用拥有 Workers AI 权限的 API Token 环境变量。普通 Cloudflare 数据管理 Token 不一定有 AI 权限。当前 DashScope 账户免费额度限制需由账户管理方处理，示例不会自动切换服务。

兼容接口直接 POST 配置中的完整 `/embeddings` 地址，不引入模型 SDK。自定义协议在 `services/embeddings.py` 注册提供者工厂，返回 LangChain `Embeddings` 实例；不得增加聊天、视觉理解或生成回退。仅文本向量化是本模块的模型调用边界。

## Cloudflare 部署

在 `ops/cloudflare/d1-data-api` 执行，使用已有 Wrangler 授权；不要让缺少权限的环境变量覆盖可用授权。

```powershell
npx wrangler vectorize create media-knowledge-v1 --dimensions=1024 --metric=cosine
npx wrangler vectorize create media-knowledge-v2 --dimensions=1024 --metric=cosine
```

两个索引均须在首次写向量前建立 `knowledge_base`、`profile_id`、`business_line`、`platform`、`stage` 五个 string 元数据索引，及 `verified` boolean 元数据索引：

```powershell
npx wrangler vectorize create-metadata-index media-knowledge-v1 --property-name=knowledge_base --type=string
```

其余字段和第二个索引按相同命令建立，`verified` 使用 `--type=boolean`。索引已存在时先用 `get`、`list-metadata-index` 核对，不重复创建。

`wrangler.jsonc` 中 `vectorize` 绑定物理索引，`KNOWLEDGE_INDEXES` 将配置里的 `index_name` 映射到绑定名、维度和距离配置。新增物理索引时两处一起配置，再部署；Worker 会核对部署登记的距离及实际索引维度；Vectorize v2 的 describe 不返回距离，部署时需用 wrangler vectorize get 核对距离登记。

```powershell
npx wrangler d1 migrations apply media-factory --local
npx wrangler deploy --dry-run
npx wrangler d1 migrations apply media-factory --remote
npx wrangler deploy
```

迁移 `0043` 只新增四张知识表、索引及文档变更触发器，不改既有业务表。写原文与创建同步任务在同一 D1 事务中完成。数据 API 沿用 `CLOUDFLARE_DATA_API_URL`、`CLOUDFLARE_DATA_API_TOKEN`；管理面 Token 不用于调用数据 API。

## 工具与数据生命周期

所有工具成功返回 `ok=true`；失败返回 `ok=false,error`，冲突保留 `DATABASE_CONFLICT` 及远程错误信息。空检索是成功的 `matches=[]`。原文/状态工具不要求配置向量化服务；注册与索引操作需要显式 profile。

| 工具 | 参数及结果 |
| --- | --- |
| `knowledge_list_bases` | 列出库类型、生效 profile、集合 generation |
| `knowledge_register_base` | `knowledge_base,profile_name,kind`；kind 为 generic 或 publisher-errors |
| `knowledge_add` | `knowledge_base,title,content,metadata`；返回文档、revision、duplicate 和同步状态 |
| `knowledge_get` | `knowledge_base,document_id`；原文及全部同步任务 |
| `knowledge_list` | `knowledge_base,cursor,limit`；limit 1–100，返回 next_cursor |
| `knowledge_update` | 文档完整字段及 `document_id,expected_revision`；版本不符返回冲突 |
| `knowledge_delete` | `knowledge_base,document_id,expected_revision`；立即墓碑屏蔽，生成删除任务 |
| `knowledge_search` | `knowledge_base,query,filters,limit,score_threshold,max_per_document` |
| `knowledge_sync` | `knowledge_base,limit,retry_failed`；limit 1–20，先刷新可见性，再处理有限任务 |
| `knowledge_index_status` | `knowledge_base,cursor,limit`；状态计数及按任务 ID 排序的游标页 |
| `knowledge_reindex` | `knowledge_base,profile_name`；注册目标配置并补齐所有文档任务 |
| `knowledge_activate_profile` | `knowledge_base,profile_name,expected_generation`；目标当前版本全部 ready 才激活 |

知识库必须显式注册；未知库不会自动建立或跨库补全。正文 1–100000 字符、标题 1–300 字符、元数据 JSON 至多 12000 字符；分类值为 1–64 位小写英文字母、数字、下划线或连字符。元数据不能覆盖系统片段标识和位置。单文档每个 profile 至多 256 片段；超过时同步明确失败，应调整切片配置或拆分原文。

同库规范化正文与元数据相同的新增返回现有文档，不重复发任务。标题变化请显式更新。更新要求 revision；删除立即从检索隐藏，所有相关索引清理完成后清除正文、标题、元数据及片段，只留无正文的墓碑和同步审计。同步失败不会丢原文。

检索 `filters` 只支持 business_line、platform、stage、verified 的等值组合。publisher-errors 强制 verified=true。query 至多 8000 字符，limit 1–20，每文档上限 1–5；最多超额召回 100 个向量，回查 D1 删除标记、文档 revision、库和 profile，剔除失效候选，按同一配置分数排序、阈值过滤和片段去重，不放宽分类。余弦和点积分数越大越相关，欧氏距离越小越相关；threshold 对应其方向，不跨模型比较分数。结果含原文位置、片段、元数据、标题、revision 和分数，来源及验证证据位于 metadata。

Worker 全部知识接口为受 Bearer 鉴权的 `POST /v1/knowledge/<操作>`，请求体为 JSON。操作对应 bases、register、add、get、list、update、delete、status、reindex、activate、claim、submit、fail、refresh、query。内部同步端点同样需要项目服务权限；没有公开向量读写入口。服务账户拥有知识库管理权限，这不是多租户用户权限系统。

## 同步与更换模型

任务状态为 pending → processing → submitted → ready；失败为 failed。processing 使用 300 秒租约和唯一 token，过期可重新领取。失败项仅在 `retry_failed=true` 时重新领取；一次调用不无限重试。发生错误先修复服务，再有限批次同步。

片段 ID 由库、文档、revision、profile、顺序确定，在向量写入前记录到 D1。上游写入按 ID 幂等；只有合法租约可提交受理状态。旧任务只清理自身及更旧版本，不能写入当前 revision 或覆盖较新任务。写入返回 mutation 标识后只是 submitted；后续 sync 依据 Vectorize 已处理 mutation 或处理时间水位刷新 ready。未确认可见时不按固定等待时间宣称成功。

重建操作注册目标 profile，并在同一事务内生成现有文档任务；重建期间新增、更新、删除会由触发器发送至所有已注册 profile。反复调用 reindex 不重复创建已有任务。继续 sync 至目标当前文档全部 ready，读取 status 的 generation，再按该值调用 activate；期间原配置仍可检索。并发变化或未完成会拒绝激活，重新查状态并同步即可。保留旧 profile 同步，支持同样条件的回切。

旧物理索引清理由运维明确执行，确认没有知识库使用后才删除 Vectorize 索引并调整绑定；不要在重建尚未可用时删除旧索引。当前工具不自动删除知识库或 profile，避免失去回切依据。切片策略调整也必须新 profile；换维度或距离需匹配的新物理索引。

## 宿主接入

标准 MCP stdio 配置示例（路径替换为当前机器绝对路径，凭据通过本机环境注入）：

```json
{
  "mcpServers": {
    "media-factory-knowledge": {
      "command": "C:/项目路径/.venv/Scripts/python.exe",
      "args": ["-m", "media_factory_mcp.knowledge"],
      "cwd": "C:/项目路径",
      "env": {"MEDIA_FACTORY_KNOWLEDGE_CONFIG": "C:/项目路径/ops/knowledge/embedding-profiles.example.json"}
    }
  }
}
```

Codex 使用其标准 MCP server 配置映射上述 command、args、env。项目本机 stdio 调用：

```python
from pathlib import Path
from media_factory_mcp.client import ProjectMCP

async with ProjectMCP("media_factory_mcp.knowledge", Path.cwd()) as client:
    result = await client.call("knowledge_search", {
        "knowledge_base": "publisher-errors", "query": "直接编辑按钮消失",
        "filters": {"business_line": "finance", "platform": "wechat_channels", "stage": "cover"}
    })
```

LangChain 和 Deep Agents 可用各自标准 MCP 客户端加载同一 stdio 工具；`langchain-mcp-adapters` 属于宿主环境，知识服务无需安装这些 Agent 依赖。例如宿主使用 `MultiServerMCPClient` 的 stdio command/args/env，`await client.get_tools()` 得到相同工具，再交给宿主 Agent。新配置或独立客户端连接成功不表示当前聊天已自动接入，需要宿主实际加载配置后检查工具目录。

发布服务不导入知识模块，没有 Embedding 配置依赖；三个发布 Skill 和发布 instructions 只引导宿主独立查询及保存，规则见 `.agents/skills/publisher-error-knowledge.md`。

## 发布经验初始化

`publisher-experiences.json` 保存三条有真实业务回执的初始化经验。执行 `python ops/knowledge/import_publisher_experiences.py`，通过标准 MCP 注册 publisher-errors、幂等新增并提交向量同步。首次导入后继续调用 sync 核对 ready；重复执行不会重复建文档。证据记录标识及脱敏日志路径，不保存 Cookie、授权链接或二维码。新的优秀文案库可独立注册为 generic，不受发布错误元数据结构约束。

## 参考

- [LangChain Embeddings 抽象](https://docs.langchain.com/oss/python/integrations/embeddings)
- [Vectorize 元数据过滤](https://developers.cloudflare.com/vectorize/reference/metadata-filtering/)
- [Vectorize API 与异步 mutation](https://developers.cloudflare.com/vectorize/reference/client-api/)
- [Vectorize 限额](https://developers.cloudflare.com/vectorize/platform/limits/)
- [Workers AI 兼容接口](https://developers.cloudflare.com/workers-ai/configuration/open-ai-compatibility/)
- [DashScope 文本向量 API](https://www.alibabacloud.com/help/en/model-studio/text-embedding-synchronous-api)
