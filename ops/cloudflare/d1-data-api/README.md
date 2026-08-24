# Cloudflare D1 数据接口

本 Worker 是各业务 MCP 访问 D1 的唯一入口。D1 保存：

- `topic_history`
- `language_learning_words`
- `image_library`
- `finance_generated_images`：财经千问生成图库，编号与 `data/image_library_finance/<id>.png` 一致并持续递增
- `publish_account_groups`
- `publish_accounts`
- `publish_account_group_members`
- `douyin_research_contents`
- `douyin_research_collections`
- `douyin_research_discoveries`
- `douyin_research_script_usage`

发布账号表只保存平台、连接器和配置别名，不保存密码、Cookie、Token、手机号，也不导入 MatrixMedia 的账号明细。图片和视频文件继续存 R2，`image_library.image_path` 只保存项目相对路径。

发布账号组通过 `GET /v1/publish-account-groups` 查询；传入 `group` 可按编码或中文名读取单组，例如 `GET /v1/publish-account-groups?group=中文`。

抖音研究 MCP 接收用户提供的抖音链接和分类，完成下载、转写后调用 `POST /v1/douyin-research/commit`。作品内容只存一份，内容分类和来源标识记录在 `douyin_research_discoveries`；链接直投的来源标识固定为 `direct_link`。

财经 MCP 通过 `POST /v1/douyin-research/scripts/reserve` 从“财经”分类选择未使用原稿并临时占用，保存改编稿后调用 `POST /v1/douyin-research/scripts/used` 标记为已使用。占用默认两小时后自动过期；全部稿件已使用时接口返回 `DOUYIN_SCRIPTS_EXHAUSTED`，禁止回退到重复稿件。

财经 MCP 的参考图千问生图完成后，从 `data/image_library_finance/` 当前最大图片编号继续递增，
并通过 `POST /v1/finance-generated-images/commit` 把相同编号、图片描述和项目相对路径写入独立生成图库；
可通过 `GET /v1/finance-generated-images` 按连续编号读取。

部署前需要：

1. 创建名为 `media-factory` 的 D1 数据库，把数据库 ID 写入 `wrangler.jsonc`。
2. 执行 `wrangler d1 migrations apply media-factory --remote`。
3. 为 Worker 设置秘密 `DATA_API_TOKEN`。
4. 部署 Worker，并把地址与相同令牌填入 MCP 宿主环境变量：
   - `CLOUDFLARE_DATA_API_URL`
   - `CLOUDFLARE_DATA_API_TOKEN`

当前目录只提供结构与接口实现，不会自动迁移或覆盖本地 SQLite 数据。
