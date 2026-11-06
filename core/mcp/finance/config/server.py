"""财经 MCP 服务名称和使用说明。"""

SERVER_NAME = "media-factory-finance"
SERVER_INSTRUCTIONS = """先用 finance_get_config 读生产配置。作者用 finance_manage_authors 管理；库存和弃稿统计用 finance_get_inventory 查询。
采集调用 finance_start_collection。按待审回执的提示筛主题、校对和定稿，再用 finance_finalize_collection 提交整批；有 continuation 就继续审核。未使用旧稿可用 finance_manage_drafts 补定稿。
制作前确认北京时间计划发布日期。finance_start_production 领取定稿并准备配音和分镜输入。宿主写分镜，依次准备和提交素材，再用 finance_prepare_editorial 定稿重点句、英文字幕和章节。合入配置后用 finance_start_render 合成及交付。
后台任务用 finance_get_task 查询原 task_path，直至完成。宿主负责内容判断、生成和翻译，MCP 负责校验、专用语音和媒体处理。"""
