# 运维工具

- `youtube/oauth.py`：为 YouTube 频道生成、检查并写入 OAuth 配置。
- `cloudflare/d1-data-api/`：Cloudflare D1 数据接口、迁移与 Worker 部署配置。
- `github_actions/`：GitHub Runner 的视频创建编排与预构建镜像；只生成成片并上传 R2，不执行平台发布。

本目录只放授权、部署和 Runner 运维入口；业务代码继续放在 `core/`，第三方发布项目继续放在 `integrations/`。
