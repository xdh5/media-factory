# 模型免费额度耗尽

实际接口错误为 HTTP 403，错误码 AllocationQuota.FreeTierOnly，返回 Free quota exhausted。该错误在真实模型回归请求中出现，不能将其归因于桌面客户端、MCP 或网络超时。

当前模型启用了仅使用免费额度的限制，额度已耗尽。先核对模型名称与接口错误码，可以由用户选择仍有可用额度的兼容模型或更换有效凭据；若要启用付费调用，必须由账户所有者在服务商控制台自行确认，不允许 Agent 自动充值或修改付费开关。

更改 Agent 文本模型可以使用 AGENT_MODEL 或 DASHSCOPE_MODEL。Embedding 和重排模型分别通过 AGENT_EMBEDDING_MODEL、AGENT_RERANK_MODEL 配置，文本模型额度不足不代表其他模型也不可用。

401、403 不应被无限重试。保留当前检查点，修复模型配置后恢复相同任务，已经完成的 MCP 操作继续复用回执。

依据：本次真实接口返回的 AllocationQuota.FreeTierOnly 及 agent/llm.py 的有限重试策略；没有修改账户付费设置。
