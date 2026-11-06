---
name: produce-finance-video
description: 使用财经库定稿制作财经、理财或情感短视频。
---

# 制作财经视频

1. 确认北京时间计划发布日期，缺失或有歧义时询问。用 `finance_get_config` 查配置，查库存或缺片用 `finance_get_inventory`。
2. 用 `finance_start_production` 领取定稿，日内两篇分别传 `content_part=1`、`2`。按返回提示写分镜，沿用稿库正文、标题和标签。
3. 用 `finance_prepare_visuals` 准备素材，默认实拍。参考图模式传 `image_config` 和参考图。用 `finance_submit_visuals` 取素材清单，缓存图片齐全时传空 `images`。
4. 用 `finance_prepare_editorial` 取输入，将重点句排版、英文字幕和章节标题合入生产配置。调用 `finance_start_render`，仅本地时传 `upload_r2=false`。交付成片、清单、标题、标签及上传结果。
5. 后台步骤用 `finance_get_task` 查原任务。配音恢复传原 `draft_path`、日期和分片；图片已保存时重试提交。
