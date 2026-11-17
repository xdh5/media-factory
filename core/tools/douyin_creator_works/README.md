# 抖音创作者中心作品接口

作品管理页是 `/creator-micro/content/manage`，单条作品数据页是 `/creator-micro/work-management/work-detail/{work_id}`。

- 作品列表使用 `GET /janus/douyin/creator/pc/work_list`。首页请求参数见模块中的 `WORK_LIST_PARAMS`。
- 单条作品数据使用 `GET /web/api/creator/item/mget`。传入作品 ID 参数 `ids`，请求字段为 `metrics,review,play_info`，请求头带 `Agw-Js-Conv: str`。
- `read_creator_works("finance")` 调用 Publisher CLI，由 Publisher 使用所选账号组的抖音 Electron 会话打开作品管理页。工具按游标读取作品列表，再按作品顺序读取逐条详情，返回 `works` 和 `metrics`。
- 已用财经账号的登录会话验证，列表参数 `status=0` 返回多种状态。只保留 `status_value=102`、`status.private_status=0` 且无私密、仅自己可见、删除、禁止或审核中标记的作品。预约未发布的作品不会查询详情。

接口来自创作者中心页面的预取配置。

- [作品管理页预取配置](https://creator.douyin.com/goofy/douyin_creator_pc/mono/prefetch/creator_content/manage/prefetch.json)
- [作品详情页预取配置](https://creator.douyin.com/goofy/douyin_creator_pc/mono/prefetch/work-management/work-detail/prefetch.json)
