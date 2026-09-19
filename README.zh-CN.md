# Media Factory

[English](README.md) | [简体中文](README.zh-CN.md)

一个由 AI Agent 编排的短视频生产与发布系统。

Media Factory 通过可复用的媒体工具、模型上下文协议（MCP）工作流、持久化生产记录和多平台发布集成，将原始素材转化为可直接发布的竖屏视频。

项目目前运行两条生产线：语言学习视频，以及面向财经常识内容的文生图视频。抖音研究资料入库和统一多平台发布能力为两条生产线提供支持。

## 为什么需要这个项目

制作一条短视频并不困难，长期稳定地运营一条内容生产线却很困难。

实际生产系统需要协调素材选择、话题去重、文稿与图片生成、语音合成、字幕、视频渲染、产物交付、预约发布和故障恢复，同时避免重复选题和重复发布。

Media Factory 将这些环节设计为一个有状态、可恢复的工作流，而不是一组互不关联的生成脚本。

## 核心能力

### Agent 编排的生产流程

每条业务工作流都作为独立的 MCP Server 暴露。AI Agent 可以通过结构化工具调用检查素材、准备内容、启动耗时任务、验收生成资源并继续后续流程。

图片生成和 FFmpeg 渲染等耗时操作统一采用“启动任务 + 轮询状态”的异步模式，避免 MCP 客户端被长时间阻塞。

### 可复用的媒体工具层

不同业务生产线共享以下 Python 工具：

- 文本、图片和语音生成
- 字幕、封面和镜头合成
- 基于 FFmpeg 的视频组装
- 视频下载与语音转写
- 云存储和持久化数据访问
- 各平台发布适配

MCP Server 只负责编排这些公开工具 API，不在协议层重复实现媒体处理逻辑。

### 持久化与幂等工作流

Cloudflare D1 保存话题占用、来源使用状态、生产产物、词汇历史、生成图片和平台发布记录等运行数据。

生产和发布写入均采用幂等设计。工作流部分失败后，可以先检查现有状态再继续执行，无需盲目重新生成资源，也不会重复发布已经成功的平台。

### 多平台发布

统一发布流程支持 YouTube、TikTok、Facebook、Instagram、抖音、快手、头条号和视频号。

正式发布前，系统会预览待发布产物、解析账号组并查询已有发布记录。每个平台的成功结果都会立即单独写入，因此部分平台失败后可以安全补发。

### 定时批量生产

GitHub Actions 每周批量生产下一周周一至周日的内容。每个计划发布日期独立且串行处理，单个产品或日期失败不会阻断剩余任务。

生成产物通过 Cloudflare R2 交付，生产和发布结果通过 Telegram 通知。

## 系统架构

![Media Factory 系统架构](docs/assets/architecture.svg)

项目明确分离业务编排和底层实现：

```text
core/
├── mcp/             # MCP 工作流入口与后台任务编排
└── tools/           # 媒体、存储、数据和发布工具包

ops/
├── cloudflare/      # D1 数据接口与数据库迁移
├── github_actions/  # 定时生产编排
└── youtube/         # YouTube OAuth 运维工具

integrations/
└── MatrixMedia/     # 本地多平台发布集成

dashboard/           # 发布管理面板
config/              # 运行配置
data/                # 本地持久化资源库
cache/               # 可恢复的中间产物
output/              # 本地最终成片
```

## 生产流程

### 财经常识文生图视频

```text
选择来源稿件
    → 改编文稿
    → 话题校验
    → 生成标题和元数据
    → TTS 与分镜
    → 生成镜头图片
    → 合成封面与视频
    → 登记生产记录
    → 交付 R2
```

这条文生图生产线将财经常识转化为视觉化短视频。来源稿件会在使用前临时占用，并在草稿成功保存后才标记为已使用。生成图片单独登记，数据库写入失败时可以只重试登记，不必重新生成图片。

### 语言学习视频

```text
选择话题
    → 生成词表
    → 校验近期词汇历史
    → 生成主体图
    → 视觉验收
    → 合成固定模板卡片
    → 双语 TTS
    → 生成原版和问答版视频
    → 登记生产记录
    → 发布
```

系统会根据近期历史检查词汇，减少内容重复。同一次生产会生成标准学习版和带倒计时的问答版。

### 抖音研究资料入库

```text
抖音分享链接
    → 下载视频
    → 语音转写
    → 指定分类
    → 写入 D1
```

该流程把单条抖音分享链接转换为可供后续内容生产复用的研究素材。

## 技术栈

- Python 3.10+
- Model Context Protocol 与 FastMCP
- FFmpeg 与 Pillow
- 千问文本、视觉与生图模型
- Groq Whisper 语音转写
- Cloudflare D1 与 R2
- GitHub Actions
- YouTube Data API、Zernio 与 MatrixMedia
- Docker

## 快速开始

### 环境要求

- Python 3.10 或更高版本
- 已将 FFmpeg 加入 `PATH`
- 支持 MCP 的客户端
- 当前工作流所需外部服务的凭据

无需配置所有集成。例如，只在本地生产财经视频时，不需要填写所有发布平台的凭据。

### 1. 克隆仓库

```bash
git clone git@github.com:xdh5/media-factory.git
cd media-factory
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

只需填写当前工作流用到的服务配置。所有可用配置均记录在 `.env.example` 中。不要提交填写过凭据的 `.env` 文件。

### 3. 安装运行环境

单独安装 FFmpeg，然后安装 Python 依赖：

```bash
python -m pip install .
```

也可以构建仓库提供的 Docker 镜像：

```bash
docker build -t media-factory .
```

### 4. 配置 MCP Server

每条工作流作为独立的 stdio MCP Server 运行：

| 服务 | 启动入口 | 职责 |
| --- | --- | --- |
| 财经常识文生图 | `python -m core.mcp.finance` | 财经常识文生图视频生产 |
| 语言学习 | `python -m core.mcp.language_learning` | 词汇视频生产 |
| 统一发布 | `python -m core.mcp.publishing` | 查询产物并发布到多个平台 |
| 抖音研究 | `python -m core.mcp.douyin_research` | 链接下载、转写和资料入库 |

MCP 客户端配置示例：

```json
{
  "mcpServers": {
    "media-factory-finance": {
      "command": "python",
      "args": ["-m", "core.mcp.finance"],
      "env": {
        "PYTHONPATH": "/absolute/path/to/media-factory",
        "PYTHONUTF8": "1",
        "DASHSCOPE_BUSINESS_LINE": "finance"
      }
    },
    "media-factory-language-learning": {
      "command": "python",
      "args": ["-m", "core.mcp.language_learning"],
      "env": {
        "PYTHONPATH": "/absolute/path/to/media-factory",
        "PYTHONUTF8": "1",
        "DASHSCOPE_BUSINESS_LINE": "language_learning"
      }
    },
    "media-factory-publishing": {
      "command": "python",
      "args": ["-m", "core.mcp.publishing"],
      "env": {
        "PYTHONPATH": "/absolute/path/to/media-factory",
        "PYTHONUTF8": "1"
      }
    }
  }
}
```

请将仓库路径和 Python 命令替换为当前机器上的绝对路径。

## 产物模型

本地成片按照业务线和北京时间计划发布日期保存：

```text
output/{business_line}/run-YYYYMMDD/
```

目录日期只代表计划发布日期，精确的预约发布时间单独使用带时区的时间戳保存。

中间产物保留在 `cache/`，便于诊断或恢复中断的流程。清理操作必须显式执行，发布完成后不会自动删除本地文件。

生产记录会保留产物来源：

- `local_mcp` 记录保存本地文件路径。
- `github_workflow` 记录只在 R2 交付成功后写入。
- 本地产物后续上传 R2 时，只补充原记录，不改变产物来源。

## 可靠性设计

- 话题占用避免并发生产重复内容。
- 发布记录避免向同一平台重复上传。
- 被放弃的来源稿件占用会自动过期。
- 耗时任务提供可持久化查询的任务状态。
- 每个平台成功后立即独立写入记录。
- 本地和云端生产的产物保留不同来源。
- 发布和本地文件清理相互独立。
- 单个日期或产品失败不会阻断整周任务。

这些约束让系统能够从部分失败中恢复，而不是把每次重试都当成一轮全新生产。

## 自动化工作流

仓库提供以下 GitHub Actions 工作流：

- 构建生产 Runner 镜像
- 生产下一周的语言学习和财经常识文生图内容
- 手动补发缺失的语言学习平台
- 部署发布管理面板

每周生产工作流在北京时间每周六 12:00 运行，依次处理下一周周一至周日的内容。

## 内部文档

- [财经 MCP](core/mcp/finance/finance.md)
- [语言学习 MCP](core/mcp/language_learning/language_learning.md)
- [统一发布 MCP](core/mcp/publishing/publishing.md)
- [运维说明](ops/README.md)

## 当前范围

Media Factory 是一个实际运行的内容生产系统，不是通用的拖拽式视频编辑器。

当前两条生产线分别包含语言学习和财经常识文生图业务规则。底层工具可以复用，但新增内容业务线仍需要定义自己的提示词、校验规则和 MCP 编排。

## 许可证

本仓库目前未声明开源许可证。在添加许可证前，应将源代码视为专有代码。
