# Cloudflare D1 数据接口

本 Worker 是各业务 MCP 访问 D1 的唯一入口。D1 只保存：

- `topic_history`
- `language_learning_words`
- `image_library`

矩阵媒体账号表禁止导入。图片和视频文件继续存 R2，`image_library.image_path` 只保存项目相对路径。

部署前需要：

1. 创建名为 `media-factory` 的 D1 数据库，把数据库 ID 写入 `wrangler.jsonc`。
2. 执行 `wrangler d1 migrations apply media-factory --remote`。
3. 为 Worker 设置秘密 `DATA_API_TOKEN`。
4. 部署 Worker，并把地址与相同令牌填入 MCP 宿主环境变量：
   - `CLOUDFLARE_DATA_API_URL`
   - `CLOUDFLARE_DATA_API_TOKEN`

当前目录只提供结构与接口实现，不会自动迁移或覆盖本地 SQLite 数据。
