# Media Factory

Media Factory 用于制作和发布财经、语言学习和动漫视频。宿主 Agent 负责内容判断、文案、分镜与生图，MCP 负责校验、媒体处理、任务状态和产物交付。财经使用实拍素材，语言学习支持词包复用，动漫支持本地制作和 GitHub Runner 发布。

## 快速开始

从仓库根目录初始化子模块并安装 Python 依赖。运行环境统一使用 Python 3.12、uv 0.13.9 和 FFmpeg。Python 依赖统一声明在 `pyproject.toml`，完整解析结果由 `uv.lock` 固定。

```powershell
git submodule update --init --recursive
uv sync --locked --no-editable --no-dev --extra mcp
Copy-Item -LiteralPath .env.example -Destination .env
```

项目 MCP 源码位于 `mcp/`，由 `pyproject.toml` 映射为 Python 包 `media_factory_mcp`。安装后通过该包名导入和启动，第三方 SDK 使用 `mcp`。修改业务代码、提示词、技能或资源后需重新执行 `uv sync --locked --no-editable --no-dev --extra mcp --reinstall-package media-factory`。

安装 uv 可使用官方安装器；依赖变更后执行 `uv lock`，升级单个包执行 `uv lock --upgrade-package 包名`，并提交 `pyproject.toml` 和 `uv.lock`。Agent 使用 `--extra agent`，桌面界面使用 `--extra desktop`，两者使用独立环境。

首次创建 `.env` 后按所用业务填写凭据。MCP 使用 stdio，工具客户端可按需注册下列入口。

| 业务 | 启动命令 |
| --- | --- |
| 财经 | `uv run --locked --no-editable --no-dev python -m media_factory_mcp.finance` |
| 语言学习 | `uv run --locked --no-editable --no-dev python -m media_factory_mcp.language_learning` |
| 动漫 | `uv run --locked --no-editable --no-dev python -m media_factory_mcp.anime` |
| 统一发布 | `uv run --locked --no-editable --no-dev python -m media_factory_mcp.publishing` |

工作区包含三个发行包：`media-factory` 提供 `tools`、`agent`、`media_factory_mcp`、`desktop` 和生产命令；`media-collector` 提供采集接口；`media-publisher-python` 提供发布适配。采集和发布包由 uv 正式安装，包内静态资源与可写工作目录分离。

运行工作目录通过启动进程的 `MEDIA_FACTORY_WORKSPACE` 指定，默认使用当前目录；相对路径按启动目录解析。`data/`、`cache/`、成片和临时文件写入该目录。字体、音乐、模板、提示词、技能和桌面页面通过已安装发行包定位，不从工作目录读取。

```powershell
$env:MEDIA_FACTORY_WORKSPACE = "D:\MediaFactory"
```

本地 Docker 镜像包含 Python、FFmpeg、已安装的业务包 和包内媒体资源。需要内置 Agent 时加 `--build-arg INSTALL_AGENT=true`。浏览器发布使用桌面环境中的 Electron 发布器。

```powershell
docker build -t media-factory .
docker run --rm -it --env-file .env -v "${PWD}/data:/app/data" -v "${PWD}/cache:/app/cache" media-factory
```

## 项目结构

| 目录 | 职责 |
| --- | --- |
| `workflows/` | 财经与语言学习共用的业务流程，供 MCP 和 GitHub 调用 |
| `mcp/` | 业务工具入口、工作流与后台任务 |
| `tools/` | 可复用的媒体处理、数据读写和发布适配 |
| `tools/paths.py` | 工作区、数据、缓存和媒体资源路径 |
| `agent/`、`.agents/skills/` | Agent 运行时与业务技能 |
| `apps/` | 桌面客户端和网页看板 |
| `integrations/` | 采集与发布子模块 |
| `ops/` | GitHub Runner、Cloudflare Worker、桌面构建及运维入口 |
| `tools/static/` | 字体、封面底图、音乐和音效 |

本地持久数据放在 `data/`，生产中间文件与工具缓存放在 `cache/`，成片在 `cache/output/`，临时文件在 `cache/tmp/`。桌面绿色版默认输出到 `dist/MediaFactory/`。这些目录均独立于源码提交。

## 延伸说明

- [Agent 使用说明](agent/README.md)
- [桌面端构建与运行](apps/desktop/README.md)
- [生产与部署运维](ops/README.md)

## 许可证

主仓库使用 [MIT 许可证](LICENSE)。采集子模块使用 MIT，发布子模块使用 GPL-2.0-only。

财经与语言学习的生产参数分别维护在 `workflows/finance/parameters.py` 和 `workflows/language_learning/parameters.py`。MCP 和 GitHub 仅调用公共 workflow；业务步骤封装放在各自 workflow 的 tools/，外部存储接入和包内资源放在 infrastructure/，提示词放在独立 prompts/。公共任务执行、日期处理和媒体能力放在根目录 tools/；workflow 不导入 MCP 业务包。

Python 字节码缓存统一保存在工作目录的 `cache/pycache/`。本地命令使用 `uv run --env-file .env` 加载缓存配置；直接运行 `python` 时需先设置 `PYTHONPYCACHEPREFIX`。Docker、MCP、GitHub Actions 和桌面启动已配置对应目录。

周生产镜像只安装基础生产与官方发布依赖，不包含 MCP、采集、Agent、桌面或技能。MCP 使用 `--extra mcp`，动漫执行镜像使用独立 `anime` 目标。每个日期的语言成片交付 R2 后立即预约发布，已有成片仅补发缺少的平台。
