# media-publisher

多平台视频发布工具。国内平台用本机浏览器登录态发布，YouTube、TikTok、Instagram、Facebook 走官方接口。没有图形界面，入口是命令行和 MCP。

## 致谢

感谢原作者 [@hanliang97](https://github.com/hanliang97)。本仓库参考了 [MatrixMedia](https://github.com/hanliang97/MatrixMedia)。

小红书视频发布流程移植自 [social-auto-upload v1.0.0-skills.2](https://github.com/dreammis/social-auto-upload/tree/7023053ec4c21bc85901cb5a66302f889ddc7fa9)，使用本工具的账号会话。上游许可证见 [MIT 许可证](./LICENSE.social-auto-upload)。

## 平台

| 平台 | 发布方式 | 登录 | 预约 |
| --- | --- | --- | --- |
| 抖音、快手、头条、视频号、百家号 | 浏览器 | 抖音、快手、头条、视频号可扫码 | 转为北京时间，由平台官方确认 |
| 哔哩哔哩 | 浏览器 | 使用已有登录态 | 只能立即发布 |
| 小红书 | 浏览器 | 创作者中心扫码，支持真实发布页预检 | 立即发布、保存草稿或平台预约发布 |
| YouTube、TikTok、Instagram、Facebook | 官方接口 | 系统浏览器授权 | 把带时区的时间交给官方接口 |

账号放在 `data/finance`、`data/korean`、`data/chinese`。浏览器 Cookie 在对应账号组的 `Partitions` 里，海外平台凭据在该账号组的环境变量里。

统一发布在 `python/publishing`，官方接口在 `python/platform_api`。

## 命令行

参数里带 `cli` 即进入命令行。说明见 [docs/cli.md](./docs/cli.md)。

| 子命令 | 作用 |
| --- | --- |
| `cli login` | 扫码，或打开系统浏览器完成海外平台授权 |
| `cli publish` | 发布一条视频 |
| `cli accounts` | 查看账号和登录态 |

```bash
media-publisher cli login -p dy --phone 13800138000
media-publisher cli publish -p dy --phone 13800138000 -f ./video.mp4 -t "标题"
media-publisher cli login -p xhs --phone korean
media-publisher cli accounts -p xhs --phone korean --json
```

开发时在项目根目录执行：

```bash
electron . cli accounts --help
```

退出码：`0` 成功，`1` 异常，`2` 参数错误，`3` 登录或上传失败。

## MCP

`mcp/` 把登录和发布暴露给支持 MCP 的工具。发布可以一次提交多条视频、多个平台，再用任务轮询取结果。说明见 [docs/mcp.md](./docs/mcp.md)。

```bash
cd mcp && npm install && npm run build
```

## 小红书账号与内容核对

发布前使用 `cli accounts -p xhs --phone <账号组>` 检查真实视频发布页。先核对素材和创作声明，含 AI 合成内容时如实标注。需要人工审核可保存草稿，由账号所有者在创作者中心检查后提交。

发布窗口保持可见。出现安全验证、频率限制或疑似自动化提示时暂停，批量任务遇到小红书失败后停止提交后续小红书作品。提交结果不明时先查作品管理。发布页验证仅确认当前会话可打开上传表单，平台审核与账号处置以创作者中心为准。参见 [上游小红书说明](https://github.com/dreammis/social-auto-upload/blob/7023053ec4c21bc85901cb5a66302f889ddc7fa9/skills/xiaohongshu-upload/SKILL.md) 和 [上游风控反馈](https://github.com/dreammis/social-auto-upload/issues/289)。

## 开发

需要 Node.js 20。

```bash
yarn
yarn build:dir
```

若启动时报 `require('electron')` 得到字符串，先关掉环境变量 `ELECTRON_RUN_AS_NODE`。

## 使用声明

本项目只用于合法合规的发布。请遵守各平台协议和当地法律，不要用于作弊、侵权或刷量。账号、Cookie 和素材由使用者自行保管。

## 许可

[GPL-2.0-only](./LICENSE)

## 头条三种独立发布

财经生产清单包含完整正文、约150字的 `micro_summary`、三张插图计划和封面路径。三个命令互不触发，可分别运行：

```bash
electron . cli publish-toutiao-video --phone finance --file manifest.json
electron . cli publish-toutiao-article --phone finance --file manifest.json
electron . cli publish-toutiao-micro --phone finance --file manifest.json
```

视频使用16:9封面并关闭生成图文；文章使用完整正文及三张插图、4:3封面，开启头条首发并关闭同时发布微头条；微头条使用定稿摘要和一张4:3封面。正文、图片与摘要均从清单读取，不在发布时生成内容。每个命令等待平台提交成功后保存独立回执；`--help` 查看参数。当前三条专用命令立即发布，预约视频使用原有 `cli publish`。

## B站发布参数

B站扫码登录使用publisher独立的账号分区，二维码从固定XPath `//img[@alt='Scan me!']` 读取；登录完成后必须重新打开真实投稿页验证，Cookie存在不能代替预检。

```bash
electron . cli login -p blbl --phone finance --save-qr-png bilibili-login.png
electron . cli publish -p blbl --phone finance --file video.mp4 --title "视频标题" --category "知识" --cover cover.png --widescreen-cover cover-widescreen.png --ai-chapters --creative-statement ai_generated
```

`--category` 可选，不传则保留平台默认分区。财经业务明确传知识。`--cover` 上传4:3首页推荐封面，`--widescreen-cover` 上传16:9个人空间封面，`--ai-chapters` 使用平台智能章节；`--publish-at "YYYY-MM-DD HH:mm:ss"` 使用平台真实定时发布。投稿成功须同时取得平台成功响应、稿件ID并在稿件管理页定位本次标题；预约还核对提交的发布时间。失败返回具体错误并保存发布页诊断信息。
# 独立 CLI 与 MCP 配置

Publisher 不读取 Factory 的数据库或接口。账号目录为 `data/accounts.json`，凭据为 `data/credentials.json`；凭据文件也可由 `PUBLISHING_CREDENTIALS_FILE` 或 `PUBLISHING_CREDENTIALS_JSON` 明确指定。Docker 使用容器内路径，不推断调用方仓库结构。启动工作目录为 Publisher 根目录，或设置 `MEDIA_PUBLISHER_DIR`。

账号组使用小写字母开头、至多64位的字母数字下划线标识，登录和发布均显式传 `--phone <账号组>`。使用 `--partition` 仍须指定账号组，会话位于 `data/<账号组>/Partitions`，既有三个账号组目录保持不变。

配置文件格式示例：

```json
{"groups":[{"code":"demo","name":"demo","enabled":true}],"members":[]}
```

官方账号 members 提供 `group_code`、`platform`、`account_key`、`connector_account_id`、`platform_account_id`、`credential_ref`，可选 `display_name`、`account_ref`、`enabled`。凭据正文只存 credentials 文件，以 credential_ref 为键。通过 `python -m publishing configure-accounts` 的标准输入完整保存目录；MCP 对应 `configure_accounts`。替换配置前应自行保留备份。浏览器账号可通过该组独立登录建立会话，官方账号环境变量使用账号自己的大写前缀，不使用业务专属前缀映射。

Factory 首次迁移使用 Factory 自己的 `ops/publishing/export_publisher_accounts.py`，脚本保留现有 Publisher 账号及原文件备份。Publisher 本身不调用此迁移脚本；Factory 日常查询不会覆盖 Publisher 目录。

独立发布入口：普通视频用 `cli publish -p <平台> --phone <组> --file <视频> --title <标题>`；头条另有 `publish-toutiao-video`、`publish-toutiao-article`、`publish-toutiao-micro`，均可接收自行构造的发布请求 JSON，无需生产系统产物。文章不支持封面；微头条只接受一个 `micro_image_path` 字符串，不接受图片数组。文章和微头条专用入口不支持草稿；微头条当前仅支持立即发布。

MCP `start_publish` 的 items 支持 `content_type=video|article|micro`，后两者选择 toutiao 并传 `request_path` 指向同样的独立请求 JSON。视频可传封面、分区、智能章节、原创、生成图文等选项；YouTube 显式传 `youtube_options`，包含 privacy_status、category_id、language、made_for_kids。官方 CLI 同样提供 `--privacy`、`--category-id`、`--language`、`--made-for-kids`、`--thumbnail-path`。

`MEDIA_PUBLISHER_EXECUTABLE` 指定已安装 CLI，`MEDIA_PUBLISHER_PYTHON` 指定 Python；各层默认执行时限统一为14520秒，通过 `MEDIA_PUBLISHER_TIMEOUT_SECONDS` 配置。预约接受带时区 ISO 时间，浏览器平台按北京时间转换，这是当前平台执行适配约定。
