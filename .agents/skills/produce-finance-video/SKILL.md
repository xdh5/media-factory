---
name: produce-finance-video
description: 生产财经视频。使用项目财经 MCP 制作中文短视频（财经、心灵鸡汤等文章类内容）；适用于“做财经视频”“生产财经视频”“运行 Finance”“生成理财短视频”“做心灵鸡汤视频”等请求。不适用于抖音关键词搜索、爬取或收集财经文案。
---

# 生产财经视频

使用 `finance` MCP。财经、心灵鸡汤等文章内容共用此制作线；原稿类型由数据库决定。关键词搜索和收集财经文案不属于本技能。用户给出链接要求收集文案时，使用 collect-finance-copy skill。

## 制作流程

1. 从请求中明确北京时间计划发布日期 publish_date；日期不明确先追问，不默认今天、不提前占用稿件。读取 `finance_get_config` 作为全部配音、素材和生产参数标准。
2. 只读库存、近期话题、某日成片和缺失分片用 `finance_get_inventory(publish_date)`。补齐旧稿用 `finance_manage_drafts`，宿主按 collect-finance-copy 定稿要求编辑，action=save 提交完整 records；不能修改已使用稿件。
3. 调用 `finance_start_production(publish_date, content_part, material_strategy)`。内部领取定稿、保存生产稿、生成配音和分镜输入。每天两条分别 content_part=1、2。直接使用库中定稿，不重写正文、标题和标签。
4. 用 `finance_get_task(task_path)` 等至 done=true，读取结果中的 draft、source、draft_path、storyboard_prompt 和 storyboard_system_prompt。宿主按提示编写完整分镜。
5. 调用 `finance_prepare_visuals(draft_path, storyboard_text, material_strategy)`。默认 stock_video 返回后台素材搜索任务，查询完成读取 context_path；agent_reference 须额外传 image_config={source: agent_reference, reference_image_path: 用户参考图路径}，由宿主生成返回的逐镜头图片。
6. 调用 `finance_submit_visuals(context_path, material_strategy, images, selections)`。生图策略传 images，各项 image_id、image_path，图片已在缓存时传空数组，工具校验并完成图库入库；实拍策略默认按搜索顺序选尺寸达标素材，必要时传明确 selections。单段不足时拼两段，不调用模型选片。下载返回后台任务，查询至 done=true，取得 manifest_path。此步骤不合成。
7. 调用 `finance_prepare_editorial(draft_path, storyboard_text, production_config)`，宿主据真实字幕和章节生成重点句排版 emphasis_lines.groups、中文字幕到英文译文的 secondary_subtitles.translations、章节短标题 chapter_timeline.titles，合入配置。不关闭图层跳过定稿。
8. 调用 `finance_start_render(draft_path, production_config, material_manifest_path, storyboard_text)`。后台合成并默认上传 R2，成功后标记原稿已使用。轮询同一 task_path，交付 video_path、manifest_path、r2、标题、标签和发布文案。仅保留本地时 upload_r2=false。

中间步骤无需逐项确认。耗时任务用 finance_get_task 持续观察至 done=true；客户端超时继续查询同一任务，不重复启动。缓存素材和成片复用，上传失败重试同一生产参数；不得重复领取稿件。配音阶段失败需重做时，finance_start_production 传已有 draft_path、原日期和分片恢复。生成图片已保存但图库入库失败时重试 finance_submit_visuals，images 传空数组，不重新生图。

实拍片头取第一段正文原始视频首帧做拍照滑入和快门，展开后直接播放该段实拍；封面原图保存为成片目录 cover.png。MCP 不调用通用生成模型，内容判断、分镜、翻译、重点句、章节及图片由宿主 Agent 完成，专用配音和转写服务保留。发布走 publishing MCP，本技能不发布。禁止绕过 MCP 执行业务脚本。
