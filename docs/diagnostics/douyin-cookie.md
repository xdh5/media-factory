# 财经采集缺少抖音 Cookie

实际错误现象：没有抓到可入库的财经稿件，提示缺少 DY_COOKIES，且 Cookie 必须包含 UIFID。

诊断：登录态未配置或不完整，不能把它解释为作者没有作品。先在 www.douyin.com 登录，从浏览器复制完整 Cookie，写入本地私有配置 DY_COOKIES。不要将 Cookie 贴入聊天、知识库或日志。客户端保存配置后重启 MCP 服务，再检查登录态和重新执行获批的采集步骤。

依据：integrations/media-collector/core 中的抖音配置与 Cookie 检查，以及真实采集任务的错误信息。未在本次诊断验收中重新采集或改变生产记录。
