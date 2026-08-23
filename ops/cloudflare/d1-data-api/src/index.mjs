const ACTIVE_STATUSES = ["reserved", "completed", "published", "used"];

function jsonResponse(payload, status = 200) {
  return Response.json(payload, {
    status,
    headers: { "Cache-Control": "no-store" },
  });
}

function errorResponse(code, message, status = 400, details = {}) {
  return jsonResponse({ error: { code, message, details } }, status);
}

function requiredText(value, name, maxLength = 500) {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} 必须是非空字符串`);
  }
  const result = value.trim();
  if (result.length > maxLength) {
    throw new Error(`${name} 不能超过 ${maxLength} 个字符`);
  }
  return result;
}

function positiveInteger(value, name, maximum = 3650) {
  const result = Number(value);
  if (!Number.isInteger(result) || result < 1 || result > maximum) {
    throw new Error(`${name} 必须是 1 到 ${maximum} 的整数`);
  }
  return result;
}

function cutoffTimestamp(days) {
  return new Date(Date.now() - days * 86400000).toISOString().replace(/\.\d{3}Z$/, "Z");
}

function isAuthorized(request, env) {
  const configured = String(env.DATA_API_TOKEN || "");
  const provided = request.headers.get("Authorization") || "";
  return configured.length >= 32 && provided === `Bearer ${configured}`;
}

async function listTopics(request, env) {
  const url = new URL(request.url);
  const workflow = requiredText(url.searchParams.get("workflow"), "workflow", 64);
  const days = positiveInteger(url.searchParams.get("days"), "days");
  const placeholders = ACTIVE_STATUSES.map(() => "?").join(",");
  const result = await env.DB.prepare(
    `SELECT id, workflow, topic, fingerprint, status, publication_id, created_at, updated_at
     FROM topic_history
     WHERE workflow = ? AND created_at >= ? AND status IN (${placeholders})
     ORDER BY created_at DESC`,
  ).bind(workflow, cutoffTimestamp(days), ...ACTIVE_STATUSES).all();
  return jsonResponse({ records: result.results || [] });
}

async function reserveTopic(request, env) {
  const body = await request.json();
  const workflow = requiredText(body.workflow, "workflow", 64);
  const topic = requiredText(body.topic, "topic", 500);
  const fingerprint = requiredText(body.fingerprint, "fingerprint", 64);
  const days = positiveInteger(body.days, "days");
  if (!/^[a-f0-9]{64}$/.test(fingerprint)) {
    throw new Error("fingerprint 必须是 64 位小写十六进制 SHA-256");
  }
  const placeholders = ACTIVE_STATUSES.map(() => "?").join(",");
  const now = new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
  const inserted = await env.DB.prepare(
    `INSERT INTO topic_history(workflow, topic, fingerprint, status, created_at, updated_at)
     SELECT ?, ?, ?, 'used', ?, ?
     WHERE NOT EXISTS (
       SELECT 1 FROM topic_history
       WHERE workflow = ? AND fingerprint = ? AND created_at >= ?
       AND status IN (${placeholders})
     )
     RETURNING id, workflow, topic, fingerprint, status, created_at, updated_at`,
  ).bind(
    workflow, topic, fingerprint, now, now,
    workflow, fingerprint, cutoffTimestamp(days), ...ACTIVE_STATUSES,
  ).first();
  if (inserted) {
    return jsonResponse({ record: inserted }, 201);
  }
  const duplicate = await env.DB.prepare(
    `SELECT id, workflow, topic, fingerprint, status, publication_id, created_at, updated_at
     FROM topic_history
     WHERE workflow = ? AND fingerprint = ? AND created_at >= ?
     AND status IN (${placeholders})
     ORDER BY created_at DESC LIMIT 1`,
  ).bind(workflow, fingerprint, cutoffTimestamp(days), ...ACTIVE_STATUSES).first();
  return errorResponse("DUPLICATE_TOPIC", `话题在最近 ${days} 天内已经使用：${duplicate?.topic || topic}`, 409, {
    duplicate_record: duplicate,
    days,
  });
}

async function commitPublication(request, env) {
  const body = await request.json();
  const publicationId = requiredText(body.publication_id, "publication_id", 200);
  const workflow = requiredText(body.workflow, "workflow", 64);
  const topic = requiredText(body.topic, "topic", 500);
  const fingerprint = requiredText(body.fingerprint, "fingerprint", 64);
  const days = positiveInteger(body.days, "days");
  const historyDays = positiveInteger(body.history_days, "history_days");
  const minimumNewWords = positiveInteger(body.minimum_new_words, "minimum_new_words", 10);
  const rawEntries = Array.isArray(body.entries) ? body.entries : [];
  if (!/^[a-f0-9]{64}$/.test(fingerprint)) {
    throw new Error("fingerprint 必须是 64 位小写十六进制 SHA-256");
  }
  const existing = await env.DB.prepare(
    `SELECT id, workflow, topic, fingerprint, status, publication_id, created_at, updated_at
     FROM topic_history WHERE publication_id = ? LIMIT 1`,
  ).bind(publicationId).first();
  if (existing) {
    if (existing.workflow !== workflow || existing.fingerprint !== fingerprint) {
      return errorResponse("PUBLICATION_CONFLICT", "publication_id 已绑定其他内容", 409, {
        publication_id: publicationId,
      });
    }
    const count = await env.DB.prepare(
      "SELECT COUNT(*) AS count FROM language_learning_words WHERE run_id = ?",
    ).bind(publicationId).first();
    return jsonResponse({
      record: existing,
      already_committed: true,
      word_count: Number(count?.count || 0),
    });
  }
  const placeholders = ACTIVE_STATUSES.map(() => "?").join(",");
  const duplicate = await env.DB.prepare(
    `SELECT id, workflow, topic, fingerprint, status, publication_id, created_at, updated_at
     FROM topic_history
     WHERE workflow = ? AND fingerprint = ? AND created_at >= ?
     AND status IN (${placeholders})
     ORDER BY created_at DESC LIMIT 1`,
  ).bind(workflow, fingerprint, cutoffTimestamp(days), ...ACTIVE_STATUSES).first();
  if (duplicate) {
    return errorResponse("DUPLICATE_TOPIC", `话题在最近 ${days} 天内已经发布：${duplicate.topic}`, 409, {
      duplicate_record: duplicate,
      days,
    });
  }
  let entries = [];
  if (rawEntries.length) {
    entries = validateWordEntries(rawEntries);
    const entriesJson = JSON.stringify(entries);
    const recent = await env.DB.prepare(
      `SELECT DISTINCT normalized_english
       FROM language_learning_words
       WHERE created_at >= ?
       AND normalized_english IN (
         SELECT json_extract(value, '$.normalized_english') FROM json_each(?)
       )`,
    ).bind(cutoffTimestamp(historyDays), entriesJson).all();
    const repeatedSet = new Set((recent.results || []).map((row) => row.normalized_english));
    const repeatedWords = entries.filter((entry) => repeatedSet.has(entry.normalized_english)).map((entry) => entry.english);
    if (entries.length - repeatedWords.length < minimumNewWords) {
      return errorResponse(
        "VOCABULARY_REUSE_LIMIT",
        `本次只有 ${entries.length - repeatedWords.length} 个新词；发布入库至少需要 ${minimumNewWords} 个新词`,
        409,
        {
          history_days: historyDays,
          minimum_new_words: minimumNewWords,
          new_word_count: entries.length - repeatedWords.length,
          repeated_word_count: repeatedWords.length,
          repeated_words: repeatedWords,
        },
      );
    }
  }
  const now = new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
  const statements = [env.DB.prepare(
    `INSERT INTO topic_history(
       workflow, topic, fingerprint, status, publication_id, created_at, updated_at
     ) VALUES (?, ?, ?, 'published', ?, ?, ?)
     RETURNING id, workflow, topic, fingerprint, status, publication_id, created_at, updated_at`,
  ).bind(workflow, topic, fingerprint, publicationId, now, now)];
  if (entries.length) {
    statements.push(env.DB.prepare(
      `INSERT INTO language_learning_words(
         run_id, topic_record_id, topic, english, normalized_english, word_json, created_at
       )
       SELECT ?,
              (SELECT id FROM topic_history WHERE publication_id = ?),
              ?,
              json_extract(value, '$.english'),
              json_extract(value, '$.normalized_english'),
              json_extract(value, '$.word_json'), ?
       FROM json_each(?)`,
    ).bind(publicationId, publicationId, topic, now, JSON.stringify(entries)));
  }
  const results = await env.DB.batch(statements);
  const record = results[0]?.results?.[0];
  if (!record) {
    throw new Error("发布入库后没有返回话题记录");
  }
  return jsonResponse({ record, already_committed: false, word_count: entries.length }, 201);
}

async function listRecentWords(request, env) {
  const url = new URL(request.url);
  const days = positiveInteger(url.searchParams.get("days"), "days");
  const result = await env.DB.prepare(
    `SELECT normalized_english, MAX(english) AS english, MAX(created_at) AS last_used_at
     FROM language_learning_words
     WHERE created_at >= ?
     GROUP BY normalized_english
     ORDER BY last_used_at DESC, normalized_english`,
  ).bind(cutoffTimestamp(days)).all();
  return jsonResponse({ words: (result.results || []).map((row) => row.english) });
}

function validateWordEntries(rawEntries) {
  if (!Array.isArray(rawEntries) || rawEntries.length !== 10) {
    throw new Error("entries 必须包含 10 个单词对象");
  }
  const entries = rawEntries.map((entry) => ({
    english: requiredText(entry?.english, "english", 200),
    normalized_english: requiredText(entry?.normalized_english, "normalized_english", 200),
    word_json: requiredText(entry?.word_json, "word_json", 20000),
  }));
  if (new Set(entries.map((entry) => entry.normalized_english)).size !== 10) {
    throw new Error("entries 必须包含 10 个不同的英语单词");
  }
  return entries;
}

async function validateAndRecordWords(request, env) {
  const body = await request.json();
  const workflow = requiredText(body.workflow, "workflow", 64);
  const runId = requiredText(body.run_id, "run_id", 64);
  const topic = requiredText(body.topic, "topic", 500);
  const historyDays = positiveInteger(body.history_days, "history_days");
  const minimumNewWords = positiveInteger(body.minimum_new_words, "minimum_new_words", 10);
  const entries = validateWordEntries(body.entries);
  const runMatch = /^run-(\d{6,})$/.exec(runId);
  if (!runMatch) {
    throw new Error("run_id 格式不正确");
  }
  const topicRecordId = Number(runMatch[1]);
  const topicRecord = await env.DB.prepare(
    "SELECT workflow, topic FROM topic_history WHERE id = ?",
  ).bind(topicRecordId).first();
  if (!topicRecord) {
    return errorResponse("WORD_HISTORY_ERROR", `run_id ${runId} 对应的话题记录不存在`, 409);
  }
  if (topicRecord.workflow !== workflow || String(topicRecord.topic).trim() !== topic) {
    return errorResponse("WORD_HISTORY_ERROR", `run_id ${runId} 与主题不匹配，禁止记录词表`, 409);
  }
  const existing = await env.DB.prepare(
    "SELECT normalized_english FROM language_learning_words WHERE run_id = ? ORDER BY normalized_english",
  ).bind(runId).all();
  if ((existing.results || []).length) {
    const recorded = (existing.results || []).map((row) => row.normalized_english).sort();
    const incoming = entries.map((entry) => entry.normalized_english).sort();
    if (JSON.stringify(recorded) !== JSON.stringify(incoming)) {
      return errorResponse("WORD_HISTORY_ERROR", `run_id ${runId} 已记录过另一份词表，禁止覆盖`, 409);
    }
    return jsonResponse({
      recorded: false,
      already_recorded: true,
      run_id: runId,
      word_count: entries.length,
      history_days: historyDays,
      minimum_new_words: minimumNewWords,
    });
  }
  const entriesJson = JSON.stringify(entries);
  const now = new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
  let inserted;
  try {
    inserted = await env.DB.prepare(
      `INSERT INTO language_learning_words(
         run_id, topic_record_id, topic, english, normalized_english, word_json, created_at
       )
       SELECT ?, ?, ?,
              json_extract(value, '$.english'),
              json_extract(value, '$.normalized_english'),
              json_extract(value, '$.word_json'), ?
       FROM json_each(?)
       WHERE (
         SELECT COUNT(DISTINCT normalized_english)
         FROM language_learning_words
         WHERE created_at >= ?
         AND normalized_english IN (
           SELECT json_extract(value, '$.normalized_english') FROM json_each(?)
         )
       ) <= ?`,
    ).bind(
      runId, topicRecordId, topic, now, entriesJson,
      cutoffTimestamp(historyDays), entriesJson, entries.length - minimumNewWords,
    ).run();
  } catch (error) {
    const raced = await env.DB.prepare(
      "SELECT normalized_english FROM language_learning_words WHERE run_id = ?",
    ).bind(runId).all();
    if ((raced.results || []).length === entries.length) {
      return jsonResponse({
        recorded: false,
        already_recorded: true,
        run_id: runId,
        word_count: entries.length,
        history_days: historyDays,
        minimum_new_words: minimumNewWords,
      });
    }
    throw error;
  }
  if (Number(inserted.meta?.changes || 0) !== entries.length) {
    const recent = await env.DB.prepare(
      `SELECT DISTINCT normalized_english
       FROM language_learning_words
       WHERE created_at >= ?
       AND normalized_english IN (
         SELECT json_extract(value, '$.normalized_english') FROM json_each(?)
       )`,
    ).bind(cutoffTimestamp(historyDays), entriesJson).all();
    const repeatedSet = new Set((recent.results || []).map((row) => row.normalized_english));
    const repeatedWords = entries.filter((entry) => repeatedSet.has(entry.normalized_english)).map((entry) => entry.english);
    return errorResponse(
      "VOCABULARY_REUSE_LIMIT",
      `本次只有 ${entries.length - repeatedWords.length} 个新词；${entries.length} 个单词中至少需要 ${minimumNewWords} 个未在最近 ${historyDays} 天使用`,
      409,
      {
        history_days: historyDays,
        minimum_new_words: minimumNewWords,
        new_word_count: entries.length - repeatedWords.length,
        repeated_word_count: repeatedWords.length,
        repeated_words: repeatedWords,
      },
    );
  }
  const recent = await env.DB.prepare(
    `SELECT DISTINCT normalized_english
     FROM language_learning_words
     WHERE created_at >= ? AND run_id <> ?
     AND normalized_english IN (
       SELECT json_extract(value, '$.normalized_english') FROM json_each(?)
     )`,
  ).bind(cutoffTimestamp(historyDays), runId, entriesJson).all();
  const repeatedSet = new Set((recent.results || []).map((row) => row.normalized_english));
  const repeatedWords = entries.filter((entry) => repeatedSet.has(entry.normalized_english)).map((entry) => entry.english);
  return jsonResponse({
    recorded: true,
    already_recorded: false,
    run_id: runId,
    word_count: entries.length,
    new_word_count: entries.length - repeatedWords.length,
    repeated_word_count: repeatedWords.length,
    repeated_words: repeatedWords,
    history_days: historyDays,
    minimum_new_words: minimumNewWords,
  }, 201);
}

async function listImages(request, env) {
  const url = new URL(request.url);
  const line = requiredText(url.searchParams.get("line"), "line", 64);
  if (!/^[a-z][a-z0-9_]{0,63}$/.test(line)) {
    throw new Error("line 格式不正确");
  }
  const result = await env.DB.prepare(
    "SELECT id, caption, image_path FROM image_library WHERE line = ? ORDER BY id",
  ).bind(line).all();
  return jsonResponse({ records: result.results || [] });
}

async function listPublishAccountGroups(request, env) {
  const url = new URL(request.url);
  const group = String(url.searchParams.get("group") || "").trim();
  if (group.length > 100) {
    throw new Error("group 不能超过 100 个字符");
  }
  const where = group ? "WHERE groups.code = ? OR groups.name = ?" : "";
  const statement = env.DB.prepare(
    `SELECT
       groups.code AS group_code,
       groups.name AS group_name,
       groups.workflow AS group_workflow,
       groups.enabled AS group_enabled,
       accounts.code AS account_code,
       accounts.platform,
       accounts.display_name,
       accounts.connector,
       accounts.config_key,
       accounts.config_json,
       members.position,
       members.enabled AS member_enabled,
       accounts.enabled AS account_enabled
     FROM publish_account_groups AS groups
     LEFT JOIN publish_account_group_members AS members
       ON members.group_code = groups.code
     LEFT JOIN publish_accounts AS accounts
       ON accounts.code = members.account_code
     ${where}
     ORDER BY groups.code, members.position, accounts.code`,
  );
  const result = group
    ? await statement.bind(group, group).all()
    : await statement.all();
  const records = [];
  const byCode = new Map();
  for (const row of result.results || []) {
    let record = byCode.get(row.group_code);
    if (!record) {
      record = {
        code: row.group_code,
        name: row.group_name,
        workflow: row.group_workflow,
        enabled: Boolean(row.group_enabled),
        members: [],
      };
      byCode.set(row.group_code, record);
      records.push(record);
    }
    if (!row.account_code) continue;
    let config;
    try {
      config = JSON.parse(row.config_json || "{}");
    } catch {
      throw new Error(`账号 ${row.account_code} 的 config_json 格式不正确`);
    }
    record.members.push({
      code: row.account_code,
      platform: row.platform,
      display_name: row.display_name,
      connector: row.connector,
      config_key: row.config_key,
      config,
      position: Number(row.position || 0),
      enabled: Boolean(row.group_enabled && row.member_enabled && row.account_enabled),
    });
  }
  if (group && !records.length) {
    return errorResponse("ACCOUNT_GROUP_NOT_FOUND", `发布账号组不存在：${group}`, 404, { group });
  }
  return jsonResponse({ records });
}

async function listDouyinResearchIds(env) {
  const result = await env.DB.prepare(
    "SELECT aweme_id FROM douyin_research_contents ORDER BY created_at DESC",
  ).all();
  return jsonResponse({
    aweme_ids: (result.results || []).map((row) => String(row.aweme_id)),
  });
}

function douyinResearchRecord(value) {
  if (!value || typeof value !== "object") {
    throw new Error("records 必须包含对象");
  }
  const awemeId = requiredText(value.aweme_id, "aweme_id", 64);
  if (!/^\d+$/.test(awemeId)) {
    throw new Error("aweme_id 格式不正确");
  }
  const searchRank = positiveInteger(value.search_rank, "search_rank", 1000);
  return {
    aweme_id: awemeId,
    collection_code: requiredText(value.collection_code, "collection_code", 64),
    collection_name: requiredText(value.collection_name, "collection_name", 100),
    search_keyword: requiredText(value.search_keyword, "search_keyword", 200),
    search_rank: searchRank,
    author_name: requiredText(value.author_name || "未知作者", "author_name", 200),
    published_at: String(value.published_at || "").trim() || null,
    caption: requiredText(value.caption || "无文案", "caption", 10000),
    transcript_raw: requiredText(value.transcript_raw, "transcript_raw", 50000),
    transcript_corrected: requiredText(value.transcript_corrected, "transcript_corrected", 50000),
    aweme_url: requiredText(value.aweme_url, "aweme_url", 1000),
    cover_url: String(value.cover_url || "").trim() || null,
  };
}

async function commitDouyinResearch(request, env) {
  const body = await request.json();
  const rawRecords = Array.isArray(body.records) ? body.records : [];
  if (!rawRecords.length || rawRecords.length > 5) {
    throw new Error("records 必须包含 1 到 5 条作品");
  }
  const records = rawRecords.map(douyinResearchRecord);
  if (new Set(records.map((record) => record.aweme_id)).size !== records.length) {
    throw new Error("records 包含重复 aweme_id");
  }
  const now = new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
  for (const record of records) {
    if (!/^[a-z][a-z0-9_-]{0,63}$/.test(record.collection_code)) {
      throw new Error("collection_code 格式不正确");
    }
  }
  const statements = [];
  for (const record of records) {
    statements.push(env.DB.prepare(
      `INSERT INTO douyin_research_collections(code, name, created_at, updated_at)
       VALUES (?, ?, ?, ?)
       ON CONFLICT(code) DO UPDATE SET name = excluded.name, updated_at = excluded.updated_at`,
    ).bind(record.collection_code, record.collection_name, now, now));
    statements.push(env.DB.prepare(
      `INSERT INTO douyin_research_contents(
         aweme_id, author_name, published_at, caption, transcript_raw,
         transcript_corrected, aweme_url, cover_url, created_at, updated_at
       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
       ON CONFLICT(aweme_id) DO NOTHING`,
    ).bind(
      record.aweme_id, record.author_name, record.published_at, record.caption,
      record.transcript_raw, record.transcript_corrected, record.aweme_url,
      record.cover_url, now, now,
    ));
    statements.push(env.DB.prepare(
      `INSERT INTO douyin_research_discoveries(
         aweme_id, collection_code, search_keyword, search_rank, discovered_at
       ) VALUES (?, ?, ?, ?, ?)
       ON CONFLICT(aweme_id, collection_code, search_keyword) DO NOTHING`,
    ).bind(
      record.aweme_id, record.collection_code, record.search_keyword,
      record.search_rank, now,
    ));
  }
  const results = await env.DB.batch(statements);
  const insertedCount = records.filter((_, index) => Number(results[index * 3 + 1]?.meta?.changes || 0) > 0).length;
  const discoveryCount = records.filter((_, index) => Number(results[index * 3 + 2]?.meta?.changes || 0) > 0).length;
  return jsonResponse({
    records: records.map((record) => ({
      aweme_id: record.aweme_id,
      collection_code: record.collection_code,
      collection_name: record.collection_name,
      search_keyword: record.search_keyword,
      search_rank: record.search_rank,
    })),
    inserted_count: insertedCount,
    duplicate_count: records.length - insertedCount,
    discovery_count: discoveryCount,
  }, insertedCount || discoveryCount ? 201 : 200);
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === "GET" && url.pathname === "/health") {
      return new Response("ok", {
        status: 200,
        headers: { "Cache-Control": "no-store", "Content-Type": "text/plain; charset=utf-8" },
      });
    }
    if (!isAuthorized(request, env)) {
      return errorResponse("UNAUTHORIZED", "鉴权失败", 401);
    }
    try {
      if (request.method === "GET" && url.pathname === "/v1/topics") return await listTopics(request, env);
      if (request.method === "POST" && url.pathname === "/v1/topics/reserve") return await reserveTopic(request, env);
      if (request.method === "POST" && url.pathname === "/v1/publications/commit") return await commitPublication(request, env);
      if (request.method === "GET" && url.pathname === "/v1/words/recent") return await listRecentWords(request, env);
      if (request.method === "POST" && url.pathname === "/v1/words/validate-and-record") return await validateAndRecordWords(request, env);
      if (request.method === "GET" && url.pathname === "/v1/images") return await listImages(request, env);
      if (request.method === "GET" && url.pathname === "/v1/publish-account-groups") return await listPublishAccountGroups(request, env);
      if (request.method === "GET" && url.pathname === "/v1/douyin-research/ids") return await listDouyinResearchIds(env);
      if (request.method === "POST" && url.pathname === "/v1/douyin-research/commit") return await commitDouyinResearch(request, env);
      return errorResponse("NOT_FOUND", "接口不存在", 404);
    } catch (error) {
      if (error instanceof SyntaxError) {
        return errorResponse("INVALID_JSON", "请求体不是有效 JSON", 400);
      }
      if (error instanceof Error && /必须|不能|格式/.test(error.message)) {
        return errorResponse("INVALID_PARAMETER", error.message, 400);
      }
      console.error(error);
      return errorResponse("D1_ERROR", "Cloudflare D1 操作失败，请检查 Worker 日志", 500);
    }
  },
};
