# 运维工具

- `cloudflare/d1-data-api/`：Cloudflare D1 数据接口、迁移与 Worker 部署配置。
- `github_actions/`：GitHub Runner 的视频创建、发布编排与预构建镜像。

每周生产工作流完成各日期的生产后，自动逐日调用语言学习发布工作流，将 R2 中的学中文（`en-zh`）成片预约到计划发布日期北京时间 16:00，使用 `chinese` 账号组发布到 YouTube、TikTok、Instagram、Facebook。调用时继承仓库 Secrets，发布需要配置 `PUBLISHING_CREDENTIALS_JSON` 和现有 D1、R2 凭据。

发布前查询成片和平台发布记录，只处理已有 GitHub R2 成片且尚未发布的平台。部分日期生产失败时，其他日期仍继续发布；重新运行每周工作流会复用已有成片并补齐缺失的平台。也可以手动运行“发布语言学习视频”工作流，按计划发布日期补发。发布失败最多尝试三次，最终失败会反映在独立发布任务中。



本目录只放授权、部署和 Runner 运维入口；业务代码继续放在 `core/`，第三方发布项目继续放在 `integrations/`。

## 财经稿件定稿与生产

采集审核由宿主 Agent 完成正文改写、品牌替换、连载指涉改写、字幕断行、黄金钩子、话题、长短标题、四个标签、封面断行和重点词，正常稿件提交 `finance_submit_copy_reviews` 时附带 `editorial`。原始转写与校对原稿保留，定稿写入 `finance_editorial_drafts`。

未使用旧稿通过 `finance_list_editorial_drafts` 读取、`finance_save_editorial_drafts` 定稿；已使用记录不能修改。缺少有效定稿的文章计入待编辑，不进入生产队列。Action 只读取已定稿内容，调用 `finance_save_draft` 固定到具体计划日期和分片，再生成分镜、配音、素材及成片并交付 R2。
