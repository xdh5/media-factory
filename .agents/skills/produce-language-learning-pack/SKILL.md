---
name: produce-language-learning-pack
description: 生产语言学习预制图包。使用语言学习 MCP 按主题生成双语词表和十张透明主体图并入库；适用于“做预制图包”“提前备语言学习图包”“生成可复用词包”等请求。不制作成片，不占用话题，不指定发布日期。
---

# 生产语言学习预制图包

用户给出主题即表示授权生成词表、生图、验收并入库，无需再次确认，也不要询问计划发布日期。

只通过 `language_learning` MCP 完成。不占用成片话题，不创建成片 run。词表、定位和整图验收规则以 MCP 返回的 Prompt 为准。禁止绕过 MCP 执行业务流程或读写内部文件。

1. 调用 `language_learning_prepare_pack(topic)`，按返回的词表 Prompt 生成中英和韩英各 10 个词，再调用 `language_learning_validate_pack_words`。
2. 使用校验返回的唯一主体图 Prompt，生成一张包含十个主体的真实 Alpha 透明 PNG。不拆成十次生图，不用纯色背景代替透明。
3. 复用成片的定位与整图验收 Prompt：先 `language_learning_validate_pack_subject_sheet` 切图，再打开返回的实际切图验收图，调用 `language_learning_review_pack_subject_sheet`。
4. 切图不完整或带入相邻主体时先重新定位；图片内容不合格时才重新生图。彩色杂边可以接受，不得因此拒收或重新生成。
5. 验收通过后调用 `language_learning_commit_pack`，上传十张透明切图并入库；提交成功时十个单词同时写入现有查重词库，后续词包必须读取最新词库再选词，禁止一次准备多包后跳过重新查重直接入库。最近 100 天最多重复 5 个单词，超过 5 个必须重新选词。

GitHub 生产只领取已入库的图包，库里没有时不会临时生图。MCP 未连接、进程退出或调用失败时，报告具体错误并停止。
