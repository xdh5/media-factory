# 运维工具

- `cloudflare/d1-data-api/`：Cloudflare D1 数据接口、迁移与 Worker 部署配置。
- `github_actions/`：GitHub Runner 的视频创建、发布编排与预构建镜像。

每周生产工作流完成各日期的生产后，自动逐日调用语言学习发布工作流，将 R2 中的学中文（`en-zh`）成片预约到计划发布日期北京时间 16:00，使用 `chinese` 账号组发布到 YouTube、TikTok、Instagram、Facebook。调用时继承仓库 Secrets，发布需要配置 `PUBLISHING_CREDENTIALS_JSON` 和现有 D1、R2 凭据。

发布前查询成片和平台发布记录，只处理已有 GitHub R2 成片且尚未发布的平台。部分日期生产失败时，其他日期仍继续发布；重新运行每周工作流会复用已有成片并补齐缺失的平台。也可以手动运行“发布语言学习视频”工作流，按计划发布日期补发。发布失败最多尝试三次，最终失败会反映在独立发布任务中。



本目录只放授权、部署和 Runner 运维入口；业务代码继续放在 `core/`，第三方发布项目继续放在 `integrations/`。

## 财经稿件定稿与生产

采集审核由宿主 Agent 完成正文改写、品牌替换、连载指涉改写、字幕断行、黄金钩子、话题、长短标题、四个标签、封面断行和重点词，正常稿件提交 `finance_finalize_collection` 时附带 `editorial`。原始转写与校对原稿保留，定稿写入 `finance_editorial_drafts`。

未使用旧稿通过 `finance_manage_drafts(action="list")` 读取、`finance_manage_drafts(action="save")` 定稿；已使用记录不能修改。缺少有效定稿的文章计入待编辑，不进入生产队列。Action 只读取已定稿内容，调用 `finance_start_production` 固定到具体计划日期和分片并准备配音，宿主生成分镜后准备和提交素材，使用 `finance_start_render` 合成并交付 R2。

## 生产镜像与动漫发布恢复

生产任务按 Git 提交找到已构建的 Runner，并使用容器仓库返回的镜像摘要启动。镜像首次使用时自动构建，重新运行同一个提交时复用已有镜像。更新 Python 生产依赖时，在仓库根目录重新生成锁定文件并一同提交。

```powershell
uv pip compile pyproject.toml --python-version 3.12 --python-platform x86_64-manylinux_2_36 --generate-hashes --no-header --no-annotate -o ops/github_actions/runner-requirements.txt
```

动漫执行目录里的 `youtube-upload-attempt-*.json` 标记已开始的上传，`youtube-receipt-*.json` 保存确认的 YouTube 视频 ID。上传中断后优先用同一执行 ID 重跑。如果仍提示上传结果待核对，请按标记中的频道、标题和内容标签检查 YouTube Studio。只有人工确认该段确实未上传后，才清除对应分段的本地及 R2 尝试标记，再重跑同一执行。已确认的回执应保留。
