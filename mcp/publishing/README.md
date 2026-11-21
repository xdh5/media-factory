# 发布账号工具

`publishing_list_account_groups` 只查询并筛选数据库配置，不启动浏览器，不返回登录通过结论。

`publishing_start_account_check` 接收业务线、账号组和平台范围，返回后台任务路径。
使用 `publishing_poll_task` 查看当前账号、平台、阶段、运行耗时和错误；任务完成后读取
`result.all_accounts_ready`、`login_states` 与异常截图，全部通过后才发布。

预检逐平台执行，页面检测异常交由宿主查看截图，不调用外部模型。已有扫码、复核和发布工具保持原有职责。
