const 活跃状态 = ["reserved", "completed", "published", "used"];

function 返回JSON(payload, status = 200) {
  return Response.json(payload, {
    status,
    headers: { "Cache-Control": "no-store" },
  });
}

function 返回错误(code, message, status = 400, details = {}) {
  return 返回JSON({ error: { code, message, details } }, status);
}

function 非空文本(value, name, maxLength = 500) {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} 必须是非空字符串`);
  }
  const result = value.trim();
  if (result.length > maxLength) {
    throw new Error(`${name} 不能超过 ${maxLength} 个字符`);
  }
  return result;
}

function 正整数(value, name, maximum = 3650) {
  const result = Number(value);
  if (!Number.isInteger(result) || result < 1 || result > maximum) {
    throw new Error(`${name} 必须是 1 到 ${maximum} 的整数`);
  }
  return result;
}

function 截止时间(days) {
  return new Date(Date.now() - days * 86400000).toISOString().replace(/\.\d{3}Z$/, "Z");
}

function 已鉴权(request, env) {
  const configured = String(env.DATA_API_TOKEN || "");
  const provided = request.headers.get("Authorization") || "";
  return configured.length >= 32 && provided === `Bearer ${configured}`;
}

async function 查询话题(request, env) {
  const url = new URL(request.url);
  const workflow = 非空文本(url.searchParams.get("workflow"), "workflow", 64);
  const days = 正整数(url.searchParams.get("days"), "days");
  const placeholders = 活跃状态.map(() => "?").join(",");
  const result = await env.DB.prepare(
    `SELECT id, workflow, topic, fingerprint, status, created_at, updated_at
     FROM topic_history
     WHERE workflow = ? AND created_at >= ? AND status IN (${placeholders})
     ORDER BY created_at DESC`,
  ).bind(workflow, 截止时间(days), ...活跃状态).all();
  return 返回JSON({ records: result.results || [] });
}

async function 占用话题(request, env) {
  const body = await request.json();
  const workflow = 非空文本(body.workflow, "workflow", 64);
  const topic = 非空文本(body.topic, "topic", 500);
  const fingerprint = 非空文本(body.fingerprint, "fingerprint", 64);
  const days = 正整数(body.days, "days");
  if (!/^[a-f0-9]{64}$/.test(fingerprint)) {
    throw new Error("fingerprint 必须是 64 位小写十六进制 SHA-256");
  }
  const placeholders = 活跃状态.map(() => "?").join(",");
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
    workflow, fingerprint, 截止时间(days), ...活跃状态,
  ).first();
  if (inserted) {
    return 返回JSON({ record: inserted }, 201);
  }
  const duplicate = await env.DB.prepare(
    `SELECT id, workflow, topic, fingerprint, status, created_at, updated_at
     FROM topic_history
     WHERE workflow = ? AND fingerprint = ? AND created_at >= ?
     AND status IN (${placeholders})
     ORDER BY created_at DESC LIMIT 1`,
  ).bind(workflow, fingerprint, 截止时间(days), ...活跃状态).first();
  return 返回错误("DUPLICATE_TOPIC", `话题在最近 ${days} 天内已经使用：${duplicate?.topic || topic}`, 409, {
    duplicate_record: duplicate,
    days,
  });
}

async function 查询最近单词(request, env) {
  const url = new URL(request.url);
  const days = 正整数(url.searchParams.get("days"), "days");
  const result = await env.DB.prepare(
    `SELECT normalized_english, MAX(english) AS english, MAX(created_at) AS last_used_at
     FROM language_learning_words
     WHERE created_at >= ?
     GROUP BY normalized_english
     ORDER BY last_used_at DESC, normalized_english`,
  ).bind(截止时间(days)).all();
  return 返回JSON({ words: (result.results || []).map((row) => row.english) });
}

function 校验单词条目(rawEntries) {
  if (!Array.isArray(rawEntries) || rawEntries.length !== 10) {
    throw new Error("entries 必须包含 10 个单词对象");
  }
  const entries = rawEntries.map((entry) => ({
    english: 非空文本(entry?.english, "english", 200),
    normalized_english: 非空文本(entry?.normalized_english, "normalized_english", 200),
    word_json: 非空文本(entry?.word_json, "word_json", 20000),
  }));
  if (new Set(entries.map((entry) => entry.normalized_english)).size !== 10) {
    throw new Error("entries 必须包含 10 个不同的英语单词");
  }
  return entries;
}

async function 校验并记录单词(request, env) {
  const body = await request.json();
  const workflow = 非空文本(body.workflow, "workflow", 64);
  const runId = 非空文本(body.run_id, "run_id", 64);
  const topic = 非空文本(body.topic, "topic", 500);
  const historyDays = 正整数(body.history_days, "history_days");
  const minimumNewWords = 正整数(body.minimum_new_words, "minimum_new_words", 10);
  const entries = 校验单词条目(body.entries);
  const runMatch = /^run-(\d{6,})$/.exec(runId);
  if (!runMatch) {
    throw new Error("run_id 格式不正确");
  }
  const topicRecordId = Number(runMatch[1]);
  const topicRecord = await env.DB.prepare(
    "SELECT workflow, topic FROM topic_history WHERE id = ?",
  ).bind(topicRecordId).first();
  if (!topicRecord) {
    return 返回错误("WORD_HISTORY_ERROR", `run_id ${runId} 对应的话题记录不存在`, 409);
  }
  if (topicRecord.workflow !== workflow || String(topicRecord.topic).trim() !== topic) {
    return 返回错误("WORD_HISTORY_ERROR", `run_id ${runId} 与主题不匹配，禁止记录词表`, 409);
  }
  const existing = await env.DB.prepare(
    "SELECT normalized_english FROM language_learning_words WHERE run_id = ? ORDER BY normalized_english",
  ).bind(runId).all();
  if ((existing.results || []).length) {
    const recorded = (existing.results || []).map((row) => row.normalized_english).sort();
    const incoming = entries.map((entry) => entry.normalized_english).sort();
    if (JSON.stringify(recorded) !== JSON.stringify(incoming)) {
      return 返回错误("WORD_HISTORY_ERROR", `run_id ${runId} 已记录过另一份词表，禁止覆盖`, 409);
    }
    return 返回JSON({
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
      截止时间(historyDays), entriesJson, entries.length - minimumNewWords,
    ).run();
  } catch (error) {
    const raced = await env.DB.prepare(
      "SELECT normalized_english FROM language_learning_words WHERE run_id = ?",
    ).bind(runId).all();
    if ((raced.results || []).length === entries.length) {
      return 返回JSON({
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
    ).bind(截止时间(historyDays), entriesJson).all();
    const repeatedSet = new Set((recent.results || []).map((row) => row.normalized_english));
    const repeatedWords = entries.filter((entry) => repeatedSet.has(entry.normalized_english)).map((entry) => entry.english);
    return 返回错误(
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
  ).bind(截止时间(historyDays), runId, entriesJson).all();
  const repeatedSet = new Set((recent.results || []).map((row) => row.normalized_english));
  const repeatedWords = entries.filter((entry) => repeatedSet.has(entry.normalized_english)).map((entry) => entry.english);
  return 返回JSON({
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

async function 查询图库(request, env) {
  const url = new URL(request.url);
  const line = 非空文本(url.searchParams.get("line"), "line", 64);
  if (!/^[a-z][a-z0-9_]{0,63}$/.test(line)) {
    throw new Error("line 格式不正确");
  }
  const result = await env.DB.prepare(
    "SELECT id, caption, image_path FROM image_library WHERE line = ? ORDER BY id",
  ).bind(line).all();
  return 返回JSON({ records: result.results || [] });
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
    if (!已鉴权(request, env)) {
      return 返回错误("UNAUTHORIZED", "鉴权失败", 401);
    }
    try {
      if (request.method === "GET" && url.pathname === "/v1/topics") return await 查询话题(request, env);
      if (request.method === "POST" && url.pathname === "/v1/topics/reserve") return await 占用话题(request, env);
      if (request.method === "GET" && url.pathname === "/v1/words/recent") return await 查询最近单词(request, env);
      if (request.method === "POST" && url.pathname === "/v1/words/validate-and-record") return await 校验并记录单词(request, env);
      if (request.method === "GET" && url.pathname === "/v1/images") return await 查询图库(request, env);
      return 返回错误("NOT_FOUND", "接口不存在", 404);
    } catch (error) {
      if (error instanceof SyntaxError) {
        return 返回错误("INVALID_JSON", "请求体不是有效 JSON", 400);
      }
      if (error instanceof Error && /必须|不能|格式/.test(error.message)) {
        return 返回错误("INVALID_PARAMETER", error.message, 400);
      }
      console.error(error);
      return 返回错误("D1_ERROR", "Cloudflare D1 操作失败，请检查 Worker 日志", 500);
    }
  },
};
