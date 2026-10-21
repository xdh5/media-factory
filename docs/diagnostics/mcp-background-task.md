# MCP 后台任务在服务退出后中断

错误类型为 OrphanTaskError，现象为任务文件仍写 running，但当前 MCP 进程不存在对应 worker。实现依据是 core/mcp/_task_runner.py 的 poll_task 与 _fail_orphan_tasks。

这是原本后台线程所属的 MCP 进程退出或重启导致的，不能靠重复 poll 使旧线程恢复。先检查任务文件、已生成产物和发布记录；有远端 GitHub Action 时单独查询远端结果。已经完成的副作用不能重复执行。确认步骤未完成后，再经人工审批重新 start 相应步骤。

桌面端在审批暂停期间保持 MCP 会话长驻。整个客户端关闭后，本地线程仍会终止，LangGraph 检查点只能恢复编排状态，不能恢复已消失的媒体计算线程。

此诊断基于实际 OrphanTaskError 历史记录和现有代码核对，不代表原生产故障已重新运行修复。
