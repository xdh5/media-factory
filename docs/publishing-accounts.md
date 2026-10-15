# 发布账号配置

账号路由以 D1 数据库为准。`publishing_accounts` 保存平台、连接器账号 ID、真实平台 ID、展示名称、凭据引用和启用状态；`publishing_account_group_members.account_key` 将账号加入内容组。同一账号可以属于多个组，同一组可以包含同平台多个账号。停用账号会从发布路由中排除。

敏感信息不写入数据库、源码或镜像。本地凭据在 `integrations/media-publisher/data/credentials.json`，GitHub Actions 使用 `PUBLISHING_CREDENTIALS_JSON` Secret。两者结构相同：顶层键是数据库的 `credential_ref`；Zernio 凭据包含 `api_key`，YouTube 凭据包含 `client_id`、`client_secret`、`refresh_token`。多个 Zernio 账号可以共用工作区凭据，YouTube 每个频道独立授权。

现有引用为 `youtube_chinese`、`zernio_tiktok`、`zernio_meta`。账号组和平台账号 ID 不再通过 GitHub Secrets 或本地账号组 `.env` 配置。

新增账号时先查询平台返回的连接器账号 ID 与真实平台 ID，建立 `publishing_accounts` 记录，再加入账号组。新授权写入凭据文件；已有工作区授权可以复用原引用。不要用连接器 ID 代替平台真实 ID。数据库迁移必须先应用到远程，再部署 Worker。

同步本地账号快照与 GitHub 凭据：在项目根目录执行 `python -m ops.publishing.sync_configuration`。该命令只同步已有配置，不创建备份、不打印密钥。更改仓库时使用 `--repository`。本地独立运行 media-publisher 时读取账号快照；配置了数据 API 地址和凭据时直接读取数据库。

发布前逐账号核验授权及真实身份。身份不匹配、缺少凭据或单账号发布失败时，其他可用账号继续执行；成功项逐账号入库，重试跳过已有记录。多账号目标按账号标识区分；直接使用 media-publisher 时可在视频条目填写 `account_key`，未指定时发布到组内该平台全部账号。

同步凭据不等于轮换平台密钥。授权刷新或轮换后需要再次运行同步。禁止提交 `data`、凭据文件和 `.env`。
