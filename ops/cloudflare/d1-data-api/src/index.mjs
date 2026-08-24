const ACTIVE_STATUSES = ["reserved", "completed", "published", "used"];
const PUBLICATION_BUSINESS_LINES = ["finance", "language_learning"];
const PUBLICATION_PLATFORMS = [
  "youtube", "facebook", "instagram", "tiktok", "kuaishou",
  "douyin", "baijiahao", "xiaohongshu", "toutiao", "wechat_channels",
];
const PUBLICATION_MODES = ["immediate", "scheduled"];
const PUBLICATION_STATUSES = ["published", "scheduled"];
const PRODUCTION_SOURCES = ["local_mcp", "github_workflow"];

function jsonResponse(payload, status = 200) {
  return Response.json(payload, {
    status,
    headers: { "Cache-Control": "no-store" },
  });
}

function errorResponse(code, message, status = 400, details = {}) {
  return jsonResponse({ error: { code, message, details } }, status);
}

function dashboardResponse(payload, status = 200) {
  return Response.json(payload, {
    status,
    headers: {
      "Cache-Control": "no-store",
      "Access-Control-Allow-Origin": "https://xdh5.github.io",
      "Access-Control-Allow-Headers": "Content-Type, X-Dashboard-Pin",
      "Access-Control-Allow-Methods": "GET, OPTIONS",
      "Vary": "Origin",
    },
  });
}

function isDashboardAuthorized(request, env) {
  const configured = String(env.DASHBOARD_PIN || "").trim();
  const provided = String(request.headers.get("X-Dashboard-Pin") || "").trim();
  if (!/^\d{6}$/.test(configured) || !/^\d{6}$/.test(provided)) return false;
  let difference = 0;
  for (let index = 0; index < configured.length; index += 1) {
    difference |= configured.charCodeAt(index) ^ provided.charCodeAt(index);
  }
  return difference === 0;
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

function optionalText(value, name, maxLength = 2000) {
  if (value === null || value === undefined || value === "") return null;
  if (typeof value !== "string") throw new Error(`${name} 必须是字符串或 null`);
  const result = value.trim();
  if (result.length > maxLength) throw new Error(`${name} 不能超过 ${maxLength} 个字符`);
  return result || null;
}

function publicationTimestamp(value) {
  const result = requiredText(value, "publish_at", 64);
  if (!/(?:Z|[+-]\d{2}:\d{2})$/.test(result) || Number.isNaN(Date.parse(result))) {
    throw new Error("publish_at 必须是带时区的 ISO 8601 日期时间");
  }
  return result;
}

function optionalTimestamp(value, name) {
  const result = optionalText(value, name, 64);
  if (result === null) return null;
  if (!/(?:Z|[+-]\d{2}:\d{2})$/.test(result) || Number.isNaN(Date.parse(result))) {
    throw new Error(`${name} 必须是带时区的 ISO 8601 日期时间或 null`);
  }
  return result;
}

function productionDate(value) {
  const result = requiredText(value, "publish_date", 10);
  const parsed = new Date(`${result}T00:00:00Z`);
  if (
    !/^\d{4}-\d{2}-\d{2}$/.test(result)
    || Number.isNaN(parsed.getTime())
    || parsed.toISOString().slice(0, 10) !== result
  ) {
    throw new Error("publish_date 必须是 YYYY-MM-DD 格式的有效日期");
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

async function listFinanceGeneratedImages(request, env) {
  const result = await env.DB.prepare(
    "SELECT id, caption, image_path FROM finance_generated_images ORDER BY id",
  ).all();
  return jsonResponse({ records: result.results || [] });
}

async function commitFinanceGeneratedImages(request, env) {
  const body = await request.json();
  const records = body.records;
  if (!Array.isArray(records) || records.length < 1 || records.length > 100) {
    throw new Error("records 必须是包含 1 到 100 条图片记录的数组");
  }
  const now = new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
  const saved = [];
  for (const item of records) {
    if (!item || typeof item !== "object") throw new Error("每条图片记录都必须是对象");
    const caption = requiredText(item.caption, "caption", 4000);
    const imagePath = requiredText(item.image_path, "image_path", 1000);
    const pathMatch = imagePath.match(/^data\/image_library_finance\/([1-9]\d*)\.png$/);
    if (!pathMatch) {
      throw new Error(`image_path 格式不正确：${imagePath}`);
    }
    const imageId = Number(pathMatch[1]);
    const occupied = await env.DB.prepare(
      "SELECT id, image_path FROM finance_generated_images WHERE id = ? OR image_path = ? LIMIT 1",
    ).bind(imageId, imagePath).first();
    if (occupied && (Number(occupied.id) !== imageId || String(occupied.image_path) !== imagePath)) {
      throw new Error(`图片编号 ${imageId} 已被其它路径占用，不能写入 ${imagePath}`);
    }
    const row = await env.DB.prepare(
      `INSERT INTO finance_generated_images(id, line, caption, image_path, created_at, updated_at)
       VALUES (?, 'finance_generated', ?, ?, ?, ?)
       ON CONFLICT(image_path) DO UPDATE SET caption = excluded.caption, updated_at = excluded.updated_at
       RETURNING id, caption, image_path`,
    ).bind(imageId, caption, imagePath, now, now).first();
    saved.push(row);
  }
  return jsonResponse({ records: saved }, 201);
}

async function listPublicationRecords(request, env) {
  const url = new URL(request.url);
  const businessLine = String(url.searchParams.get("business_line") || "").trim();
  const platform = String(url.searchParams.get("platform") || "").trim();
  const publishDate = String(url.searchParams.get("publish_date") || "").trim();
  const runId = String(url.searchParams.get("run_id") || "").trim();
  if (businessLine && !PUBLICATION_BUSINESS_LINES.includes(businessLine)) {
    throw new Error(`business_line 必须从 ${PUBLICATION_BUSINESS_LINES.join(", ")} 中选择`);
  }
  if (platform && !PUBLICATION_PLATFORMS.includes(platform)) {
    throw new Error(`platform 必须从 ${PUBLICATION_PLATFORMS.join(", ")} 中选择`);
  }
  if (publishDate) productionDate(publishDate);
  if (runId) requiredText(runId, "run_id", 200);
  const clauses = [];
  const values = [];
  if (businessLine) {
    clauses.push("business_line = ?");
    values.push(businessLine);
  }
  if (platform) {
    clauses.push("platform = ?");
    values.push(platform);
  }
  if (publishDate) {
    clauses.push("substr(publish_at, 1, 10) = ?");
    values.push(publishDate);
  }
  if (runId) {
    clauses.push("run_id = ?");
    values.push(runId);
  }
  const where = clauses.length ? `WHERE ${clauses.join(" AND ")}` : "";
  const statement = env.DB.prepare(
    `SELECT id, publication_id, run_id, business_line, platform, connector, account_id,
            content_part, title, publish_mode, publish_at, status, external_id, external_url,
            created_at, updated_at
     FROM publication_records ${where}
     ORDER BY publish_at DESC, id DESC LIMIT 500`,
  );
  const result = values.length ? await statement.bind(...values).all() : await statement.all();
  return jsonResponse({ records: result.results || [] });
}

async function listPublishingAccountGroups(request, env) {
  const url = new URL(request.url);
  const businessLine = String(url.searchParams.get("business_line") || "").trim();
  if (businessLine && !PUBLICATION_BUSINESS_LINES.includes(businessLine)) {
    throw new Error(`business_line 必须从 ${PUBLICATION_BUSINESS_LINES.join(", ")} 中选择`);
  }
  const where = businessLine ? "WHERE business_line = ? AND enabled = 1" : "WHERE enabled = 1";
  const groupStatement = env.DB.prepare(
    `SELECT code, name, business_line, enabled, created_at, updated_at
     FROM publishing_account_groups ${where}
     ORDER BY business_line, name`,
  );
  const groupResult = businessLine
    ? await groupStatement.bind(businessLine).all()
    : await groupStatement.all();
  const groups = groupResult.results || [];
  if (!groups.length) return jsonResponse({ groups: [], members: [] });
  const placeholders = groups.map(() => "?").join(",");
  const memberResult = await env.DB.prepare(
    `SELECT id, platform_account_id, group_code, platform, connector, account_ref, display_name,
            position, enabled, created_at, updated_at
     FROM publishing_account_group_members
     WHERE enabled = 1 AND group_code IN (${placeholders})
     ORDER BY group_code, position, platform, id`,
  ).bind(...groups.map((item) => item.code)).all();
  return jsonResponse({ groups, members: memberResult.results || [] });
}

function runDate(runId, fallback) {
  const matched = /^run-(\d{4})(\d{2})(\d{2})$/.exec(String(runId || ""));
  return matched ? `${matched[1]}-${matched[2]}-${matched[3]}` : String(fallback || "").slice(0, 10);
}

async function dashboardRecords(request, env) {
  if (!isDashboardAuthorized(request, env)) {
    return dashboardResponse({ error: { code: "INVALID_PIN", message: "PIN 不正确" } }, 401);
  }
  const url = new URL(request.url);
  const selectedDate = String(url.searchParams.get("date") || "").trim();
  if (selectedDate) productionDate(selectedDate);
  const outputStatement = selectedDate
    ? env.DB.prepare(
      `SELECT production_id, run_id, publish_date, business_line, content_kind,
              content_part, title, hashtags, source, local_path, r2_url, r2_expires_at
       FROM production_outputs WHERE publish_date = ?
       ORDER BY business_line, content_kind, content_part`,
    ).bind(selectedDate)
    : env.DB.prepare(
      `SELECT production_id, run_id, publish_date, business_line, content_kind,
              content_part, title, hashtags, source, local_path, r2_url, r2_expires_at
       FROM production_outputs ORDER BY publish_date DESC, business_line, content_kind, content_part
       LIMIT 1000`,
    );
  const publicationStatement = selectedDate
    ? env.DB.prepare(
      `SELECT publication_id, run_id, business_line, platform, content_part, title,
              publish_mode, publish_at, status, external_url
       FROM publication_records WHERE substr(publish_at, 1, 10) = ?
       ORDER BY business_line, title, content_part, platform`,
    ).bind(selectedDate)
    : env.DB.prepare(
      `SELECT publication_id, run_id, business_line, platform, content_part, title,
              publish_mode, publish_at, status, external_url
       FROM publication_records ORDER BY id DESC LIMIT 1000`,
    );
  const [outputResult, publicationResult] = await Promise.all([
    outputStatement.all(),
    publicationStatement.all(),
  ]);
  const byKey = new Map();
  const itemKey = (item) => [
    item.business_line,
    item.publish_date || runDate(item.run_id, item.publish_at),
    item.title,
    Number(item.content_part || 1),
  ].join("|");
  for (const output of outputResult.results || []) {
    const key = itemKey(output);
    const item = byKey.get(key) || {
      publish_date: output.publish_date,
      run_id: output.run_id,
      business_line: output.business_line,
      content_kind: output.content_kind,
      content_part: Number(output.content_part || 1),
      title: output.title,
      hashtags: output.hashtags || "",
      outputs: [],
      publications: [],
    };
    item.outputs.push({
      source: output.source,
      local_available: Boolean(output.local_path),
      r2_available: Boolean(output.r2_url),
      r2_url: output.r2_url || "",
      r2_expires_at: output.r2_expires_at || null,
      r2_expired: Boolean(
        output.r2_expires_at && Date.parse(output.r2_expires_at) <= Date.now()
      ),
    });
    byKey.set(key, item);
  }
  for (const publication of publicationResult.results || []) {
    const key = itemKey(publication);
    const item = byKey.get(key) || {
      publish_date: runDate(publication.run_id, publication.publish_at),
      run_id: publication.run_id,
      business_line: publication.business_line,
      content_kind: "",
      content_part: Number(publication.content_part || 1),
      title: publication.title,
      hashtags: "",
      outputs: [],
      publications: [],
    };
    item.publications.push({
      platform: publication.platform,
      publish_mode: publication.publish_mode,
      publish_at: publication.publish_at,
      status: publication.status,
      external_url: publication.external_url || "",
    });
    byKey.set(key, item);
  }
  const dates = new Map();
  for (const item of byKey.values()) {
    if (!dates.has(item.publish_date)) dates.set(item.publish_date, []);
    dates.get(item.publish_date).push(item);
  }
  return dashboardResponse({
    dates: [...dates.entries()]
      .sort(([left], [right]) => right.localeCompare(left))
      .map(([date, contents]) => ({
        date,
        contents: contents.sort((left, right) =>
          left.business_line.localeCompare(right.business_line)
          || left.title.localeCompare(right.title)
          || left.content_part - right.content_part),
      })),
  });
}

async function commitPublicationRecords(request, env) {
  const body = await request.json();
  const records = body.records;
  if (!Array.isArray(records) || records.length < 1 || records.length > 100) {
    throw new Error("records 必须是包含 1 到 100 条发布记录的数组");
  }
  const statements = records.map((item) => {
    if (!item || typeof item !== "object") throw new Error("每条发布记录都必须是对象");
    const publicationId = requiredText(item.publication_id, "publication_id", 200);
    const runId = requiredText(item.run_id, "run_id", 200);
    const businessLine = requiredText(item.business_line, "business_line", 64);
    const platform = requiredText(item.platform, "platform", 64);
    const connector = requiredText(item.connector, "connector", 64);
    const accountId = requiredText(item.account_id, "account_id", 500);
    const contentPart = positiveInteger(item.content_part || 1, "content_part", 1000);
    const title = requiredText(item.title, "title", 1000);
    const publishMode = requiredText(item.publish_mode, "publish_mode", 32);
    const publishAt = publicationTimestamp(item.publish_at);
    const status = requiredText(item.status, "status", 32);
    const externalId = optionalText(item.external_id, "external_id", 500);
    const externalUrl = optionalText(item.external_url, "external_url", 2000);
    if (!PUBLICATION_BUSINESS_LINES.includes(businessLine)) {
      throw new Error(`business_line 必须从 ${PUBLICATION_BUSINESS_LINES.join(", ")} 中选择`);
    }
    if (!PUBLICATION_PLATFORMS.includes(platform)) {
      throw new Error(`platform 必须从 ${PUBLICATION_PLATFORMS.join(", ")} 中选择`);
    }
    if (!PUBLICATION_MODES.includes(publishMode)) {
      throw new Error(`publish_mode 必须从 ${PUBLICATION_MODES.join(", ")} 中选择`);
    }
    if (!PUBLICATION_STATUSES.includes(status)) {
      throw new Error(`status 必须从 ${PUBLICATION_STATUSES.join(", ")} 中选择`);
    }
    if ((publishMode === "immediate") !== (status === "published")) {
      throw new Error("immediate 必须对应 published，scheduled 必须对应 scheduled");
    }
    return env.DB.prepare(
      `INSERT INTO publication_records(
         publication_id, run_id, business_line, platform, connector, account_id,
         content_part, title, publish_mode, publish_at, status, external_id, external_url
       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
       ON CONFLICT(business_line, title, platform, account_id, content_part) DO UPDATE SET
         publication_id = excluded.publication_id,
         run_id = excluded.run_id,
         connector = excluded.connector,
         publish_mode = excluded.publish_mode,
         publish_at = excluded.publish_at,
         status = excluded.status,
         external_id = excluded.external_id,
         external_url = excluded.external_url,
         updated_at = CURRENT_TIMESTAMP
       RETURNING id, publication_id, run_id, business_line, platform, connector, account_id,
                 content_part, title, publish_mode, publish_at, status, external_id, external_url,
                 created_at, updated_at`,
    ).bind(
      publicationId, runId, businessLine, platform, connector, accountId,
      contentPart, title, publishMode, publishAt, status, externalId, externalUrl,
    );
  });
  const results = await env.DB.batch(statements);
  return jsonResponse({ records: results.map((result) => result.results?.[0]).filter(Boolean) }, 201);
}

async function listProductionOutputs(request, env) {
  const url = new URL(request.url);
  const publishDate = String(url.searchParams.get("publish_date") || "").trim();
  const businessLine = String(url.searchParams.get("business_line") || "").trim();
  const source = String(url.searchParams.get("source") || "").trim();
  if (publishDate) productionDate(publishDate);
  if (businessLine && !PUBLICATION_BUSINESS_LINES.includes(businessLine)) {
    throw new Error(`business_line 必须从 ${PUBLICATION_BUSINESS_LINES.join(", ")} 中选择`);
  }
  if (source && !PRODUCTION_SOURCES.includes(source)) {
    throw new Error(`source 必须从 ${PRODUCTION_SOURCES.join(", ")} 中选择`);
  }
  const clauses = [];
  const values = [];
  if (publishDate) {
    clauses.push("publish_date = ?");
    values.push(publishDate);
  }
  if (businessLine) {
    clauses.push("business_line = ?");
    values.push(businessLine);
  }
  if (source) {
    clauses.push("source = ?");
    values.push(source);
  }
  const where = clauses.length ? `WHERE ${clauses.join(" AND ")}` : "";
  const statement = env.DB.prepare(
    `SELECT id, production_id, run_id, publish_date, business_line, content_kind,
            content_part, title, hashtags, source, local_path, r2_url, r2_expires_at, created_at, updated_at
     FROM production_outputs ${where}
     ORDER BY publish_date DESC, business_line, content_kind, content_part LIMIT 500`,
  );
  const result = values.length ? await statement.bind(...values).all() : await statement.all();
  return jsonResponse({ records: result.results || [] });
}

async function commitProductionOutputs(request, env) {
  const body = await request.json();
  const records = body.records;
  if (!Array.isArray(records) || records.length < 1 || records.length > 100) {
    throw new Error("records 必须是包含 1 到 100 条产物记录的数组");
  }
  const statements = records.map((item) => {
    if (!item || typeof item !== "object") throw new Error("每条产物记录都必须是对象");
    const productionId = requiredText(item.production_id, "production_id", 200);
    const runId = requiredText(item.run_id, "run_id", 200);
    const publishDate = productionDate(item.publish_date);
    const businessLine = requiredText(item.business_line, "business_line", 64);
    const contentKind = requiredText(item.content_kind, "content_kind", 100);
    const contentPart = positiveInteger(item.content_part || 1, "content_part", 1000);
    const title = requiredText(item.title, "title", 1000);
    const hashtags = optionalText(item.hashtags, "hashtags", 1000) || "";
    const source = requiredText(item.source, "source", 32);
    const localPath = optionalText(item.local_path, "local_path", 2000);
    const r2Url = optionalText(item.r2_url, "r2_url", 2000);
    const r2ExpiresAt = optionalTimestamp(item.r2_expires_at, "r2_expires_at");
    if (!PUBLICATION_BUSINESS_LINES.includes(businessLine)) {
      throw new Error(`business_line 必须从 ${PUBLICATION_BUSINESS_LINES.join(", ")} 中选择`);
    }
    if (!PRODUCTION_SOURCES.includes(source)) {
      throw new Error(`source 必须从 ${PRODUCTION_SOURCES.join(", ")} 中选择`);
    }
    if (!localPath && !r2Url) {
      throw new Error("local_path 和 r2_url 至少需要填写一个");
    }
    if (source === "github_workflow" && (localPath || !r2Url)) {
      throw new Error("github_workflow 产物只能记录最终 r2_url，不能记录 Runner 临时路径");
    }
    const expectedRunId = `run-${publishDate.replaceAll("-", "")}`;
    if (runId !== expectedRunId) {
      throw new Error(`run_id 必须与 publish_date 一致，期望 ${expectedRunId}`);
    }
    return env.DB.prepare(
      `INSERT INTO production_outputs(
         production_id, run_id, publish_date, business_line, content_kind,
         content_part, title, hashtags, source, local_path, r2_url, r2_expires_at
       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
       ON CONFLICT(source, business_line, run_id, content_kind, content_part) DO UPDATE SET
         production_id = excluded.production_id,
         publish_date = excluded.publish_date,
         title = excluded.title,
         hashtags = excluded.hashtags,
         local_path = COALESCE(excluded.local_path, production_outputs.local_path),
         r2_url = COALESCE(excluded.r2_url, production_outputs.r2_url),
         r2_expires_at = COALESCE(excluded.r2_expires_at, production_outputs.r2_expires_at),
         updated_at = CURRENT_TIMESTAMP
       RETURNING id, production_id, run_id, publish_date, business_line, content_kind,
                 content_part, title, hashtags, source, local_path, r2_url, r2_expires_at, created_at, updated_at`,
    ).bind(
      productionId, runId, publishDate, businessLine, contentKind,
      contentPart, title, hashtags, source, localPath, r2Url, r2ExpiresAt,
    );
  });
  const results = await env.DB.batch(statements);
  return jsonResponse({ records: results.map((result) => result.results?.[0]).filter(Boolean) }, 201);
}

async function listDouyinResearchIds(env) {
  const result = await env.DB.prepare(
    "SELECT aweme_id FROM douyin_research_contents ORDER BY created_at DESC",
  ).all();
  return jsonResponse({
    aweme_ids: (result.results || []).map((row) => String(row.aweme_id)),
  });
}

async function getDouyinResearchScriptStats(request, env) {
  const url = new URL(request.url);
  const collectionCode = requiredText(url.searchParams.get("collection_code"), "collection_code", 64);
  const workflow = requiredText(url.searchParams.get("workflow"), "workflow", 64);
  const reservationMinutes = positiveInteger(
    url.searchParams.get("reservation_minutes") || 120,
    "reservation_minutes",
    1440,
  );
  const checkedAt = new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
  const expiredBefore = new Date(Date.now() - reservationMinutes * 60000)
    .toISOString()
    .replace(/\.\d{3}Z$/, "Z");
  const stats = await env.DB.prepare(
    `SELECT
       COUNT(DISTINCT c.aweme_id) AS total_count,
       COUNT(DISTINCT CASE WHEN u.status = 'used' THEN c.aweme_id END) AS used_count,
       COUNT(DISTINCT CASE
         WHEN u.status = 'reserved' AND u.reserved_at >= ? THEN c.aweme_id
       END) AS reserved_count
     FROM douyin_research_contents c
     JOIN douyin_research_discoveries d ON d.aweme_id = c.aweme_id AND d.collection_code = ?
     LEFT JOIN douyin_research_script_usage u ON u.aweme_id = c.aweme_id AND u.workflow = ?`,
  ).bind(expiredBefore, collectionCode, workflow).first();
  const totalCount = Number(stats?.total_count || 0);
  const usedCount = Number(stats?.used_count || 0);
  const reservedCount = Number(stats?.reserved_count || 0);
  return jsonResponse({
    collection_code: collectionCode,
    workflow,
    reservation_minutes: reservationMinutes,
    total_count: totalCount,
    available_count: Math.max(0, totalCount - usedCount - reservedCount),
    reserved_count: reservedCount,
    used_count: usedCount,
    checked_at: checkedAt,
  });
}

async function reserveDouyinResearchScript(request, env) {
  const body = await request.json();
  const collectionCode = requiredText(body.collection_code, "collection_code", 64);
  const workflow = requiredText(body.workflow, "workflow", 64);
  const reservationMinutes = positiveInteger(body.reservation_minutes || 120, "reservation_minutes", 1440);
  const now = new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
  const expiredBefore = new Date(Date.now() - reservationMinutes * 60000).toISOString().replace(/\.\d{3}Z$/, "Z");
  await env.DB.prepare(
    `DELETE FROM douyin_research_script_usage
     WHERE workflow = ? AND status = 'reserved' AND reserved_at < ?`,
  ).bind(workflow, expiredBefore).run();

  const candidates = await env.DB.prepare(
    `SELECT c.aweme_id, c.caption, c.transcript_corrected, c.aweme_url, c.created_at
     FROM douyin_research_contents c
     WHERE EXISTS (
       SELECT 1 FROM douyin_research_discoveries d
       WHERE d.aweme_id = c.aweme_id AND d.collection_code = ?
     )
     AND NOT EXISTS (
       SELECT 1 FROM douyin_research_script_usage u
       WHERE u.aweme_id = c.aweme_id AND u.workflow = ?
     )
     ORDER BY c.created_at ASC, c.aweme_id ASC
     LIMIT 20`,
  ).bind(collectionCode, workflow).all();

  for (const candidate of candidates.results || []) {
    const reservationToken = crypto.randomUUID();
    const reserved = await env.DB.prepare(
      `INSERT INTO douyin_research_script_usage(
         aweme_id, workflow, status, reservation_token, reserved_at
       ) VALUES (?, ?, 'reserved', ?, ?)
       ON CONFLICT(aweme_id, workflow) DO NOTHING
       RETURNING aweme_id, workflow, status, reservation_token, reserved_at`,
    ).bind(candidate.aweme_id, workflow, reservationToken, now).first();
    if (reserved) {
      return jsonResponse({
        source: {
          aweme_id: String(candidate.aweme_id),
          caption: String(candidate.caption || ""),
          transcript: String(candidate.transcript_corrected || ""),
          aweme_url: String(candidate.aweme_url || ""),
          collection_code: collectionCode,
        },
        reservation: reserved,
        reservation_minutes: reservationMinutes,
      }, 201);
    }
  }

  const stats = await env.DB.prepare(
    `SELECT
       COUNT(DISTINCT c.aweme_id) AS total_count,
       COUNT(DISTINCT CASE WHEN u.status = 'used' THEN c.aweme_id END) AS used_count,
       COUNT(DISTINCT CASE WHEN u.status = 'reserved' THEN c.aweme_id END) AS reserved_count
     FROM douyin_research_contents c
     JOIN douyin_research_discoveries d ON d.aweme_id = c.aweme_id AND d.collection_code = ?
     LEFT JOIN douyin_research_script_usage u ON u.aweme_id = c.aweme_id AND u.workflow = ?`,
  ).bind(collectionCode, workflow).first();
  const totalCount = Number(stats?.total_count || 0);
  const usedCount = Number(stats?.used_count || 0);
  const reservedCount = Number(stats?.reserved_count || 0);
  if (totalCount > 0 && usedCount >= totalCount) {
    return errorResponse("DOUYIN_SCRIPTS_EXHAUSTED", "财经稿件库已全部使用", 409, {
      collection_code: collectionCode,
      total_count: totalCount,
      used_count: usedCount,
    });
  }
  if (reservedCount > 0) {
    return errorResponse("DOUYIN_SCRIPTS_BUSY", "财经稿件库中未使用的稿件当前均已被占用", 409, {
      collection_code: collectionCode,
      total_count: totalCount,
      used_count: usedCount,
      reserved_count: reservedCount,
    });
  }
  return errorResponse("DOUYIN_SCRIPTS_EMPTY", "财经稿件库没有可用稿件", 404, {
    collection_code: collectionCode,
    total_count: totalCount,
  });
}

async function markDouyinResearchScriptUsed(request, env) {
  const body = await request.json();
  const awemeId = requiredText(body.aweme_id, "aweme_id", 64);
  const workflow = requiredText(body.workflow, "workflow", 64);
  const reservationToken = requiredText(body.reservation_token, "reservation_token", 100);
  const runId = requiredText(body.run_id, "run_id", 100);
  const sourceHook = requiredText(body.source_hook, "source_hook", 2000);
  const source = await env.DB.prepare(
    "SELECT transcript_corrected FROM douyin_research_contents WHERE aweme_id = ?",
  ).bind(awemeId).first();
  if (!source || !String(source.transcript_corrected || "").startsWith(sourceHook)) {
    return errorResponse("DOUYIN_SCRIPT_HOOK_MISMATCH", "黄金钩子不是数据库原稿的原样开头", 409, {
      aweme_id: awemeId,
    });
  }
  const now = new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
  const updated = await env.DB.prepare(
    `UPDATE douyin_research_script_usage
     SET status = 'used', used_at = ?, run_id = ?
     WHERE aweme_id = ? AND workflow = ? AND status = 'reserved' AND reservation_token = ?
     RETURNING aweme_id, workflow, status, reservation_token, reserved_at, used_at, run_id`,
  ).bind(now, runId, awemeId, workflow, reservationToken).first();
  if (updated) {
    return jsonResponse({ record: updated, already_used: false });
  }
  const existing = await env.DB.prepare(
    `SELECT aweme_id, workflow, status, reservation_token, reserved_at, used_at, run_id
     FROM douyin_research_script_usage
     WHERE aweme_id = ? AND workflow = ?`,
  ).bind(awemeId, workflow).first();
  if (existing?.status === "used" && existing?.reservation_token === reservationToken) {
    return jsonResponse({ record: existing, already_used: true });
  }
  return errorResponse("DOUYIN_SCRIPT_RESERVATION_INVALID", "财经来源稿件的占用不存在、已过期或令牌不匹配", 409, {
    aweme_id: awemeId,
    workflow,
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
    if (request.method === "OPTIONS" && url.pathname === "/v1/dashboard/records") {
      return new Response(null, {
        status: 204,
        headers: {
          "Access-Control-Allow-Origin": "*",
          "Access-Control-Allow-Headers": "Content-Type, X-Dashboard-Pin",
          "Access-Control-Allow-Methods": "GET, OPTIONS",
        },
      });
    }
    if (request.method === "GET" && url.pathname === "/v1/dashboard/records") {
      try {
        return await dashboardRecords(request, env);
      } catch (error) {
        if (error instanceof Error && /必须|不能|格式/.test(error.message)) {
          return dashboardResponse({ error: { code: "INVALID_PARAMETER", message: error.message } }, 400);
        }
        console.error(error);
        return dashboardResponse({ error: { code: "D1_ERROR", message: "读取发布看板失败" } }, 500);
      }
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
      if (request.method === "GET" && url.pathname === "/v1/finance-generated-images") return await listFinanceGeneratedImages(request, env);
      if (request.method === "POST" && url.pathname === "/v1/finance-generated-images/commit") return await commitFinanceGeneratedImages(request, env);
      if (request.method === "GET" && url.pathname === "/v1/publication-records") return await listPublicationRecords(request, env);
      if (request.method === "POST" && url.pathname === "/v1/publication-records/commit") return await commitPublicationRecords(request, env);
      if (request.method === "GET" && url.pathname === "/v1/publishing-account-groups") return await listPublishingAccountGroups(request, env);
      if (request.method === "GET" && url.pathname === "/v1/production-outputs") return await listProductionOutputs(request, env);
      if (request.method === "POST" && url.pathname === "/v1/production-outputs/commit") return await commitProductionOutputs(request, env);
      if (request.method === "GET" && url.pathname === "/v1/douyin-research/ids") return await listDouyinResearchIds(env);
      if (request.method === "POST" && url.pathname === "/v1/douyin-research/commit") return await commitDouyinResearch(request, env);
      if (request.method === "GET" && url.pathname === "/v1/douyin-research/scripts/stats") {
        return await getDouyinResearchScriptStats(request, env);
      }
      if (request.method === "POST" && url.pathname === "/v1/douyin-research/scripts/reserve") return await reserveDouyinResearchScript(request, env);
      if (request.method === "POST" && url.pathname === "/v1/douyin-research/scripts/used") return await markDouyinResearchScriptUsed(request, env);
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
