# 运维工具

- `cloudflare/d1-data-api/`：Cloudflare D1 数据接口、迁移与 Worker 部署配置。
- `github_actions/`：GitHub Runner 的视频创建、发布编排与预构建镜像。

每周生产工作流完成各日期的生产后，自动逐日调用语言学习发布工作流，将 R2 中的学中文（`en-zh`）成片预约到计划发布日期北京时间 16:00，使用 `chinese` 账号组发布到 YouTube、TikTok、Instagram、Facebook。调用时继承仓库 Secrets，发布需要配置 `PUBLISHING_CREDENTIALS_JSON` 和现有 D1、R2 凭据。

发布前查询成片和平台发布记录，只处理已有 GitHub R2 成片且尚未发布的平台。部分日期生产失败时，其他日期仍继续发布；重新运行每周工作流会复用已有成片并补齐缺失的平台。也可以手动运行“发布语言学习视频”工作流，按计划发布日期补发。发布失败最多尝试三次，最终失败会反映在独立发布任务中。

每周生产结束后，也会逐日调用“发布财经 YouTube 视频”工作流，使用 `finance` 账号组中的 YouTube 频道预约财经成片。两篇默认分别预约到计划发布日期北京时间 14:00、18:00，单篇只预约 18:00；已过时段不自动改成立即发布。发布复用统一发布 MCP 的 R2 恢复、按频道去重和记录写回能力，失败最多尝试三次，也支持手动按计划发布日期补发。YouTube 的 OAuth 凭据通过 `PUBLISHING_CREDENTIALS_JSON` Secret 注入，数据库仅存频道身份和凭据引用。

财经 YouTube 描述固定为正文使用的黄金钩子、空行、hashtag。生产时将完成品牌替换的钩子保存为 `source-hook.txt` 并上传 R2，发布时恢复该文件；钩子或标签缺失时阻止发布并报错。

本目录只放授权、部署和 Runner 运维入口；业务代码继续放在 `core/`，第三方发布项目继续放在 `integrations/`。
