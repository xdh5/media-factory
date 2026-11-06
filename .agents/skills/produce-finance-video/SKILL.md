---
name: produce-finance-video
description: 使用财经库定稿制作财经、理财或情感短视频。
---

# 制作财经视频

1. 确定北京时间计划发布日期 `publish_date`，缺失或有歧义先问。用 `finance_get_config` 读取生产参数；只查库存或缺失分片时用 `finance_get_inventory`。
2. 用 `finance_start_production` 领取定稿，日内两篇分别传 `content_part=1`、`2`。用 `finance_get_task` 取已有稿件和分镜提示，按提示写分镜，沿用库中正文、标题和标签。
3. 用 `finance_prepare_visuals` 准备素材。默认实拍，按搜索顺序选尺寸达标素材，单段不足拼两段。参考图模式传 `image_config` 与用户参考图路径，按返回任务生成分镜图。
4. 用 `finance_submit_visuals` 提交素材，取 `manifest_path`。缓存已有图片时传空 `images`。用 `finance_prepare_editorial` 取得字幕和章节，再生成重点句排版、英文字幕与章节标题，合入生产配置。
5. 用 `finance_start_render` 合成，默认上传 R2；仅本地时传 `upload_r2=false`。交付成片、清单、上传结果、标题与标签。

后台步骤查询同一 `task_path`。配音需重做时带原 `draft_path`、日期和分片恢复；图片已保存时重试提交，避免重新生图或重复领取稿件。
