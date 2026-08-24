# Cloudflare D1 数据接口

本 Worker 是各业务 MCP 访问 D1 的唯一入口。D1 保存：

- `topic_history`
- `language_learning_words`
- `finance_generated_images`：财经千问生成图库，编号与 `data/image_library_finance/<id>.png` 一致并持续递增
- `publication_records`：记录财经和语言学习内容在各具体平台的标题、发布方式和精确发布时间
- `publishing_account_groups` / `publishing_account_group_members`：统一发布账号组与非敏感路由引用；不保存密码、Cookie、Token 或手机号凭据
- `production_outputs`：按北京时间计划发布日期记录财经和语言学习成片；明确区分本地 MCP 与 GitHub Workflow 来源
- `douyin_research_contents`
- `douyin_research_collections`
- `douyin_research_discoveries`
- `douyin_research_script_usage`

发布记录把 MatrixMedia 视为连接器，最终平台细分为 YouTube、Facebook、Instagram、TikTok、快手、抖音、百家号、小红书、头条号和视频号。`publish_at` 保存带时区的完整 ISO 8601 日期时间：立即发布写实际发送成功时间，预约发布写预约时间。

通过 `POST /v1/publication-records/commit` 幂等写入发布记录；数据库以业务线、标题、平台、账号和分段作为稳定唯一键，不允许外部任务 ID 变化造成重复记录，也不接受空账号。通过 `GET /v1/publication-records` 查询，可选按 `business_line`、`platform`、`publish_date` 和 `run_id` 过滤。通过 `GET /v1/publishing-account-groups` 查询数据库账号组。

通过 `POST /v1/production-outputs/commit` 幂等写入成片记录；通过 `GET /v1/production-outputs` 查询，可选按 `publish_date`、`business_line` 和 `source` 过滤。`source=local_mcp` 保留 `local_path`，按需上传 R2 后补充 `r2_url`；`source=github_workflow` 只在 R2 交付成功后写入 `r2_url`，禁止保存 Runner 临时路径。

抖音研究 MCP 接收用户提供的抖音链接和分类，完成下载、转写后调用 `POST /v1/douyin-research/commit`。作品内容只存一份，内容分类和来源标识记录在 `douyin_research_discoveries`；链接直投的来源标识固定为 `direct_link`。

财经 MCP 通过 `POST /v1/douyin-research/scripts/reserve` 从“财经”分类选择未使用原稿并临时占用，保存改编稿后调用 `POST /v1/douyin-research/scripts/used` 标记为已使用。占用默认两小时后自动过期；全部稿件已使用时接口返回 `DOUYIN_SCRIPTS_EXHAUSTED`，禁止回退到重复稿件。

可通过 `GET /v1/douyin-research/scripts/stats?collection_code=finance&workflow=finance&reservation_minutes=120` 只读查询稿件总数、可用数、有效占用数和已使用数；过期占用计入可用数，查询不会创建或更新占用记录。

财经 MCP 的参考图千问生图完成后，从 `data/image_library_finance/` 当前最大图片编号继续递增，
并通过 `POST /v1/finance-generated-images/commit` 把相同编号、图片描述和项目相对路径写入独立生成图库；
可通过 `GET /v1/finance-generated-images` 按连续编号读取。

部署前需要：

1. 创建名为 `media-factory` 的 D1 数据库，把数据库 ID 写入 `wrangler.jsonc`。
2. 执行 `wrangler d1 migrations apply media-factory --remote`。
3. 为 Worker 设置秘密 `DATA_API_TOKEN`。
4. 为 GitHub Pages 发布看板设置六位数字秘密 `DASHBOARD_PIN`。看板只读接口为 `GET /v1/dashboard/records`，Worker 必须先验证 `X-Dashboard-Pin` 才查询 D1；无 PIN 或错误 PIN 返回 401。跨域读取仅允许 `https://xdh5.github.io`，响应不会返回本地路径、账号凭据或数据 API Token。
5. 部署 Worker，并把地址与相同令牌填入 MCP 宿主环境变量：
   - `CLOUDFLARE_DATA_API_URL`
   - `CLOUDFLARE_DATA_API_TOKEN`

当前目录只提供结构与接口实现，不会自动迁移或覆盖本地 SQLite 数据。
