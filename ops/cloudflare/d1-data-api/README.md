# Cloudflare D1 数据接口

本 Worker 是各业务 MCP 访问 D1 的唯一入口。D1 保存：

- `topic_history`
- `language_learning_words`
- `image_library`
- `publish_account_groups`
- `publish_accounts`
- `publish_account_group_members`
- `douyin_research_contents`

发布账号表只保存平台、连接器和配置别名，不保存密码、Cookie、Token、手机号，也不导入 MatrixMedia 的账号明细。图片和视频文件继续存 R2，`image_library.image_path` 只保存项目相对路径。

发布账号组通过 `GET /v1/publish-account-groups` 查询；传入 `group` 可按编码或中文名读取单组，例如 `GET /v1/publish-account-groups?group=中文`。

抖音研究 MCP 通过 `GET /v1/douyin-research/ids` 做作品 ID 去重；只有用户确认后才调用 `POST /v1/douyin-research/commit` 保存作者、发布时间、文案和转写文本。

部署前需要：

1. 创建名为 `media-factory` 的 D1 数据库，把数据库 ID 写入 `wrangler.jsonc`。
2. 执行 `wrangler d1 migrations apply media-factory --remote`。
3. 为 Worker 设置秘密 `DATA_API_TOKEN`。
4. 部署 Worker，并把地址与相同令牌填入 MCP 宿主环境变量：
   - `CLOUDFLARE_DATA_API_URL`
   - `CLOUDFLARE_DATA_API_TOKEN`

当前目录只提供结构与接口实现，不会自动迁移或覆盖本地 SQLite 数据。
