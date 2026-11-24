# Codex Cloud 开发环境

本机保留发布器、发布技能和账号。Codex Cloud 使用独立检出目录，仅安装采集和制作依赖；不注册统一发布工具或动漫发布工具，不加载发布技能。发布器源码属于主仓库普通目录，不再需要子模块。

## 云端初始化

在 Codex Cloud 创建连接本仓库的环境，使用 Python 3.12、uv 0.13.9 和 FFmpeg。将 `MEDIA_FACTORY_PROFILE=codex-cloud` 设置为环境变量；按 `environment.example` 配置本次所需变量。不要上传本机 `.env`、发布器 data、浏览器登录目录或 YouTube 授权文件。不要配置 `ANIME_GITHUB_TOKEN` 等可触发发布工作流的凭据。

在没有 `.env` 的独立检出目录中运行以下设置命令：

```bash
uv run --no-project --with python-dotenv python ops/codex_cloud/prepare_environment.py
```

初始化仅修改云端检出目录：生成筛选后的 `.env` 和 `.mcp.json`，移除三个发布技能目录，补充云端指令并安装依赖。不要提交这些环境专属改动。初始化脚本不会自动安装系统级 FFmpeg。

`.mcp.json` 是通用服务配置参考；在使用的云端客户端中按其支持方式注册 finance、language_learning、anime 三个 stdio MCP。生成文件不代表 Codex Cloud 已自动连接项目 MCP。

这是工具和依赖配置隔离，不是对拥有终端权限的开发 Agent 的操作系统沙箱。云端不提供发布凭据是必要条件；共享 D1 和 R2 权限仍应按实际任务分配。

## 本机发布

本机维持默认 local 配置；安装发布依赖时执行：

```powershell
uv sync --locked --no-editable --no-dev --extra mcp --extra publishing
```

agent 和 desktop 安装项已包含发布依赖，既有桌面和独立 Agent 发布入口保留。Docker 默认镜像及 GitHub 生产镜像仍包含发布依赖。
