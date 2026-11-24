# 获取作者作品列表

实现在 `tools/list_author_works`。公开方法是 `list_author_works`、`resolve_author_profile` 和 `resolve_author_nickname`。

`list_author_works(profile_url, limit)` 读取作者主页最新作品，按发布时间从新到旧返回，最多 `limit` 条。每条包含 `aweme_id`、`work_url`、`title`、`author_name`、`sec_user_id`、`published_at`、`cover_url`、`is_video`。`work_url` 是 `https://www.douyin.com/video/{aweme_id}`，可交给 `download_video.download`。

主页没有返回 `webid` 时，作品请求保留空值，不生成随机浏览器标识。随机值与 Cookie 不匹配时，作品接口可能返回 HTTP 200 空响应。接口业务状态失败时明确报错，不能当作作者没有作品。

`resolve_author_profile(profile_text)` 把主页链接、`sec_user_id`，或整段「查看TA的更多作品」分享口令规范成 `sec_user_id` 和主页地址。口令里的 `v.douyin.com` 短链会先跟随跳转，落地页是 `iesdouyin.com/share/user/` 时取路径里的作者标识。

## 配置

作品还包含 `description`（平台原文，与抖音 `desc` 对应）和 `duration_seconds`（秒，缺失时为 0），供上层按需判断剧集与疑似合集，不在采集层判断业务归属。

翻页响应缺少作品列表、分页标志，或仍有下一页但游标无效时明确报错；不能把仅含 `status_code: 0` 的受限响应视为扫描结束。此类情况可能由登录态受限、接口风控或签名拦截引起，错误会包含已读取数量，避免将近期作品误报为全主页作品。

`resolve_author_nickname(profile_url)` 直接请求作者资料接口，核对返回的 `sec_uid` 后返回昵称。它不依赖作品列表，作者没有作品时也能读取昵称；资料接口失败、作者标识不匹配或昵称为空时抛出 `AuthorWorksError`。作品列表接口可能返回空响应，不能用它的失败判断作者资料不可用或 Cookie 必然失效。

`.env` 填写 `DY_COOKIES`：登录 https://www.douyin.com 后，从任意 `/aweme/v1/web/` 请求复制完整 Cookie，必须包含 `UIFID`。
