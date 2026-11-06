import { jsonResponse, errorResponse, requiredText, positiveInteger, optionalText } from "./api-common.mjs";

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

function financeSourceAuthor(row) {
  return {
    sec_user_id: String(row.sec_user_id),
    profile_url: String(row.profile_url),
    display_name: String(row.display_name || ""),
    created_at: String(row.created_at || ""),
    updated_at: String(row.updated_at || ""),
  };
}

function financeSourceAuthorId(value) {
  const secUserId = requiredText(value, "sec_user_id", 128);
  if (!/^[A-Za-z0-9_-]{8,128}$/.test(secUserId)) {
    throw new Error("sec_user_id 格式不正确");
  }
  return secUserId;
}

async function listFinanceSourceAuthors(env) {
  const result = await env.DB.prepare(
    `SELECT sec_user_id, profile_url, display_name, created_at, updated_at
     FROM finance_source_authors
     ORDER BY created_at ASC, sec_user_id ASC`,
  ).all();
  const authors = (result.results || []).map(financeSourceAuthor);
  return jsonResponse({ authors, author_count: authors.length });
}

async function addFinanceSourceAuthor(request, env) {
  const body = await request.json();
  const secUserId = financeSourceAuthorId(body.sec_user_id);
  const profileUrl = requiredText(body.profile_url, "profile_url", 1000);
  if (profileUrl !== `https://www.douyin.com/user/${secUserId}`) {
    throw new Error("profile_url 必须是该作者的抖音主页链接");
  }
  const displayName = optionalText(body.display_name, "display_name", 100) || "";
  const now = new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
  const record = await env.DB.prepare(
    `INSERT INTO finance_source_authors(
       sec_user_id, profile_url, display_name, created_at, updated_at
     ) VALUES (?, ?, ?, ?, ?)
     ON CONFLICT(sec_user_id) DO UPDATE SET
       profile_url = excluded.profile_url,
       display_name = CASE
         WHEN excluded.display_name != '' THEN excluded.display_name
         ELSE finance_source_authors.display_name
       END,
       updated_at = excluded.updated_at
     RETURNING sec_user_id, profile_url, display_name, created_at, updated_at`,
  ).bind(secUserId, profileUrl, displayName, now, now).first();
  return jsonResponse({ author: financeSourceAuthor(record) }, 201);
}

async function removeFinanceSourceAuthor(request, env) {
  const body = await request.json();
  const secUserId = financeSourceAuthorId(body.sec_user_id);
  const record = await env.DB.prepare(
    `DELETE FROM finance_source_authors
     WHERE sec_user_id = ?
     RETURNING sec_user_id, profile_url, display_name, created_at, updated_at`,
  ).bind(secUserId).first();
  if (!record) {
    return errorResponse("FINANCE_AUTHOR_NOT_FOUND", "财经作者不在名单中", 404, {
      sec_user_id: secUserId,
    });
  }
  return jsonResponse({ author: financeSourceAuthor(record) });
}

async function listFinanceRejectedAwemes(env) {
  const result = await env.DB.prepare(
    "SELECT aweme_id FROM finance_rejected_awemes ORDER BY created_at DESC",
  ).all();
  return jsonResponse({
    aweme_ids: (result.results || []).map((row) => String(row.aweme_id)),
  });
}

async function rejectFinanceAweme(request, env) {
  const body = await request.json();
  const awemeId = requiredText(body.aweme_id, "aweme_id", 64);
  if (!/^\d+$/.test(awemeId)) {
    throw new Error("aweme_id 格式不正确");
  }
  const reason = requiredText(body.reason, "reason", 16);
  if (reason !== "ad") {
    throw new Error("reason 只能是 ad");
  }
  const now = new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
  const record = await env.DB.prepare(
    `INSERT INTO finance_rejected_awemes(aweme_id, reason, created_at)
     VALUES (?, ?, ?)
     ON CONFLICT(aweme_id) DO NOTHING
     RETURNING aweme_id, reason, created_at`,
  ).bind(awemeId, reason, now).first();
  return jsonResponse({
    aweme_id: awemeId,
    reason,
    already_rejected: !record,
  }, record ? 201 : 200);
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
       COUNT(DISTINCT CASE WHEN (u.aweme_id IS NULL OR (u.status = 'reserved' AND u.reserved_at < ?)) AND NOT EXISTS (
         SELECT 1 FROM finance_editorial_drafts e WHERE e.aweme_id = c.aweme_id AND e.source_transcript = c.transcript_corrected
       ) THEN c.aweme_id END) AS pending_editorial_count,
       COUNT(DISTINCT CASE
         WHEN u.status = 'reserved' AND u.reserved_at >= ? THEN c.aweme_id
       END) AS reserved_count
     FROM douyin_research_contents c
     JOIN douyin_research_discoveries d ON d.aweme_id = c.aweme_id AND d.collection_code = ?
     LEFT JOIN douyin_research_script_usage u ON u.aweme_id = c.aweme_id AND u.workflow = ?`,
  ).bind(expiredBefore, expiredBefore, collectionCode, workflow).first();
  const totalCount = Number(stats?.total_count || 0);
  const usedCount = Number(stats?.used_count || 0);
  const reservedCount = Number(stats?.reserved_count || 0);
  const pendingEditorialCount = Number(stats?.pending_editorial_count || 0);
  return jsonResponse({
    collection_code: collectionCode,
    workflow,
    reservation_minutes: reservationMinutes,
    total_count: totalCount,
    available_count: Math.max(0, totalCount - usedCount - reservedCount - pendingEditorialCount),
    pending_editorial_count: pendingEditorialCount,
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
    `SELECT c.aweme_id, c.caption, c.transcript_corrected, c.aweme_url, c.created_at, e.content_json
     FROM douyin_research_contents c
     JOIN finance_editorial_drafts e ON e.aweme_id = c.aweme_id AND e.source_transcript = c.transcript_corrected
     WHERE EXISTS (
       SELECT 1 FROM douyin_research_discoveries d
       WHERE d.aweme_id = c.aweme_id AND d.collection_code = ?
     )
     AND NOT EXISTS (
       SELECT 1 FROM douyin_research_script_usage u
       WHERE u.aweme_id = c.aweme_id AND u.workflow = ?
     )
     AND NOT EXISTS (
       SELECT 1 FROM topic_history t WHERE t.workflow = 'finance'
       AND t.topic = json_extract(e.content_json, '$.topic')
       AND t.status IN ('reserved', 'completed', 'published', 'used')
       AND t.created_at >= datetime('now', '-30 days')
     )
     ORDER BY RANDOM()
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
          editorial: JSON.parse(candidate.content_json),
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

export { listFinanceGeneratedImages, commitFinanceGeneratedImages, listFinanceSourceAuthors, addFinanceSourceAuthor, removeFinanceSourceAuthor, listFinanceRejectedAwemes, rejectFinanceAweme, listDouyinResearchIds, getDouyinResearchScriptStats, reserveDouyinResearchScript, markDouyinResearchScriptUsed, commitDouyinResearch };
