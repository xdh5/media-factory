---
name: collect-finance-copy
description: 使用财经 MCP 收集财经文案：保存单条抖音链接，维护财经作者名单，或按作者平分抓取指定数量的最新口播。适用于“收集财经文案”“把这个抖音链接转写入库”“添加财经作者”“查看作者名单”“抓取100个财经稿件”等请求。不用于制作成片。
---

# 收集财经文案

只通过 `finance` MCP 完成。下载和作者作品列表由该 MCP 调用 media-collector 子仓库，不要改到工厂的 `core/tools`。分类固定为“财经”。用户要求保存或抓取即表示授权下载、转写并写入财经文案库，无需再次确认。

作者名单保存在数据库里，可以随时增加、删除和查看，不是一次性导入。

## 作者怎么提供

每行一位作者。可以贴作者主页，也可以整段贴「查看TA的更多作品」分享口令。需要显示名时，在链接或口令后面加一个空格再写名字。

```text
https://www.douyin.com/user/MS4wLjABAAAA... 显示名
8- 长按复制此条消息，打开抖音搜索，查看TA的更多作品。 https://v.douyin.com/xxxx/ 4@9.com :3pm
```

口令里的短链必须跳到作者主页。不要用单条作品链接代替作者主页。

## 采集并定稿入库

1. 作者操作使用 `finance_manage_authors(action, profile_url, display_name)`，action 为 list、add、remove，增删后返回最新名单。
2. 单条调用 `finance_start_collection(share_text=原始分享文本)`；按作者配额调用 `finance_start_collection(count=N)`。分类固定财经。抓取数量按作者均分，去重并跳过已入库作品。
3. 调用 `finance_get_task(task_path)` 等待，完成后读取 result.pending、prompt、context_path。当前步骤完成不代表入库完成。
4. 宿主亲自校对错字标点、删除插入广告、判断整篇广告，并生成完整 editorial。禁止外部文本模型、关键词脚本代替判断。
5. 调用 `finance_finalize_collection(context_path, reviews)`，reviews 直接传数组，每条格式见下方。统一校验原稿与定稿再入库。
6. 返回 continuation 时查询其中 task_path，继续审核新 pending；无需再次启动续采。直到 completed=true 或候选用尽。不要为相同上下文重复提交审核。
7. 交付入库数、各作者取稿数、广告与重复跳过数及失败原因。不制作视频、不要求发布日期。

## 内容定稿

正常记录格式：`{"aweme_id":"作品ID","kind":"normal","text":"校对原稿","ad_segments":[],"reason":"广告清理和品牌替换结论","editorial":{"article":"完整断行正文","db_source_hook":"原文钩子","source_hook":"处理后钩子","replacements":[],"topic":"话题","title":"长标题","short_title":"短标题","hashtags":["标签一","标签二","标签三","标签四"],"cover_lines":["标题第一行"],"cover_highlights":["标题重点词"]}}`。

- 整篇广告 kind=ad，不需要 editorial；插入广告的 ad_segments 逐字复制原文并删除。逐篇通读，清除推销、导流、拉群、卖课及软植入。
- 原稿、定稿分开保存；保持结构、顺序、观点、数字和信息量，只做措辞级改写，不总结、扩写或编造。品牌、作者名、账号名、机构名、课程名和外号统一替换为财富研习岛，消除连载指涉。
- db_source_hook 从校对原稿开头连续复制完整钩子；source_hook 为品牌替换后的钩子，替换表写 replacements。
- 按语义断行，每行最多36字。长标题12～26字，短标题6～16字，四个标签不重复且不带井号。封面1～3行，拼接等于长标题，重点词来自长标题。
- 用 `finance_get_inventory` 的 topics 和 `finance_manage_drafts(action="list", missing_only=false)` 返回的稿件话题查重。待编辑旧稿通过同一稿件工具 action=save、records 保存；不修改已使用稿件。
- 正文不足以成篇时保留待编辑，不编造。工具校验失败只修改错误字段后重提。

禁止改用浏览器、临时脚本或外部文本 LLM 下载、转写、审核和入库。作者列表使用 media-collector 唯一的 DY_COOKIES 配置，缺失时报告错误，不改抓搜索页。
