# 动漫工具调用流程

1. 调用 `anime_get_production_config` 读取配置和账号组。
2. 主页找剧使用 `anime_discover_series(profile_url, series_name, limit)`；读取完整扫描结果，识别别称、改名、误标和补发。只检查缺集时到此即可，不制作、不发布。
3. 疑点使用 `anime_inspect_sources(discovery_path, work_ids, window_starts, cover_reason)` 提取片段；先用标题、集号、发布时间和转写核对，封面只作最后取证。报告扫描范围、集序、缺集、重复、合集覆盖和完结证据；暂未找到与确认缺失分开说明。扫描到上限继续扩大，最多1000条，不能把更新至某集当成完结。
4. 仅制作使用 `anime_start_compile`：有序链接传 `share_texts`；主页选片传 `discovery_path`、有序 `work_ids`、`selection_reason`。排除重复覆盖，完整合集保持原文件，多来源在完整剧集边界按约三小时均衡分段。
5. 发布准备调用 `anime_prepare_publication`：主页选片传 `source_type="series"`、`discovery_path`、`work_ids`、`selection_reason`；直接长链接传 `source_type="links"`、`share_texts`、`series_name`、`selection_reason`；本地成片传 `source_type="local"`、`manifest_path`。来源须确认无缺集且已完结，原因写清证据。远程来源只读取开头60秒，不先全量下载。
6. 所有本地后台任务使用 `anime_get_task(task_path=...)` 查询，完成后读取结果，禁止重复启动。
7. 宿主根据转写撰写共用标题、描述、标签。标题先剧名和剧情，后追加已完结、一口气看完、完整全集等适用词。描述含 #已完结 #一口气看完 #完整全集；搜索标签含已完结。超长合集和爽文须符合实际。
8. 调用 `anime_save_publication_assets(manifest_path, titles, descriptions, tags)`，标题和描述数组各一个元素，返回参考帧、各段封面任务与缓存情况。宿主亲自查看参考并生图，保留画风且画面包含各段集数，不让 MCP 调用生成模型。
9. 再调用同一素材工具，传相同文案和 `images`（各项 `image_id`、`image_path`）；全部命中缓存时传空数组。只有 `assets_ready=true` 才可发布。
10. 获得用户发布授权后调用 `anime_start_publication(manifest_path, account_group, playlist_title)`。执行位置由清单决定：远程来源走 GitHub Action，本地完整成片本地发布。不同作品进入各自播放列表。工具读取保存的素材，无需再次传文案。
11. Action 返回 dispatched 仅代表已触发，按需用 `anime_get_task(execution_id=...)` 查询；不用持续在线轮询。全部分段取得视频 ID 且回执持久化即成功，不等待 YouTube 转码。重跑同一执行只恢复未完成工作，不能重复上传成功项。

任务结果保留原始阶段、异常、产物路径和最终链接。下载、拼接和发布必须复用 MCP，不自行执行替代脚本。不要求动漫计划发布日期，不触发其他平台发布。
