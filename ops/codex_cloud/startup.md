# Media Factory 云端启动指引

每个新聊天先进入 `/workspace/media-factory`，读取仓库根目录 `AGENTS.md` 和当前任务对应的 `.agents/skills/*/SKILL.md`。先宣布使用哪个技能，再执行任务；即使宿主没有自动列出仓库技能，也必须从文件读取。

大鹅认知业务的内部目录名是 finance，覆盖心理、情绪、关系、职场、家庭、人生和通俗财富。用户提出“刷手机逃避不安，怎样重新面对自己”等主题或要求制作文章，应读取 `.agents/skills/collect-finance-copy/SKILL.md` 及其引用的撰稿提示词。要求制作长短视频时再读取 `.agents/skills/produce-finance-video/SKILL.md`。不要因 README 中的“财经”二字误判仓库，也不要把用户的计划发布日期当成先询问发布平台的理由。

语言词包、语言视频和动漫分别使用对应的 produce 技能。未完成技能要求的正文、定稿、封面、分镜或入库时，按实际状态交付，不得将通用文章草稿报告为整个业务已完成。仅提供主题而缺少真实来源时，不虚构采集记录。

云端保持 `MEDIA_FACTORY_PROFILE=codex-cloud`，不得加载 publish 技能或向内容平台上传、预约、发布；允许制作流程向 R2 上传素材、封面和成片，也不得触发发布工作流。不得读取本机发布凭据。本机发布能力保留。

先核实当前聊天是否实际具备业务 MCP 工具；`.mcp.json` 和独立 Codex CLI 配置只是连接配置。未自动加载时读取 `mcp/client.py`，通过项目 `ProjectMCP` stdio 客户端调用已安装的 finance、language_learning 或 anime 服务。只调用业务工具，不绕过其校验直接写库；缺少凭据时明确报告，不能跳过业务流程直接生成替代稿。

若用户要求更新代码，先检查当前分支、工作区改动和远端提交，保留已有改动；更新后重新读取技能文件。不要假定已发布快照永远等于最新 main。
