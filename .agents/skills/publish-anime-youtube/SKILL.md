---
name: publish-anime-youtube
description: 将主页选出的动漫、直接提供的长视频链接或本地成片发布到 YouTube。
---

# 发布动漫到 YouTube

1. 用 `anime_get_production_config` 查账号组。用 `publishing_start_account_check` 传业务线 `anime`、该账号组和平台 `youtube`，再用 `publishing_poll_task` 查实际授权。需要授权时展示入口，检测失败单独说明。全部通过后提示 **全部账号已登录，开始发布**。
2. 用 `anime_prepare_publication` 准备发布。主页找剧先用 `anime_discover_series`，存疑用 `anime_inspect_sources`，核对集序、合集和完结证据，再传 `source_type="series"`、`discovery_path`、有序 `work_ids` 与选片依据。直接长链接传 `source_type="links"`、有序 `share_texts`、剧名与选片依据。本地成片传 `source_type="local"` 和 `manifest_path`。远程准备只读取开头 60 秒。
3. 按转写写一份共用标题、描述和标签。剧名与剧情在前；已确认完结且覆盖全集时，描述加 #已完结 #一口气看完 #完整全集，搜索标签含「已完结」。用 `anime_save_publication_assets` 取参考帧和封面任务；按原画风生成带集数的封面，再传相同文案和 `images` 提交。全命中缓存时传空数组。
4. 确认作品已完结且无缺集、用户已要求发布、`assets_ready=true` 后，用 `anime_start_publication` 启动。远程来源交 GitHub Action 下载、按约三小时分段并上传，本地成片在本地发布。各作品用各自的播放列表。
5. 用 `anime_get_task` 查 `task_path` 或 `execution_id`。已触发只报告已触发；全部分段有视频 ID 且回执落库才算成功。重试只恢复未完成项。
