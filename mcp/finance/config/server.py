"""财经 MCP 服务名称和使用说明。"""

SERVER_NAME = "media-factory-finance"
SERVER_INSTRUCTIONS = """先用 finance_get_config 读生产配置。作者用 finance_manage_authors 管理；库存和弃稿统计用 finance_get_inventory 查询。
采集调用 finance_start_collection。按待审回执的提示筛主题、校对原稿，再吸收主题观点原创撰稿并定稿，再用 finance_finalize_collection 提交整批；有 continuation 就继续审核。未使用旧稿可用 finance_manage_drafts 补定稿。
预先给稿件生图时，用 finance_manage_storyboard_images(aweme_id) 领取图片任务和参考图；生成后以 image_paths 提交同一工具，上传 R2 并登记。GitHub Runner 直接下载远端图片。
定稿入库后用 finance_manage_cover 领取封面任务，宿主参考样图分别生成含文字的16:9横版和9:16竖版封面，验字后以 image_paths 同时提交 landscape、portrait 两版上传 R2。生产直接下载已登记封面，不代码叠字。
制作前确认北京时间计划发布日期。finance_start_production 默认搜索实拍素材，generate_images=true 则使用生图模式。同一日期和分片重复启动恢复原模式。用 finance_get_task(workflow_id=...) 查结果。
stage=ready_to_search 时调用 finance_continue_production(workflow_id)。stage=awaiting_images 时，宿主读取 image_generation_reference，使用参考图和 image_requests 生成各镜图片，保存到 output_path 后调用 finance_continue_production(workflow_id)；另存位置时按镜头顺序传 image_paths。MCP 不调用生图模型。之后素材处理、合成和 R2 上传由 workflow 执行。只有 stage=completed 才代表整条生产完成。
财经抖音公开作品、统计指标与关联定稿用 finance_start_douyin_analysis 只读采集。
后台任务用 finance_get_task 查询生产 workflow_id；采集查询原 task_path，直至完成。宿主负责内容判断、生成和翻译，MCP 负责校验、专用语音和媒体处理。"""
