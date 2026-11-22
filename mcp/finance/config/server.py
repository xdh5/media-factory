"""财经 MCP 服务名称和使用说明。"""

SERVER_NAME = "media-factory-finance"
SERVER_INSTRUCTIONS = """先用 finance_get_config 读生产配置。作者用 finance_manage_authors 管理；库存和弃稿统计用 finance_get_inventory 查询。
采集调用 finance_start_collection。按待审回执的提示筛主题、校对和定稿，再用 finance_finalize_collection 提交整批；有 continuation 就继续审核。未使用旧稿可用 finance_manage_drafts 补定稿。
制作前确认北京时间计划发布日期。finance_start_production 启动完整 workflow；用 finance_get_task(workflow_id=...) 查结果。stage=ready_to_search 时调用 finance_continue_production(workflow_id)；分镜已随定稿保存，实拍素材、合成和 R2 上传由 workflow 自动执行。只有 stage=completed 才代表整条生产完成。
财经抖音公开作品、统计指标与关联定稿用 finance_start_douyin_analysis 只读采集。
后台任务用 finance_get_task 查询生产 workflow_id；采集查询原 task_path，直至完成。宿主负责内容判断、生成和翻译，MCP 负责校验、专用语音和媒体处理。"""
