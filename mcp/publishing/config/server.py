"""统一发布 MCP 服务配置。"""

SERVER_NAME = "media-factory-publishing"

SERVER_INSTRUCTIONS = """按业务线、计划日期、账号组、平台和发布方式发布。立即发布用 immediate + now；预约用 scheduled 和带时区的未来 ISO 8601。
publishing_list_account_groups 只查配置。用 publishing_start_account_check 与 publishing_poll_task 核验本次目标的真实发布页或官方授权。仅 login_required 提供登录入口或二维码；检测异常有截图时先查看，再用 publishing_review_session 提交判断。页面或网络失败单独报告。
账号未全部通过前不恢复或上传成片。all_accounts_ready=true 后先提示 **全部账号已登录，开始发布**，再自动继续。优先本地成片，缺失时从 GitHub R2 产物恢复；查重复记录，按平台保存成功回执。
多日用 publishing_start_batch，交给后台执行，按需查 publishing_batch_status。单日用 publishing_start_publish 和 publishing_poll_task。提交结果不明先查回执。
财经默认北京时间第一篇 14:00、第二篇 18:00。只有一篇或 14:00 已过时只排 18:00 一篇。用户指定单个预约时刻时只排一篇。"""
