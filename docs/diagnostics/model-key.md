# 千问视觉模型缺少 API 密钥

实际错误为 QwenVisionConfigurationError，提示读取千问配置失败，缺少 DASHSCOPE_API_KEY。

先检查调用业务线 DASHSCOPE_BUSINESS_LINE。财经可选择 finance 并配置 DASHSCOPE_API_KEY_FINANCE，语言学习可选择 language_learning 并配置 DASHSCOPE_API_KEY_LANGUAGE；没有选择业务线时读取通用 DASHSCOPE_API_KEY。视觉模型和文本模型的密钥选择复用 core/tools/qwen_text/qwen_text.py。

不要将密钥写进任务、日志或评估样本。更改客户端业务配置后重启相关 MCP 服务，并先用只读配置检查验证模型连接。不要以重新下载视频代替模型配置修复。

依据：实际视觉识别失败记录及现有密钥解析代码。本次真实模型测试只调用只读工具。
