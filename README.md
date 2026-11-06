# Media Factory

Media Factory 用于制作和发布财经、语言学习和动漫视频。宿主 Agent 负责内容判断、文案、分镜与生图，MCP 负责校验、媒体处理、任务状态和产物交付。财经支持实拍素材与参考图生图，语言学习支持词包复用，动漫支持本地制作和 GitHub Runner 发布。

## 快速开始

从仓库根目录初始化子模块并安装 Python 依赖。运行环境需要 Python 3.10+ 和 FFmpeg，运行 GitHub 生产入口及桌面构建时使用 Python 3.12。

```powershell
git submodule update --init --recursive
python -m pip install .
Copy-Item -LiteralPath .env.example -Destination .env
```

首次创建 `.env` 后按所用业务填写凭据。MCP 使用 stdio，工具客户端可按需注册下列入口。

| 业务 | 启动命令 |
| --- | --- |
| 财经 | `python -m core.mcp.finance` |
| 语言学习 | `python -m core.mcp.language_learning` |
| 动漫 | `python -m core.mcp.anime` |
| 统一发布 | `python -m core.mcp.publishing` |

本地 Docker 镜像包含 Python、FFmpeg、业务代码和媒体资源。需要内置 Agent 时加 `--build-arg INSTALL_AGENT=true`。浏览器发布使用桌面环境中的 Electron 发布器。

```powershell
docker build -t media-factory .
docker run --rm -it --env-file .env -v "${PWD}/data:/app/data" -v "${PWD}/cache:/app/cache" media-factory
```

## 项目结构

| 目录 | 职责 |
| --- | --- |
| `core/mcp/` | 业务工具入口、工作流与后台任务 |
| `core/tools/` | 可复用的媒体处理、数据读写和发布适配 |
| `core/paths.py` | 工作区、数据、缓存和媒体资源路径 |
| `agent/`、`.agents/skills/` | Agent 运行时与业务技能 |
| `apps/` | 桌面客户端和网页看板 |
| `integrations/` | 采集与发布子模块 |
| `ops/` | GitHub Runner、Cloudflare Worker、桌面构建及运维入口 |
| `core/static/` | 字体、封面底图、音乐和音效 |

本地持久数据放在 `data/`，生产中间文件与工具缓存放在 `cache/`，成片在 `cache/output/`，临时文件在 `cache/tmp/`。桌面绿色版默认输出到 `dist/MediaFactory/`。这些目录均独立于源码提交。

## 延伸说明

- [Agent 使用说明](agent/README.md)
- [桌面端构建与运行](apps/desktop/README.md)
- [生产与部署运维](ops/README.md)
- [发布账号配置](docs/publishing-accounts.md)
- [MCP 模型调用边界](docs/mcp-model-boundary.md)

## 许可证

主仓库使用 [MIT 许可证](LICENSE)。采集子模块使用 MIT，发布子模块使用 GPL-2.0-only。
