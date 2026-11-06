---
name: publish-anime-youtube
description: 将主页选出的动漫、直接提供的长视频链接或本地成片发布到 YouTube。
---

# 发布动漫到 YouTube

1. 用户要求发布后，读取 `anime_get_production_config`。用 `publishing_start_account_check` 检查该账号组的 YouTube 授权，用 `publishing_poll_task` 查结果。需要授权时提供入口，检测失败单独说明。全部通过后提示 **全部账号已登录，开始发布**。
2. 核实已完结且无缺集。用 `anime_prepare_publication` 准备：主页选片传 `series`、扫描清单、有序作品 ID 和依据；长链接传 `links`、有序链接、剧名和依据；本地传 `local` 和成片清单。
3. 根据开头转写写共用标题、描述和标签，标题先写剧名与剧情。全集完结时描述加 #已完结 #一口气看完 #完整全集，搜索标签含「已完结」。用 `anime_save_publication_assets` 取参考帧，按原画风生成含集数的各段封面，再以相同文案和 `images` 提交。全命中缓存时传空数组。
4. `assets_ready=true` 后用 `anime_start_publication` 启动。各作品用独立播放列表。用 `anime_get_task` 查 `task_path` 或 `execution_id`，各段取得视频 ID 且保存回执才算成功。重试恢复未完成项。
