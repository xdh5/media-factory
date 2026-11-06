import { jsonResponse, errorResponse, requiredText, positiveInteger, productionDate, cutoffTimestamp } from "./api-common.mjs";

function languageLearningPack(value) {
  if (!value || typeof value !== "object") throw new Error("词包必须是对象");
  const packId = requiredText(value.pack_id, "pack_id", 100);
  const topic = requiredText(value.topic, "topic", 200);
  if (!/^[A-Za-z]+$/.test(topic)) throw new Error("topic 必须是不含空格的英文单词");
  if (!value.words || typeof value.words !== "object") throw new Error("words 必须是词表对象");
  for (const mode of ["en-zh", "en-ko"]) {
    if (!Array.isArray(value.words[mode]) || value.words[mode].length !== 10) throw new Error(`words.${mode} 必须正好包含 10 个单词`);
  }
  if (!Array.isArray(value.image_urls) || value.image_urls.length !== 10) throw new Error("image_urls 必须包含十张已验收透明主体图地址");
  const imageUrls = value.image_urls.map((item, index) => {
    const url = requiredText(item, `image_urls[${index}]`, 2000);
    if (!/^https:\/\//.test(url)) throw new Error(`image_urls[${index}] 必须是 https 地址`);
    return url;
  });
  return { packId, topic, words: value.words, imageUrls };
}

function languageLearningPackRecord(row) {
  return { ...row, status: row.used_at ? 'used' : row.status === 'claimed' ? 'reserved' : 'ready', words: JSON.parse(row.words_json || "{}"), image_urls: JSON.parse(row.image_urls_json || "[]"), words_json: undefined, image_urls_json: undefined };
}

async function commitLanguageLearningPack(request, env) {
  const pack = languageLearningPack((await request.json()).pack);
  const entries = validateWordEntries(pack.words["en-zh"].map((word, index) => {
    const english = requiredText(word.english, "english", 200);
    const normalized = english.normalize("NFKC").toLowerCase().replaceAll("’", "'").replace(/\s+/g, " ").trim();
    const korean = pack.words["en-ko"][index];
    if (String(korean?.english || "").normalize("NFKC").toLowerCase().trim() !== normalized) throw new Error("双语词表必须按相同英语单词排序");
    return { english, normalized_english: normalized, word_json: JSON.stringify({ english, normalized_english: normalized, modes: { "en-zh": word, "en-ko": korean } }) };
  }));
  const now = new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
  const recent = await env.DB.prepare(
    `SELECT COUNT(DISTINCT normalized_english) AS count FROM language_learning_words
     WHERE created_at >= ? AND run_id <> ? AND normalized_english IN
     (SELECT json_extract(value, '$.normalized_english') FROM json_each(?))`,
  ).bind(cutoffTimestamp(100), pack.packId, JSON.stringify(entries)).first();
  if (Number(recent?.count || 0) > 5) return errorResponse("VOCABULARY_REUSE_LIMIT", "词包最近 100 天重复单词超过 5 个，请重新选词", 409);
  const results = await env.DB.batch([env.DB.prepare(
    `INSERT INTO language_learning_packs(pack_id, topic, words_json, image_urls_json, status) VALUES (?, ?, ?, ?, 'ready')
     ON CONFLICT(pack_id) DO UPDATE SET topic = excluded.topic, words_json = excluded.words_json, image_urls_json = excluded.image_urls_json, status = 'ready', run_id = NULL, publish_date = NULL, claimed_at = NULL, updated_at = CURRENT_TIMESTAMP
     WHERE language_learning_packs.status = 'ready' RETURNING *`,
  ).bind(pack.packId, pack.topic, JSON.stringify(pack.words), JSON.stringify(pack.imageUrls)),
  // 预制词包仅建立词库关联记录，不占用正式成片话题。
  env.DB.prepare(`INSERT INTO topic_history(workflow, topic, fingerprint, status, publication_id, created_at, updated_at)
    SELECT 'language_learning', ?, ?, 'prepared', ?, ?, ?
    WHERE EXISTS (SELECT 1 FROM language_learning_packs WHERE pack_id = ? AND status = 'ready')
    ON CONFLICT(publication_id) WHERE publication_id IS NOT NULL DO UPDATE SET topic = excluded.topic, updated_at = excluded.updated_at`)
    .bind(pack.topic, pack.packId, pack.packId, now, now, pack.packId),
  env.DB.prepare(`DELETE FROM language_learning_words WHERE run_id = ?
    AND EXISTS (SELECT 1 FROM language_learning_packs WHERE pack_id = ? AND status = 'ready')`).bind(pack.packId, pack.packId),
  env.DB.prepare(`INSERT INTO language_learning_words(run_id, topic_record_id, topic, english, normalized_english, word_json, created_at)
    SELECT ?, (SELECT id FROM topic_history WHERE publication_id = ?), ?,
    json_extract(value, '$.english'), json_extract(value, '$.normalized_english'), json_extract(value, '$.word_json'), ?
    FROM json_each(?) WHERE EXISTS (SELECT 1 FROM language_learning_packs WHERE pack_id = ? AND status = 'ready')`)
    .bind(pack.packId, pack.packId, pack.topic, now, JSON.stringify(entries), pack.packId)]);
  const row = results[0]?.results?.[0];
  if (!row) return errorResponse("LANGUAGE_PACK_ALREADY_CLAIMED", "词包已经被 GitHub 领取，不能覆盖", 409, { pack_id: pack.packId });
  return jsonResponse({ pack: languageLearningPackRecord(row) }, 201);
}

async function claimLanguageLearningPack(request, env) {
  const body = await request.json();
  const runId = requiredText(body.run_id, "run_id", 100);
  const publishDate = productionDate(body.publish_date);
  const now = new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
  await env.DB.prepare(
    "UPDATE language_learning_packs SET status = 'ready', run_id = NULL, publish_date = NULL, claimed_at = NULL, reservation_expires_at = NULL, updated_at = CURRENT_TIMESTAMP WHERE status = 'claimed' AND used_at IS NULL AND reservation_expires_at <= ?",
  ).bind(now).run();
  const existing = await env.DB.prepare(
    "SELECT * FROM language_learning_packs WHERE run_id = ? AND publish_date = ? ORDER BY claimed_at, pack_id LIMIT 1",
  ).bind(runId, publishDate).first();
  if (existing) return jsonResponse({ pack: languageLearningPackRecord(existing) });
  const selected = await env.DB.prepare("SELECT * FROM language_learning_packs WHERE status = 'ready' AND json_array_length(image_urls_json) = 10 ORDER BY created_at, pack_id LIMIT 1").first();
  if (!selected) return errorResponse("LANGUAGE_PACKS_EMPTY", "没有可用的已验收语言词包，请先让 Agent 生成并提交词包", 409);
  const expiresAt = new Date(Date.now() + 7 * 3600000).toISOString().replace(/\.\d{3}Z$/, "Z");
  const claimed = await env.DB.prepare(
    `UPDATE language_learning_packs SET status = 'claimed', run_id = ?, publish_date = ?, claimed_at = ?, reservation_expires_at = ?, updated_at = CURRENT_TIMESTAMP WHERE pack_id = ? AND status = 'ready' AND NOT EXISTS (SELECT 1 FROM language_learning_packs WHERE run_id = ? AND publish_date = ?) RETURNING *`,
  ).bind(runId, publishDate, now, expiresAt, selected.pack_id, runId, publishDate).first();
  if (!claimed) return errorResponse("LANGUAGE_PACK_CLAIM_CONFLICT", "词包刚被其他生产任务领取，请重试", 409);
  return jsonResponse({ pack: languageLearningPackRecord(claimed) });
}

async function releaseLanguageLearningPack(request, env) {
  const body = await request.json();
  const runId = requiredText(body.run_id, "run_id", 100);
  const publishDate = productionDate(body.publish_date);
  const result = await env.DB.prepare(
    "UPDATE language_learning_packs SET status = 'ready', run_id = NULL, publish_date = NULL, claimed_at = NULL, reservation_expires_at = NULL, updated_at = CURRENT_TIMESTAMP WHERE run_id = ? AND publish_date = ? AND status = 'claimed' AND used_at IS NULL RETURNING pack_id",
  ).bind(runId, publishDate).all();
  return jsonResponse({ released_pack_ids: (result.results || []).map(row => row.pack_id) });
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

async function listLanguageLearningPackTopics(env) {
  const result = await env.DB.prepare(
    "SELECT DISTINCT lower(trim(topic)) AS topic FROM language_learning_packs ORDER BY topic",
  ).all();
  return jsonResponse({ topics: result.results.map((row) => row.topic) });
}

export { validateWordEntries, commitLanguageLearningPack, claimLanguageLearningPack, releaseLanguageLearningPack, listRecentWords, validateAndRecordWords, listLanguageLearningPackTopics };
