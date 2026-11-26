---
name: collect-finance-copy
description: 采集认知提升口播，审核并完成大鹅正文、分镜、发布文案和封面定稿。
---

# 采集与定稿

频道面向普通人，涵盖情绪、关系、职场、家庭、人生及通俗财富与商业认知。按全文是否帮助理解、判断和行动选稿；专业财经与项目变现教学不作为主体。

## 素材模式

收集财经材料默认使用生图模式，无需再次询问素材模式；用户明确要求实拍时使用实拍。生图模式定稿完成后，除三版封面外，还需用 `finance_manage_storyboard_images(aweme_id)` 领取分镜生图任务，由宿主生成逐镜图片，再按顺序提交 `image_paths` 上传 R2。报告分镜图片预制状态，未完成时明确列为待处理。

本次采集稿继续制作视频时显式传 `generate_images=true`；实拍模式传 `false`，不依赖生产接口的默认值。同一工作流续跑保持原模式。

## 采集和审核

1. `finance_manage_authors` 管理作者；`finance_start_collection` 用 `share_text` 采单条，或用 `count` 分配作者配额。
2. 用 `finance_get_task` 读取原文和提示词，依次完成审核、校对、撰稿、发布文案、分镜和 SSML。内容判断与生成由宿主 Agent 完成。
3. 校对稿保存为 `text`：删除广告并将原文逐字记录到 `ad_segments`，补标点、纠正误识、清理冗余称呼，保留事实、数字、例子和论证顺序。无广告填空数组。

默认按项目 `mcp/finance/prompts/editorial-writing.md` 原创撰稿，目标2000～2500字；仅在用户明确要求按原稿改写时使用 `editorial-rewrite.md`，两者不混用。发布文案、分镜、配音分别遵循同目录的 `editorial-metadata.md`、`editorial-storyboard.md`、`editorial-ssml.md`。时长以实际配音为准，不加硬性字数拦截。

## 定稿字段与入库

撰稿、改写和发布文案中的网络表达由宿主大模型根据本篇主题直接选择，不为选梗联网检索，不维护固定词表，不宣称实时热度；已有定稿不批量重做。

将以下内容合并为 `editorial`，正文变更时同步更新分镜、SSML 和切片行号。

| 字段 | 内容 |
| --- | --- |
| `topic`、`article` | 主题、原创正文 |
| `source_hook` | 正文开头的黄金钩子，不含固定开场白 |
| `db_source_hook` | 从校对稿连续摘录的相关原文，仅用于来源核对 |
| `replacements` | 实际品牌替换的 `from`、`to` 数组，无则空数组 |
| `title`、`short_title`、`hashtags` | 完整标题、短标题、四个不带井号的标签 |
| `cover_lines`、`cover_highlights` | 封面断行、重点字，均为数组 |
| `storyboard` | 与正文逐行对应的「画面描述\|搜索关键词」 |
| `ssml` | 与正文逐行对应的 `<s>` 字符串数组 |
| `youtube_short_selection` | 连续约500字的 `start_line`、`end_line` 及完整标题断行 `title_lines` |
| `youtube_description`、`youtube_hashtags` | 长视频说明、10个专用标签 |
| `micro_summary` | 约150字微头条摘要 |

新采集稿通过 `finance_finalize_collection(context_path, reviews)` 一次提交全部待审作品：每篇包含 `aweme_id`、`kind`、`reason`、`text`。`keep` 另含 `ad_segments` 和完整 `editorial`；`skip` 的 `text` 为空，不填 `editorial`。继续处理返回的 `continuation`，直至配额补齐或候选用尽。

旧稿用 `finance_manage_drafts` 读取未使用记录，以校对原稿为参考重新定稿，再用 `action="save"` 保存。库存、话题及累计弃稿统计用 `finance_get_inventory` 查询。

## 封面与完成条件

1. 定稿入库后，用 `finance_manage_cover(aweme_id)` 领取参考图、指令和输出路径。
2. 宿主将两张参考图作为生图输入，独立生成4:3、3:4、16:9三版含完整长短标题的封面；文字与背景整体成图，不用代码叠字或素材拼景。
3. 查看三版实际图片，逐字核对标题及构图，再用 `image_paths={"landscape": 横版路径, "portrait": 竖版路径, "widescreen": 宽屏路径}` 提交同一工具上传 R2 并登记。标题变化须重做封面。

报告入库、封面、各作者取稿、弃稿及失败数。封面未登记的稿件不能报告为可生产。
