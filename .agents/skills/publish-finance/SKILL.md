---
name: publish-finance
description: 发布或预约指定计划日期的财经成片。
---

# 发布财经成片

业务线和内容类型用 `finance`，默认账号组同名。计划日期有歧义时询问；指定标题用预览定位 `production_id`。

- 默认北京时间第一篇 14:00、第二篇 18:00。只有一篇排 18:00；14:00 已过或用户只指定 18:00 时仅排一篇，优先第二篇。其他指定时刻也只排一篇。默认时段均已过时询问立即发布或改约。
- 头条滚动 7 天预约窗口的最远一天，第二篇用页面最晚可选小时，通常为 17:00。确认未提交且时段不可选时，只调整该条时间。

1. 用 `publishing_list_account_groups` 选择启用平台，按用户要求限缩范围。按发布 MCP 的规则完成真实登录预检及提示后再继续。
2. 用 `publishing_preview` 核对产物与重复记录，跳过已发布或已预约项。
3. 多日用 `publishing_start_batch`，单日诊断用 `publishing_start_publish`。指定预约时刻用带时区 ISO 8601。用户只要求首日时仅提交首日。
4. 单日轮询同一任务；批次按需查 `publishing_batch_status`，需要监控时每 3 分钟读摘要。登录、验证码或平台限制立即提示，结果不明先查回执。按平台报告结果。

财经抖音发布默认启用平台智能章节：打开视频章节，点击智能生成，等待推荐接口返回章节后保存。必须上传本期横竖自定义封面 `cover.png` 和 `cover-portrait.png`；本地缺失时从该期 R2 产物恢复。发布器自动适配抖音 4:3 横封面与 3:4 竖封面，保留图片完整内容。

封面固定生成三种比例：`cover.png` 为 4:3，`cover-portrait.png` 为 3:4，`cover-widescreen.png` 为 16:9。抖音使用前两张，快手必须上传3:4竖版封面，视频号必须分别上传3:4个人主页卡片和4:3分享卡片封面，YouTube 长视频使用16:9宽屏封面。

## 头条独立发布

头条视频、文章、微头条分别执行，互不触发，不检查其他类型是否已发布。每次仅预检本次使用的头条账号，仍须执行上面的真实登录检查。

在 `integrations/media-publisher` 构建后，分别使用以下命令，`--file` 指向财经生产清单：

```powershell
.\node_modules\.bin\electron.cmd . cli publish-toutiao-video --phone finance --file <manifest.json>
.\node_modules\.bin\electron.cmd . cli publish-toutiao-article --phone finance --file <manifest.json>
.\node_modules\.bin\electron.cmd . cli publish-toutiao-micro --phone finance --file <manifest.json>
```

- 视频上传16:9的 `cover-widescreen.png`，关闭“生成图文”。
- 文章保留清单中的完整正文，生产代码将正文对应镜头分三等份，每份随机选一张插图并保存选择结果；上传4:3的 `cover.png`，勾选“头条首发”，关闭“同时发布微头条”。
- 微头条使用与标题和标签同批定稿的 `micro_summary`，约150字，配图仅上传4:3的 `cover.png`。
- 生产清单、正文、摘要、三张插图和三种封面均随生产上传R2，GitHub Action同样生成这些资产。跨机器使用前，将所需资产恢复到本地并更新清单的本地路径；文章和微头条不需要恢复视频。
- 每个命令只保存自己的 `toutiao-video-publication.json`、`toutiao-article-publication.json` 或 `toutiao-micro-publication.json` 回执，提交结果不明时先核查对应作品管理页，避免重复发布。


## 财经YouTube

财经YouTube使用原频道“大鹅说”，账号标识 `finance_youtube`，凭据引用 `youtube_finance`。GitHub Actions生产完成后分别执行长视频和Shorts发布，不触发其他平台；长片上传16:9封面，Shorts不上传独立封面，两者沿用完整长标题和YouTube专用说明。各自使用 `:youtube-long`、`:youtube-short` 内容标识和回执，互不依赖；某类失败只重试该类。未来日期沿用第一篇14:00、第二篇18:00预约。正式发布前必须核验原频道实际授权。

```bash
python -m github_actions finance_youtube_account_check --publish-date YYYY-MM-DD
python -m github_actions finance_youtube_publish_day --publish-date YYYY-MM-DD --variant long
python -m github_actions finance_youtube_publish_day --publish-date YYYY-MM-DD --variant short
```

用户仅要求预览或明确不发布时，只运行生产，不运行发布命令、不触发发布Action。
