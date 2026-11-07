# 财经 MCP

业务分为采集定稿入库、财经视频制作。通过 `python -m core.mcp.finance` 启动。

| 工具 | 职责 |
|---|---|
| finance_get_config | 唯一生产配置 |
| finance_manage_authors | 作者名单管理 |
| finance_start_collection | 单条、作者配额和续采 |
| finance_finalize_collection | 宿主审核与完整定稿一起入库，配额不足自动启动续采 |
| finance_manage_drafts | 查询和补齐未使用旧稿 |
| finance_start_production | 领取定稿、保存生产稿、后台生成配音及分镜输入 |
| finance_prepare_visuals | 提交分镜，准备生图任务或搜索视频 |
| finance_submit_visuals | 图片保存和图库入库，或下载所选视频；不合成 |
| finance_prepare_editorial | 返回重点句、翻译、章节的宿主定稿输入 |
| finance_validate_editorial | 校验重点句、英文字幕和章节标题 |
| finance_start_render | 合成、提交来源使用状态、默认上传 R2 |
| finance_get_task | 查询所有后台任务 |
| finance_get_inventory | 只读库存、话题、某日成片和生产计划 |

工具在 workflows/business.py 按业务组合现有服务；注册清单仅包含以上12项。内部提示和校验函数保留为业务实现，不单独暴露。公共规则放在 config/server.py，具体交互见项目 collect-finance-copy 和 produce-finance-video 技能。

采集内容由宿主去广告、改写并生成全部定稿字段，入库时统一校验。制作直接使用定稿，分镜、翻译、重点句和章节由宿主生成。MCP 不调用外部通用模型；语音合成与转写保留。GitHub Runner 在 MCP 外的既有模型调用独立保留。所有耗时步骤返回 task_path，finance_get_task 完成后读取 result，采集须额外确认 completed=true。
