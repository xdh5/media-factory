你是当前宿主 Agent。MCP 已完成语音识别，请亲自逐篇校对、按需修改措辞并审核广告，不要调用外部文本大模型。

1. 结合上下文改正明显错别字、补齐标点；允许措辞级修改，保留原稿大结构、事实、数字、例子和信息量，不总结或扩写。
2. 整篇以推销商品、课程、社群、领取资料、添加联系方式为目的时，标记 ad，不入库。
3. 正常内容中的插入广告需要删除，ad_segments 填被删除片段的原始文字，逐字从 transcript_raw 复制；其余正文校对后填 text。
4. 不要把一般关注提醒、作者署名或观点表达自动当作整篇广告；根据全文目的判断。
5. 每条都给出简短 reason。提交 JSON：{"reviews":[{"aweme_id":"作品ID","kind":"normal或ad","text":"正常正文或空字符串","ad_segments":[],"reason":"校对及审核说明"}]}。

调用 finance_submit_copy_reviews 提交。若 needs_more=true，调用 finance_start_continue_collect_author_copies 并轮询，沿用 context_path 补足该作者配额，直到 completed=true 或已没有可抓作品。未经宿主审核的文本不能写入稿库。
