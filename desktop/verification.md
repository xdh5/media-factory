# 绿色版实际验收记录

验收日期：2026 年 10 月 21 日。Windows 本机构建并运行了 `dist/MediaFactory/MediaFactory.exe`，交付形式为约 3.7 GiB 的完整绿色版目录，不是单文件程序或安装包。Docker 引擎不可用，因此使用原生 Windows 构建。

## 桌面与 Agent

- 清除开发机 Python、Node.js、FFmpeg 的 PATH 后启动真实 EXE，原版 Open WebUI 正常渲染并发现四个业务模型。
- 通过原版 Open WebUI 的聊天接口调用真实 qwen-plus，再调用现有 `finance_get_production_config` MCP 工具，返回 HTTP 200 和 completed 状态。
- 桌面管理窗口的会话认证、执行记录读取通过；退出后服务端口关闭，监督进程退出。Windows Job Object 的独立进程清理验收通过。
- 真实模型集成验收覆盖流式响应、多轮工具调用、审批前中断、拒绝审批、检查点重启恢复、Trace 与 Token、脱敏、视频 Range 预览及签名重启后继续有效。
- 本轮没有新增单元测试，没有实际发布视频，也没有执行生产任务作为验收。

证据：`cache/desktop-verification/portable-b685637951e04e99a7d967fe1934d05e/desktop-verification.json`、同目录截图，以及 `cache/desktop-verification/6de62ea79e0f44529277e3996495013e/verification.json`。

## 诊断与评估

- 实际调用 Embedding、模型重排与诊断接口；验证脱敏、知识去重、数据库重新打开和已验证记忆保存。
- Agent 读取一条真实历史失败任务后自主检索故障文档，生成诊断；未重启原生产任务。
- 四条真实历史错误的小样本评估：Recall@1 为 1.0，来源相关性为 1.0，关键词组命中率为 1.0。样本较小，不能代表通用诊断能力。
- 本次生成答案尚未经过独立人工复核，诊断准确率为 null。管理窗口支持逐条复核并记录证据；不把关键词命中冒充准确率。
- 完整来源、模型和原始回答见 `desktop/rag-evaluation-results.json`；没有验收标签的 Agent 任务成功率同样保持 null。

## 首次使用与限制

完整复制 `dist/MediaFactory` 后双击 EXE。首次需联网，填写有可用额度的 LLM、Embedding 和业务凭据；配置业务凭据后重启客户端。默认数据保存在 `%APPDATA%\MediaFactory`，升级只替换程序目录。

现有默认 DeepSeek 模型在验收时返回免费额度耗尽错误；没有修改计费设置，改用已有 qwen-plus 配置完成验收。客户端不预置开发机密钥、平台授权或历史生产数据。真实平台发布仍需账号配置和逐次人工审批，未做真实上传验收。

源码及依赖导入、JavaScript 语法、Python 编译与 Git 空白检查通过。没有提交或推送代码。

## 聊天入口修正验收

已去掉自动弹出的管理窗口及菜单入口。项目内启动自动复用已有配置；EXE 实际启动验收确认 `chatWindowCount=1`，只有原版 Open WebUI 聊天窗口，关闭后服务正常退出。证据：`cache/desktop-verification/portable-a83dc92a459d4fda8c5ef8460a980254/desktop-verification.json`。审批在当前聊天回复“同意”或“取消”，不要求任务 ID。

真实 qwen-plus、HTTP 与 MCP 回归通过，审批通过当前聊天发送“取消”完成，未调用管理审批接口。多轮、流式、检查点重启、视频签名与进程清理继续通过。证据：`cache/desktop-verification/efed12e2413140068bbe235f7f3d5a6c/verification.json`。

## 真实千问模型入口验收

模型列表改为实际 `qwen-plus`，同一个 Agent 获得全部业务工具，旧业务模型不再列出。EXE 实际窗口文本包含 qwen-plus，不含原 finance 模型名；原版 Open WebUI 与网关均只返回一个模型，真实模型转发 HTTP 200，仍仅一个聊天窗口。证据：`cache/desktop-verification/portable-262b83a38f12412baabf49db897655e6/desktop-verification.json`。真实模型流式、多轮、审批、重启回归通过：`cache/desktop-verification/32bd4fde7ef849279b1f229962a349cb/verification.json`。

## Token 实际测量

使用真实 deepseek-v4-pro 和原任务记录的 27 条运行中、1 条完成进度重放，经过 143.53 秒，28 次程序进度读取期间新增模型请求为零。场景总共两次真实模型请求，输入 42,577 Token、输出 244 Token，总计 42,821。通过真实 stdio MCP 查询原任务，确认 done=true、status=succeeded。该测试没有重新下载或转写，不等同于新任务全流程消耗。

原任务总计 805,832 Token；等待场景重放相比该历史总量低 94.69%，两者范围不同，不能作为完整生产任务的固定节省比例。首次测量脚本错误消耗 50,956 Token，失败证据保留，本轮两次测量累计实际消耗 93,777 Token、五次模型请求。详见 `desktop/token-measurement-results.json` 及其证据路径。
