function editorialRecord(record, source) {
  const draft = record.editorial;
  for (const key of ['article', 'topic', 'title', 'short_title', 'source_hook', 'db_source_hook']) {
    if (typeof draft?.[key] !== 'string' || !draft[key].trim()) throw new Error(`定稿 ${key} 必须是非空字符串`);
  }
  const bare = value => value.replace(/\s+/g, '');
  if (!source.startsWith(draft.db_source_hook) || !bare(draft.article).startsWith(bare(draft.source_hook))) {
    throw new Error('定稿黄金钩子必须与原稿和正文开头对应');
  }
  if (draft.article.split(/\r?\n/).some(line => line.trim().length > 36)) throw new Error('定稿正文每行不能超过36字');
  if (draft.title.length < 12 || draft.title.length > 26 || draft.short_title.length < 6 || draft.short_title.length > 16) throw new Error('定稿标题长度不符合要求');
  if (!Array.isArray(draft.hashtags) || new Set(draft.hashtags).size !== 4 || draft.hashtags.length !== 4) throw new Error('定稿必须有四个不同标签');
  if (!Array.isArray(draft.cover_lines) || draft.cover_lines.length < 1 || draft.cover_lines.length > 3 || bare(draft.cover_lines.join('')) !== bare(draft.title)) throw new Error('封面断行必须与标题一致');
  if (!Array.isArray(draft.cover_highlights) || !draft.cover_highlights.length || draft.cover_highlights.some(word => !word || !draft.title.includes(word))) throw new Error('封面重点词必须来自标题');
  return JSON.stringify(draft);
}

export async function listFinanceEditorialDrafts(request, env) {
  const missingOnly = new URL(request.url).searchParams.get('missing_only') !== 'false';
  const rows = await env.DB.prepare(`SELECT c.aweme_id, c.caption, c.author_name, c.transcript_corrected,
    e.content_json, u.status AS usage_status
    FROM douyin_research_contents c
    LEFT JOIN finance_editorial_drafts e ON e.aweme_id = c.aweme_id AND e.source_transcript = c.transcript_corrected
    LEFT JOIN douyin_research_script_usage u ON u.aweme_id = c.aweme_id AND u.workflow = 'finance'
    WHERE EXISTS (SELECT 1 FROM douyin_research_discoveries d WHERE d.aweme_id = c.aweme_id AND d.collection_code = 'finance')
    AND (u.status IS NULL OR u.status <> 'used')
    AND (? = 0 OR e.aweme_id IS NULL)
    ORDER BY c.created_at, c.aweme_id`).bind(Number(missingOnly)).all();
  return Response.json({ records: rows.results.map(row => ({ ...row, editorial: row.content_json ? JSON.parse(row.content_json) : null, content_json: undefined })) });
}

export async function commitFinanceEditorialDrafts(request, env) {
  const { records } = await request.json();
  if (!Array.isArray(records) || !records.length || records.length > 100) throw new Error('records 必须包含1至100篇定稿');
  const statements = [];
  for (const record of records) {
    const source = await env.DB.prepare(`SELECT c.transcript_corrected FROM douyin_research_contents c
      WHERE c.aweme_id = ? AND NOT EXISTS (SELECT 1 FROM douyin_research_script_usage u WHERE u.aweme_id = c.aweme_id AND u.status = 'used')`).bind(record.aweme_id).first();
    if (!source) throw new Error(`稿件不存在或已经使用，不能修改：${record.aweme_id}`);
    const content = editorialRecord(record, source.transcript_corrected);
    statements.push(env.DB.prepare(`INSERT INTO finance_editorial_drafts(aweme_id, source_transcript, content_json)
      SELECT ?, ?, ? WHERE NOT EXISTS (SELECT 1 FROM douyin_research_script_usage WHERE aweme_id = ? AND status = 'used')
      ON CONFLICT(aweme_id) DO UPDATE SET source_transcript = excluded.source_transcript, content_json = excluded.content_json, updated_at = CURRENT_TIMESTAMP
      WHERE NOT EXISTS (SELECT 1 FROM douyin_research_script_usage WHERE aweme_id = excluded.aweme_id AND status = 'used')`)
      .bind(record.aweme_id, source.transcript_corrected, content, record.aweme_id));
  }
  const results = await env.DB.batch(statements);
  return Response.json({ saved_count: results.reduce((sum, row) => sum + Number(row.meta.changes), 0) });
}
