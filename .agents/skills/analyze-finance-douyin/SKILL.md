---
name: analyze-finance-douyin
description: 复盘财经账号的公开抖音作品，用创作者中心指标和数据库定稿分析黄金钩子、内容表现和观众偏好。
---

# 复盘财经抖音作品

1. 调用 `finance_start_douyin_analysis` 读取 `finance` 的公开作品。按用户给出的统计范围传参。默认 90 天、12 篇定稿样本，作品发布满 48 小时后进入对照。
2. 按目标选择 `rank_by`。整体表现用 `view_count`，开场留存用 `bounce_rate_2s` 或 `completion_rate_5s`，正文观看深度用 `completion_rate`，收藏、分享或关注用相应的 `favorite_rate`、`share_rate`、`subscribe_rate`。
3. 使用 `finance_get_task` 和返回的 `task_path` 查询至完成。账号需要登录时请用户在 Publisher 重新登录。用成功结果的 `analysis_prompt` 结合 `works` 和 `script_sample` 直接撰写复盘。
4. 检查定稿覆盖与样本量。文案未匹配的作品可纳入指标概览。黄金钩子和正文分析只使用确定关联的 Cloudflare D1 定稿，禁止打开、下载、播放或转写视频。分析结论和实验由宿主生成。
