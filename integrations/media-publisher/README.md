# media-publisher

独立的多平台发布 CLI 和 MCP。提供账号组配置、扫码与官方授权、真实登录状态检查、视频发布、头条文章、单图微头条、平台官方预约及发布回执。调用者提供文案、图片、视频和发布选项，Publisher 不生成内容。

## 安装与运行

需要 Node.js 20 和 Python 3.10 以上。在 Publisher 根目录执行，Python 使用自己的虚拟环境：

```powershell
npm install
npm run build:dir
python -m pip install ./python
```

已有可执行文件使用 `media-publisher cli <命令>`；源码运行使用 `npx electron . cli <命令>`，Windows 也可使用 `./node_modules/.bin/electron.cmd . cli <命令>`。不要设置 `ELECTRON_RUN_AS_NODE`。

Python 命令在 Publisher 根目录运行，或设置 `MEDIA_PUBLISHER_DIR`。示例中的账号、路径和日期须替换为实际值，预约时间必须在未来。

## 平台

| 平台 | 平台码 | 发布与授权方式 | 视频官方预约 |
| --- | --- | --- | --- |
| 抖音 | dy / douyin | 浏览器扫码 | 支持 |
| 快手 | ks / kuaishou | 浏览器扫码 | 支持 |
| 视频号 | sph / wechat_channels | 浏览器扫码 | 支持 |
| 哔哩哔哩 | blbl / bilibili | 浏览器扫码 | 支持 |
| 头条 | tt / toutiao | 浏览器扫码 | 支持 |
| 百家号 | bjh / baijiahao | 使用已有浏览器会话 | 支持 |
| 小红书 | xhs / xiaohongshu | 创作者中心扫码 | 支持 |
| YouTube | youtube / yt / ytb | Google 官方 API 与 OAuth | 支持 |
| TikTok | tiktok / tk | Zernio API 与授权 | 支持 |
| Instagram | instagram / ig / ins | Zernio API 与授权 | 支持 |
| Facebook | facebook / fb | Zernio API 与授权 | 支持 |

头条文章支持立即发布和官方预约，固定无封面；微头条只接受一张图片，只支持立即发布。可预约日期和账号权限由平台决定。

## 账号组与凭据

账号组以小写字母开头，由字母、数字、下划线组成，最长64位，例如 `demo`、`travel_cn`。浏览器登录、发布传 `--phone <账号组>`；即使指定 `--partition` 也须传账号组。

| 路径 | 内容 |
| --- | --- |
| data/accounts.json | 账号组、官方账号和凭据引用 |
| data/credentials.json | 官方接口凭据正文 |
| data/账号组/Partitions/ | 浏览器 Cookie 和会话 |
| data/账号组/.env | 官方登录命令写入的环境变量凭据 |
| data/账号组/runtime/ | Electron 运行数据 |

账号配置示例 `accounts.json`：

```json
{
  "groups": [{"code":"demo","name":"demo","enabled":true}],
  "members": [{
    "group_code":"demo", "platform":"youtube", "account_key":"demo_youtube",
    "connector_account_id":"实际频道ID", "platform_account_id":"实际频道ID",
    "credential_ref":"demo_google", "display_name":"频道名称", "enabled":true
  }]
}
```

浏览器账号组可以先使用空 members 数组，再扫码建立会话。官方账号 members 提供上述标识和凭据引用，可另传 account_ref。凭据文件以 credential_ref 为键：

```json
{
  "demo_google": {"client_id":"客户端ID","client_secret":"客户端密钥","refresh_token":"刷新令牌"},
  "demo_social": {"api_key":"Zernio密钥"}
}
```

官方账号也可使用环境变量：YouTube 为 `<账号大写前缀>_YOUTUBE_CHANNEL_ID`、`<前缀>_YOUTUBE_REFRESH_TOKEN`、`YOUTUBE_OAUTH_CLIENT_ID`、`YOUTUBE_OAUTH_CLIENT_SECRET`；TikTok 为 `<前缀>_TIKTOK_ACCOUNT_ID` 和 `ZERNIO_API_KEY`；Instagram、Facebook 分别为 `<前缀>_INSTAGRAM_ACCOUNT_ID`、`<前缀>_FACEBOOK_ACCOUNT_ID`，密钥变量均为 `zernio_api_key_meta`。

## CLI 命令目录

| 命令 | 作用 |
| --- | --- |
| media-publisher cli login | 扫码或官方授权 |
| media-publisher cli accounts | 查询和验证账号 |
| media-publisher cli publish | 单视频或浏览器目录批量发布 |
| media-publisher cli publish-toutiao-video | 独立发布头条视频 |
| media-publisher cli publish-toutiao-article | 独立发布无封面文章 |
| media-publisher cli publish-toutiao-micro | 独立发布单图微头条 |
| media-publisher cli douyin-creator-works | 读取抖音公开作品及指标 |
| python -m publishing configure-accounts | 从标准输入完整保存本地账号目录 |
| python -m publishing groups | 列出账号组 |
| python -m publishing accounts | 查询组内账号，支持 --group、--platform |
| python -m publishing platform 平台码 | 查询平台能力 |
| python -m publishing publish | 从标准输入读取统一发布 JSON |
| python -m platform_api.cli accounts --group 账号组 | 查询官方接口账号 |
| python -m platform_api.cli publish | 直接执行官方平台发布 |
| python -m platform_api.oauth | YouTube OAuth 辅助命令 |

常规命令支持 `--help`；抖音作品读取使用下文固定参数格式。

### 创建与查询账号组

```powershell
Get-Content -Raw -Encoding utf8 ./accounts.json | python -m publishing configure-accounts
python -m publishing groups
python -m publishing accounts --group demo --platform youtube
python -m publishing platform douyin
```

configure-accounts 完整替换目录，新增时也须保留其他组和成员。groups 合并配置中的启用组与包含 Partitions 或 .env 的本地目录。账号组存在不代表已登录。

### 登录

```powershell
media-publisher cli login -p dy --phone demo --save-qr-png ./login.png
media-publisher cli login -p blbl --phone demo --save-qr-png ./bilibili-login.png
media-publisher cli login -p youtube --phone demo --client-secret ./client_secret.json
media-publisher cli login -p tiktok --phone demo --api-key <Zernio密钥> --profile <资料ID>
```

| 参数 | 说明 |
| --- | --- |
| -p、--platform | 平台码，浏览器扫码支持 dy、sph、ks、tt、xhs、blbl |
| --phone | 账号组 |
| --partition | 完整浏览器分区，仍须提供账号组 |
| --show、--hide | 请求显示或隐藏窗口，实际行为由平台决定 |
| --no-terminal-qr | 不向终端输出二维码 |
| --save-qr-png 路径 | 保存二维码图片 |
| --timeout-sec 秒数 | 登录等待上限，默认900秒 |
| --force | 刷新旧登录会话 |
| --puppeteer-headless | 抖音使用系统 Chrome/Chromium 无头登录 |
| --client-secret 文件 | Google OAuth 客户端 JSON |
| --api-key 密钥 | Zernio API Key |
| --profile ID | Zernio 资料 ID |
| -h、--help | 帮助 |

无头抖音可通过 PUPPETEER_EXECUTABLE_PATH 指定浏览器，无交互终端时使用二维码文件。Linux 无图形会话可通过虚拟显示运行 Electron。

### 账号预检

```powershell
media-publisher cli accounts --phone demo --platforms dy,ks,sph --json
media-publisher cli accounts --phone demo -p blbl --json
media-publisher cli accounts --phone demo --official --json
```

参数为 `--phone`、`-p/--platform`、`--platforms`（逗号分隔）、`--official`、`--logged-in`、`--logged-out`、`--json`、`-h/--help`。platforms 不能和 platform 或 official 同用；logged-in 和 logged-out 互斥。

浏览器检查打开真实发布页，不上传素材。Electron 入口读取系统文档目录 `media-publisher/data/account/*.json`，并补充当前组的会话分区；Python 账号查询读取 Publisher 本地目录及授权。Cookie 存在不能代替真实预检。

## 浏览器视频发布

```powershell
media-publisher cli publish -p dy --phone demo --file D:/media/video.mp4 --title "视频标题" --tags "成长 职场"
media-publisher cli publish -p dy --phone demo --file D:/media/video.mp4 --title "视频标题" --cover D:/media/cover.png --portrait-cover D:/media/portrait.png --ai-chapters --creative-statement ai_generated
media-publisher cli publish -p sph --phone demo --file D:/media/video.mp4 --title "视频标题" --bt2 "每日认知分享" --declare-original
media-publisher cli publish -p blbl --phone demo --file D:/media/video.mp4 --title "视频标题" --category "知识" --cover D:/media/cover.png --widescreen-cover D:/media/widescreen.png --ai-chapters
```

| 参数 | 说明及默认行为 |
| --- | --- |
| -p、--platform | 平台，必填 |
| --phone | 账号组，必填 |
| --partition | 完整分区，例如 persist:demo抖音 |
| -f、--file | 本地视频或 HTTP(S) 视频 URL，远程文件先下载，任务结束清理临时文件 |
| -t、--title | 单文件标题，必填 |
| --description、--desc | 描述 |
| --tags、--bq | 空格分隔标签；抖音、快手、视频号补 #，B站、小红书按独立标签处理 |
| --bt2 | 视频号短标题，建议6–16字，不传为空 |
| --name、--book-name | 任务名称，默认取文件名 |
| --creative-statement、--cs | 创作声明，默认 none |
| --cover 路径 | 自定义封面；抖音和B站首页4:3、快手3:4、头条视频16:9、视频号分享卡片4:3 |
| --portrait-cover 路径 | 抖音或视频号3:4封面 |
| --widescreen-cover 路径 | B站16:9个人空间封面 |
| --category 分区 | B站分区，不传保留页面默认值 |
| --ai-chapters | 抖音、B站智能章节，不传不主动启用 |
| --declare-original | 视频号原创声明，不传不主动勾选 |
| --generate-image-text true/false | 头条生成图文，不传不主动修改页面状态 |
| --system-cover-index 整数 | 头条系统候选封面索引，从0开始 |
| --publish-at 时间 | 北京时间，格式 YYYY-MM-DD HH:mm:ss；不传立即发布 |
| --draft | 保存草稿，与预约互斥 |
| --show | 显示抖音、快手、视频号、B站或头条执行窗口，完成后保留现场 |
| --no-close-window | 发布结束不自动关窗 |
| --sph-product-id 编号 | 视频号挂载商品 |
| --sph-link-type none/product | 视频号链接类型 |
| --sph-link-value 编号 | 视频号商品编号，单独传入时按商品处理 |
| --dir 目录、--config/--xlsx XLSX | 目录批量模式，须配对，不能同时传 file |
| -h、--help | 帮助 |

创作声明取值为 none、ai_generated、fiction、marketing、personal_opinion、repost、self_made_no_repost，最后一项仅用于B站。章节、原创、分区、封面、预约均为可选项，仅对应平台消费。未传参数不保证平台页面默认关闭该选项。

```powershell
media-publisher cli publish -p tt --phone demo --file D:/media/video.mp4 --title "视频标题" --generate-image-text false
media-publisher cli publish -p dy --phone demo --file D:/media/video.mp4 --title "视频标题" --publish-at "2030-01-10 18:00:00"
media-publisher cli publish -p xhs --phone demo --file D:/media/video.mp4 --title "视频标题" --draft
media-publisher cli publish -p dy --phone demo --dir D:/media/videos --config D:/media/batch.xlsx
```

XLSX 使用首个工作表，列为文件名、标题、标签、描述、短标题、创作声明；文件名和标题必填。标签用逗号分隔。按完整文件名或不含扩展名的文件名匹配素材。

## 官方平台视频发布

```powershell
media-publisher cli publish -p youtube --phone demo --account-id demo_youtube --file D:/media/video.mp4 --title "视频标题" --description "视频描述" --privacy public --category-id 24 --language zh --thumbnail-path D:/media/cover.png --publication-id video-001
media-publisher cli publish -p tiktok --phone demo --account-id <账号ID> --video-url https://example.com/video.mp4 --description "视频描述"
media-publisher cli publish -p instagram --phone demo --account-id <账号ID> --video-url https://example.com/video.mp4 --description "视频描述"
media-publisher cli publish -p facebook --phone demo --account-id <账号ID> --video-url https://example.com/video.mp4 --title "视频标题" --description "视频描述"
```

官方和浏览器发布使用不同的参数解析入口，不混用参数：

| 参数 | 说明 |
| --- | --- |
| -p、--platform | 官方平台，必填 |
| --phone | 账号组，必填 |
| --account-id | connector_account_id 或配置中的 account_key，必填 |
| -f、--file | YouTube 本地视频 |
| --video-url | TikTok、Instagram、Facebook 可下载的公网视频地址 |
| --title、--description | 标题和描述 |
| --privacy | YouTube private、unlisted、public，CLI默认 public |
| --category-id | YouTube 分类 ID，默认24 |
| --language | YouTube 语言，默认 zh |
| --made-for-kids | YouTube 儿童内容声明，不传为 false |
| --thumbnail-path | YouTube 封面文件 |
| --publication-id | YouTube 去重标识，与文件内容共同识别上传 |
| --publish-at | 带时区的未来 ISO 8601，例如 2030-01-10T18:00:00+08:00 |
| -h、--help | 帮助 |

可直接用 `python -m platform_api.cli publish` 替换上述官方发布前缀。YouTube 使用 Google API；其他三个平台使用 Zernio，并要求公网素材地址。

## 头条视频、文章、微头条

```powershell
media-publisher cli publish-toutiao-video --phone demo --file D:/media/video-request.json
media-publisher cli publish-toutiao-article --phone demo --file D:/media/article-request.json
media-publisher cli publish-toutiao-micro --phone demo --file D:/media/micro-request.json
```

三个命令互不触发。file 指向执行请求 JSON，phone 指定账号组，可传 show、no-close-window 等共用浏览器选项。视频和文章可传北京时间 publish-at；微头条拒绝预约。三种专用命令均拒绝 draft。使用 `--help` 查看入口用法。

公共必填字段为 title、description、tags、creative_statement、output_dir、publish_options。output_dir 须为已存在且可写的目录，素材建议使用绝对路径。

视频请求：

```json
{
  "title":"视频标题", "description":"视频描述", "tags":"", "creative_statement":"none",
  "output_dir":"D:/media/results", "video_path":"D:/media/video.mp4", "cover_path":"D:/media/cover-16x9.png",
  "publish_options":{"generateImageText":false}
}
```

文章请求：

```json
{
  "title":"文章标题", "description":"文章描述", "tags":"", "creative_statement":"none",
  "output_dir":"D:/media/results", "toutiao_article_path":"D:/media/article.json",
  "publish_options":{"quote_ai":false,"first_publish":false,"sync_micro":false}
}
```

article.json 正文格式，图片相对于该文件所在目录：

```json
{"title":"文章标题","paragraphs":[{"text":"第一段正文"},{"text":"第二段正文","image":"illustration.png"}]}
```

实际文章标题由正文 JSON 填写，建议与请求 title 一致。quote_ai、first_publish、sync_micro 必须是明确的布尔值。文章固定无封面，拒绝 cover_path 及 CLI 封面参数；正文可含插图。

单图微头条请求：

```json
{
  "title":"微头条任务标题", "description":"任务描述", "tags":"", "creative_statement":"none",
  "output_dir":"D:/media/results", "micro_text":"完整正文和话题 #成长#",
  "micro_image_path":"D:/media/picture.png", "publish_options":{"quote_ai":false}
}
```

正文直接使用 micro_text；图片必须是一个非空路径字符串，不接受数组。回执分别保存到 output_dir 下的 toutiao-video-publication.json、toutiao-article-publication.json、toutiao-micro-publication.json。

## 统一 JSON 批次发布

```powershell
Get-Content -Raw -Encoding utf8 ./publish-request.json | python -m publishing publish
```

```json
{
  "account_group":"demo", "platforms":["douyin"], "publish_mode":"immediate", "publish_at":"now",
  "items":[{"title":"视频标题","file":"D:/media/video.mp4","description":"视频描述","tags":"成长 职场","ai_chapters":false,"creative_statement":"none"}]
}
```

items 与 platforms 组合展开；也可用顶层 targets 数组逐条提供 platform 和其余条目字段。每条可指定 account_key，同平台多官方账号可明确选择，否则按账号路由展开。

| 条目字段 | 用途 |
| --- | --- |
| title | 必填标题 |
| content_type、request_path | 默认 video；article、micro 仅用于 toutiao，request_path 指向前述独立请求 JSON |
| account_key | 指定账号标识 |
| file、video_url | 浏览器和YouTube使用本地视频，其他官方平台使用公网地址 |
| description、tags、bt2 | 描述、标签、视频号短标题 |
| thumbnail_path、portrait_thumbnail_path、widescreen_thumbnail_path | 各比例封面 |
| ai_chapters、declare_original | 智能章节、视频号原创布尔选项 |
| generate_image_text、system_cover_index | 头条视频图文选项及系统封面索引 |
| category、creative_statement | B站分区、创作声明 |
| draft、sph_product_id | 浏览器草稿、视频号商品编号 |
| publication_id、client_ref | YouTube 去重标识、调用方跟踪标识 |
| youtube_options | YouTube 必填对象，包含 privacy_status、category_id、language、made_for_kids |

顶层 immediate 配合 now；预约使用 scheduled 和带时区的未来 ISO 时间。publish_at_by_platform 按所选平台覆盖时间，值为 now 或带时区 ISO 时间。浏览器统一转成北京时间；不支持循环排期。

结果包含 status、published、failed 及逐条回执。执行中单条失败继续其他目标；小红书失败后暂停本批剩余小红书作品。请求格式、必要素材字段或时间无效时，执行前返回参数错误。

## 抖音作品读取

```text
media-publisher cli douyin-creator-works --phone <账号组> <接口配置JSON字符串>
```

配置提供 listPath、metricsPath、listParams、metricsFields、metricsHeaders；listParams 包含初始 max_cursor 和接口要求的其他参数。工具使用账号会话在创作者中心同源请求，分页筛选公开作品，逐条读取指标，返回 works 和 metrics。调用者提供实际接口路径、字段及请求头。

## YouTube OAuth 辅助入口

```powershell
python -m platform_api.oauth --client-secret ./client_secret.json --output ./google-token.json
python -m platform_api.oauth --inspect-token ./google-token.json
python -m platform_api.oauth --configure-env ./data/demo/.env --token-file ./google-token.json --account demo --channel-id <频道ID> --channel-title "频道名称"
```

参数包含 --client-secret、--output、--port（默认18765）、--callback（完整授权回调 URL）、--inspect-token、--configure-env、--token-file、--account（默认 language_learning）、--channel-id、--channel-title。常规授权使用 `cli login -p youtube`。

## MCP

```powershell
cd mcp
npm install
npm run build
node dist/index.js
```

标准 stdio 配置示例：

```json
{
  "mcpServers": {
    "media-publisher": {
      "command":"node", "args":["D:/media-publisher/mcp/dist/index.js"],
      "env":{"MEDIA_PUBLISHER_DIR":"D:/media-publisher","MEDIA_PUBLISHER_PYTHON":"D:/media-publisher/.venv/Scripts/python.exe"}
    }
  }
}
```

| 工具 | 输入与用途 |
| --- | --- |
| configure_accounts | groups、members，完整保存账号目录 |
| list_accounts | 可选 account_group、platform，查询账号 |
| login | platform、account_group，可选 timeoutSec、force，返回二维码或授权信息 |
| login_status | login_id，查询登录任务 |
| start_publish | account_group、platforms、items 和时间参数，与统一 JSON 发布字段一致，返回 task_path |
| poll_task | task_path，查询发布状态及最终回执 |

发布任务使用进程内队列，保持同一 MCP 进程运行，轮询原任务，不重复提交。宿主需要实际加载配置并发现工具。

## 环境变量与外部服务

| 环境变量 | 用途 |
| --- | --- |
| MEDIA_PUBLISHER_DIR | Publisher 根目录 |
| MEDIA_PUBLISHER_EXECUTABLE | 已安装的 Publisher 可执行文件 |
| MEDIA_PUBLISHER_PYTHON | Python 可执行文件 |
| PUBLISHING_CREDENTIALS_FILE | 凭据 JSON 路径，默认 data/credentials.json |
| PUBLISHING_CREDENTIALS_JSON | 凭据 JSON 正文，优先于文件 |
| MEDIA_PUBLISHER_TIMEOUT_SECONDS | Python 执行器及 MCP 默认上限14520秒；Electron内部上传上限4小时 |
| PUPPETEER_EXECUTABLE_PATH | 无头抖音使用的 Chrome/Chromium 路径 |
| YOUTUBE_FALLBACK_PROXY | YouTube 超时后的 HTTP 代理，默认本机7897，容器内 host.docker.internal:7897；空值禁用回退 |
| MEDIA_PUBLISHER_DISABLE_TELEMETRY | 非空时关闭启动统计 |
| MEDIA_PUBLISHER_GIST_ID、MEDIA_PUBLISHER_GIST_TOKEN | 可选 GitHub Gist 启动统计配置 |

浏览器平台访问官方网页，YouTube 访问 Google API，TikTok、Instagram、Facebook 访问 Zernio。启动统计仅在 Gist ID、Token 齐全且未禁用时调用 GitHub API；Token 也可从 ~/.media-publisher/gist-token 读取，~/.media-publisher/no-telemetry 文件可关闭统计。浏览器代理由账号代理配置提供。凭据、会话及含密钥的配置不要提交版本库。

## 结果与回执

浏览器单文件退出码：0成功、1异常、2参数错误、3失败、4已保存草稿需核对；目录批量为0全部成功、1部分失败、2全部失败。官方入口失败返回非零。Python统一批次须同时检查 JSON 的 status、published、failed，不能只看退出码。

发布前验证目标账号的真实登录或授权。出现登录、验证码、平台限制时处理对应问题；提交结果不明时先查回执和作品管理页。小红书执行窗口保持可见，平台验证需人工处理。官方预约以平台确认回执为准。

## 致谢与许可

感谢原作者 [@hanliang97](https://github.com/hanliang97)，项目参考 [MatrixMedia](https://github.com/hanliang97/MatrixMedia)。小红书流程参考 [social-auto-upload](https://github.com/dreammis/social-auto-upload/tree/7023053ec4c21bc85901cb5a66302f889ddc7fa9)，上游许可见 [MIT 许可证](./LICENSE.social-auto-upload)。本项目使用 [GPL-2.0-only](./LICENSE)。
