---
name: publish-finance
description: 发布或预约指定计划日期的财经内容，默认覆盖视频、YouTube Shorts、头条文章和微头条，支持按平台及内容类型限定范围。
---

# 发布财经成片

业务线、内容类型及默认账号组均为 `finance`。日期有歧义时询问；指定标题时先预览定位 `production_id`。仅制作或预览的请求不运行发布命令，不触发发布 Action。

## 默认发布范围

用户要求“发布某天财经”“发布本地已有财经”且未限定类型时，对本次启用的平台执行以下全部内容。指定平台时只保留该平台；指定“只发视频”“只发长视频”等类型时遵守用户限定。

| 目标平台 | 默认执行内容 | 执行入口 |
| --- | --- | --- |
| 抖音、快手、视频号、B站 | 本期长视频 | 统一发布 MCP |
| YouTube | 长视频、Shorts各一条 | 长视频用统一发布 MCP 或 `--variant long`，Shorts单独用 `--variant short` |
| 头条 | 视频、文章、微头条各一条 | 视频用统一发布 MCP 或视频 CLI，文章和微头条分别用对应 CLI |

统一发布 MCP 只处理视频，不会自动发布 Shorts、文章或微头条。同一内容的两种入口只选一个，已发布的长视频不再次调用长视频入口。

## 发布流程

1. 用 `publishing_list_account_groups` 确认本次平台范围，按发布 MCP 规则完成真实登录预检；只检查本次目标账号。全部通过后提示“**全部账号已登录，开始发布**”并继续。
2. 用 `publishing_preview` 核对视频产物与记录，同时核对 Shorts、文章、微头条各自的产物与独立回执，列出“平台、内容类型、production_id、执行入口、当前状态”清单。跳过已发布或已预约项，缺少产物的类型明确标为待处理。
3. 视频多日用 `publishing_start_batch`，单日用 `publishing_start_publish`；随后按清单分别执行 Shorts、头条文章、微头条的独立入口，不因视频任务完成而结束。预约时间传带时区的 ISO 8601。用户只要求首日时仅提交首日。
4. 单日轮询原任务；批次用 `publishing_batch_status`，需监控时每3分钟读摘要。登录、验证码和平台限制立即提示；结果不明先查回执及作品管理页，再决定是否重试。
5. 完成前逐项核对清单：每个目标内容必须有成功或预约回执，或明确的失败、缺少产物、待用户处理原因。按“平台＋内容类型”报告结果；YouTube长视频成功不能代表Shorts成功，头条视频成功不能代表文章和微头条成功。

## 预约时间

- 财经每天一篇，默认使用分片1，预约北京时间18:00；GitHub Actions同样每天只生产这一篇，并由同篇生成Shorts、文章和微头条。
- 18:00已过时，询问立即发布或改约；用户明确要求立即发布时直接执行。指定其他时刻时只安排一篇。
- 头条滚动7天窗口的最远一天，使用页面最晚可选小时，通常17:00；确认尚未提交且18:00不可选后，仅调整该条。

## 平台封面与附加操作

封面缺失时从本期 R2 恢复，保持图片完整内容。

| 平台 | 封面 | 附加操作 |
| --- | --- | --- |
| 抖音 | `cover.png`（4:3）、`cover-portrait.png`（3:4） | 启用智能章节，等待推荐接口返回并保存 |
| 快手 | `cover-portrait.png`（3:4） | 必须上传竖版封面 |
| 视频号 | 个人主页卡片用3:4，分享卡片用4:3 | 分别上传两张封面；勾选并核验“声明原创”，未通过则停止发表 |
| YouTube 长视频 | `cover-widescreen.png`（16:9） | 使用本期专用说明和标签 |
| YouTube Shorts | 无独立封面 | 直接使用切片成品 |
| B站 | 首页推荐用4:3，个人空间用16:9 | 两张分别上传，启用智能章节 |

## 头条：视频、文章、微头条

三类内容独立发布、独立预检和记录，互不触发。默认发布财经时三类都执行；用户限定类型时只执行对应项。在 `integrations/media-publisher` 构建后执行，`--file` 指向财经生产清单：

```powershell
.\node_modules\.bin\electron.cmd . cli publish-toutiao-video --phone finance --file <manifest.json>
.\node_modules\.bin\electron.cmd . cli publish-toutiao-article --phone finance --file <manifest.json>
.\node_modules\.bin\electron.cmd . cli publish-toutiao-micro --phone finance --file <manifest.json>
```

| 类型 | 内容与设置 | 独立回执 |
| --- | --- | --- |
| 视频 | 16:9封面，关闭“生成图文” | `toutiao-video-publication.json` |
| 文章 | 完整正文、三张预制插图、4:3封面；勾选“头条首发”，关闭“同时发布微头条” | `toutiao-article-publication.json` |
| 微头条 | 定稿 `micro_summary`（约150字），仅配4:3封面 | `toutiao-micro-publication.json` |

插图由生产代码将正文对应镜头分三等份，每份随机选一张并保存选择结果。清单、正文、摘要、插图及封面随生产上传 R2，GitHub 同样生成；跨机器先恢复所需资产并更新清单路径，文章和微头条无需恢复视频。

## YouTube：长视频与 Shorts

使用原频道“大鹅说”，账号 `finance_youtube`，凭据引用 `youtube_finance`，发布前验证实际授权。本地或 GitHub 生产均需分别执行长视频和 Shorts；下列独立入口读取指定日期产物，不触发其他平台。长视频已由统一发布 MCP 发出时，仅补执行 short：

```bash
python -m github_actions finance_youtube_account_check --publish-date YYYY-MM-DD
python -m github_actions finance_youtube_publish_day --publish-date YYYY-MM-DD --variant long
python -m github_actions finance_youtube_publish_day --publish-date YYYY-MM-DD --variant short
```

两类上传标题均为完整标题加原有4个标签，描述使用定稿 YouTube 说明及10个专用标签；画面固定标题只含标题正文。分别使用 `:youtube-long`、`:youtube-short` 标识及回执，失败仅重试对应类型。未来日期默认预约北京时间18:00。

## B站

- 财经账号独立分区为 `persist:finance哔哩哔哩`，使用 publisher 登录环境，不操作用户 Chrome。二维码 XPath 为 `//img[@alt='Scan me!']`；扫码跳转后继续打开真实投稿页核验。
- 明确传 `--category 知识`，CLI 未指定分区时保留平台默认值。标题用完整标题，简介复用 YouTube 说明及10个专用标签，标签控件填写原有四个标签。
- `--cover` 传4:3封面，`--widescreen-cover` 传16:9封面；启用 `--ai-chapters`，等待平台生成并保存。
- 用 `--publish-at` 执行真实预约。成功须取得投稿接口成功响应及稿件ID，并在稿件管理页定位作品；预约另核对请求中的实际发布时间。
