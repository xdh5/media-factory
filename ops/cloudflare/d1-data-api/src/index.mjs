import { jsonResponse, errorResponse, requiredText, positiveInteger, productionDate, cutoffTimestamp } from "./api-common.mjs";
import { handleDashboard } from "./dashboard.mjs";
import { listPublicationRecords, deletePublicationRecords, listPublishingAccountGroups, commitPublicationRecords, listProductionOutputs, deleteProductionOutputs, commitProductionOutputs } from "./publication-records.mjs";
import { listFinanceGeneratedImages, commitFinanceGeneratedImages, listFinanceSourceAuthors, addFinanceSourceAuthor, removeFinanceSourceAuthor, listFinanceRejectedAwemes, rejectFinanceAweme, listDouyinResearchIds, getDouyinResearchScriptStats, reserveDouyinResearchScript, markDouyinResearchScriptUsed, commitDouyinResearch } from "./finance-data.mjs";
import { validateWordEntries, commitLanguageLearningPack, claimLanguageLearningPack, releaseLanguageLearningPack, listRecentWords, validateAndRecordWords, listLanguageLearningPackTopics } from "./language-learning-data.mjs";

import { listFinanceEditorialDrafts, commitFinanceEditorialDrafts } from "./finance-editorial.mjs";

const ACTIVE_STATUSES = ["reserved", "completed", "published", "used"];
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
       AND NOT EXISTS (SELECT 1 FROM language_learning_packs p WHERE p.pack_id = language_learning_words.run_id AND ('language_learning:' || p.run_id) = ?)
       AND normalized_english IN (
         SELECT json_extract(value, '$.normalized_english') FROM json_each(?)
       )`,
    ).bind(cutoffTimestamp(historyDays), publicationId, entriesJson).all();
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

async function listScenarioQuizQuestions(request, env) {
  const url = new URL(request.url);
  const days = positiveInteger(url.searchParams.get("days") || "30", "days", 3650);
  const result = await env.DB.prepare(
    `SELECT id, run_id, topic_record_id, topic, category, scene_title, scenario,
            option_a, option_b, option_c, option_d, result_a, result_b, result_c, result_d,
            image_keywords_json, status, publish_date, created_at, updated_at
     FROM scenario_quiz_questions
     WHERE created_at >= ?
     ORDER BY created_at DESC`,
  ).bind(cutoffTimestamp(days)).all();
  return jsonResponse({
    records: (result.results || []).map((row) => ({
      ...row,
      image_keywords: JSON.parse(row.image_keywords_json || "[]"),
      image_keywords_json: undefined,
    })),
  });
}

async function commitScenarioQuizQuestion(request, env) {
  const body = await request.json();
  const item = body.record;
  if (!item || typeof item !== "object") throw new Error("record 必须是对象");
  const runId = requiredText(item.run_id, "run_id", 100);
  const topicRecordId = positiveInteger(item.topic_record_id, "topic_record_id", 2147483647);
  const topic = requiredText(item.topic, "topic", 500);
  const category = requiredText(item.category, "category", 32);
  if (!["finance", "success", "human_nature"].includes(category)) {
    throw new Error("category 必须从 finance、success、human_nature 中选择");
  }
  const imageKeywords = item.image_keywords;
  if (!Array.isArray(imageKeywords) || !imageKeywords.length || imageKeywords.length > 20) {
    throw new Error("image_keywords 必须是包含 1 到 20 项的数组");
  }
  const normalizedKeywords = imageKeywords.map((value, index) =>
    requiredText(value, `image_keywords[${index}]`, 100));
  const status = String(item.status || "reserved").trim();
  if (!["reserved", "used", "rejected"].includes(status)) {
    throw new Error("status 必须从 reserved、used、rejected 中选择");
  }
  const publishDate = productionDate(item.publish_date);
  const values = {
    sceneTitle: requiredText(item.scene_title, "scene_title", 200),
    scenario: requiredText(item.scenario, "scenario", 4000),
    optionA: requiredText(item.option_a, "option_a", 500),
    optionB: requiredText(item.option_b, "option_b", 500),
    optionC: requiredText(item.option_c, "option_c", 500),
    optionD: requiredText(item.option_d, "option_d", 500),
    resultA: requiredText(item.result_a, "result_a", 2000),
    resultB: requiredText(item.result_b, "result_b", 2000),
    resultC: requiredText(item.result_c, "result_c", 2000),
    resultD: requiredText(item.result_d, "result_d", 2000),
  };
  const row = await env.DB.prepare(
    `INSERT INTO scenario_quiz_questions(
       run_id, topic_record_id, topic, category, scene_title, scenario,
       option_a, option_b, option_c, option_d, result_a, result_b, result_c, result_d,
       image_keywords_json, status, publish_date
     ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
     ON CONFLICT(run_id) DO UPDATE SET
       topic_record_id = excluded.topic_record_id,
       topic = excluded.topic,
       category = excluded.category,
       scene_title = excluded.scene_title,
       scenario = excluded.scenario,
       option_a = excluded.option_a,
       option_b = excluded.option_b,
       option_c = excluded.option_c,
       option_d = excluded.option_d,
       result_a = excluded.result_a,
       result_b = excluded.result_b,
       result_c = excluded.result_c,
       result_d = excluded.result_d,
       image_keywords_json = excluded.image_keywords_json,
       status = excluded.status,
       publish_date = excluded.publish_date,
       updated_at = CURRENT_TIMESTAMP
     RETURNING id, run_id, topic_record_id, topic, category, scene_title, scenario,
               option_a, option_b, option_c, option_d, result_a, result_b, result_c, result_d,
               image_keywords_json, status, publish_date, created_at, updated_at`,
  ).bind(
    runId, topicRecordId, topic, category, values.sceneTitle, values.scenario,
    values.optionA, values.optionB, values.optionC, values.optionD,
    values.resultA, values.resultB, values.resultC, values.resultD,
    JSON.stringify(normalizedKeywords), status, publishDate,
  ).first();
  return jsonResponse({
    record: {
      ...row,
      image_keywords: JSON.parse(row.image_keywords_json || "[]"),
      image_keywords_json: undefined,
    },
  }, 201);
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
    const dashboard = await handleDashboard(request, env, url);
    if (dashboard) return dashboard;
    if (!isAuthorized(request, env)) {
      return errorResponse("UNAUTHORIZED", "鉴权失败", 401);
    }
    try {
      if (request.method === "GET" && url.pathname === "/v1/topics") return await listTopics(request, env);
      if (request.method === "POST" && url.pathname === "/v1/topics/reserve") return await reserveTopic(request, env);
      if (request.method === "POST" && url.pathname === "/v1/publications/commit") return await commitPublication(request, env);
      if (request.method === "GET" && url.pathname === "/v1/words/recent") return await listRecentWords(request, env);
      if (request.method === "POST" && url.pathname === "/v1/words/validate-and-record") return await validateAndRecordWords(request, env);
      if (request.method === "GET" && url.pathname === "/v1/language-learning-packs/topics") return await listLanguageLearningPackTopics(env);
      if (request.method === "POST" && url.pathname === "/v1/language-learning-packs/commit") return await commitLanguageLearningPack(request, env);
      if (request.method === "POST" && url.pathname === "/v1/language-learning-packs/claim") return await claimLanguageLearningPack(request, env);
      if (request.method === "POST" && url.pathname === "/v1/language-learning-packs/release") return await releaseLanguageLearningPack(request, env);
      if (request.method === "GET" && url.pathname === "/v1/finance-generated-images") return await listFinanceGeneratedImages(request, env);
      if (request.method === "POST" && url.pathname === "/v1/finance-generated-images/commit") return await commitFinanceGeneratedImages(request, env);
      if (request.method === "GET" && url.pathname === "/v1/scenario-quiz-questions") return await listScenarioQuizQuestions(request, env);
      if (request.method === "POST" && url.pathname === "/v1/scenario-quiz-questions/commit") return await commitScenarioQuizQuestion(request, env);
      if (request.method === "GET" && url.pathname === "/v1/publication-records") return await listPublicationRecords(request, env);
      if (request.method === "DELETE" && url.pathname === "/v1/publication-records") return await deletePublicationRecords(request, env);
      if (request.method === "POST" && url.pathname === "/v1/publication-records/commit") return await commitPublicationRecords(request, env);
      if (request.method === "GET" && url.pathname === "/v1/publishing-account-groups") return await listPublishingAccountGroups(request, env);
      if (request.method === "GET" && url.pathname === "/v1/production-outputs") return await listProductionOutputs(request, env);
      if (request.method === "DELETE" && url.pathname === "/v1/production-outputs") return await deleteProductionOutputs(request, env);
      if (request.method === "POST" && url.pathname === "/v1/production-outputs/commit") return await commitProductionOutputs(request, env);
      if (request.method === "GET" && url.pathname === "/v1/finance-editorial-drafts") return await listFinanceEditorialDrafts(request, env);
      if (request.method === "POST" && url.pathname === "/v1/finance-editorial-drafts") return await commitFinanceEditorialDrafts(request, env);
      if (request.method === "GET" && url.pathname === "/v1/finance-source-authors") {
        return await listFinanceSourceAuthors(env);
      }
      if (request.method === "POST" && url.pathname === "/v1/finance-source-authors") {
        return await addFinanceSourceAuthor(request, env);
      }
      if (request.method === "DELETE" && url.pathname === "/v1/finance-source-authors") {
        return await removeFinanceSourceAuthor(request, env);
      }
      if (request.method === "GET" && url.pathname === "/v1/finance-rejected-awemes") {
        return await listFinanceRejectedAwemes(env);
      }
      if (request.method === "POST" && url.pathname === "/v1/finance-rejected-awemes") {
        return await rejectFinanceAweme(request, env);
      }
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
