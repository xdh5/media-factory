import { jsonResponse, requiredText, positiveInteger, optionalText, publicationTimestamp, optionalTimestamp, productionDate, PUBLICATION_BUSINESS_LINES, ACCOUNT_GROUP_BUSINESS_LINES, PUBLICATION_PLATFORMS, PUBLICATION_MODES, PUBLICATION_STATUSES, PRODUCTION_SOURCES } from "./api-common.mjs";

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

async function deletePublicationRecords(request, env) {
  const body = await request.json();
  const recordIds = body.record_ids;
  if (!Array.isArray(recordIds) || recordIds.length < 1 || recordIds.length > 100) {
    throw new Error("record_ids 必须是包含 1 到 100 个记录 ID 的数组");
  }
  const ids = recordIds.map((value) => positiveInteger(value, "record_id", 2147483647));
  const placeholders = ids.map(() => "?").join(", ");
  const existing = await env.DB.prepare(
    `SELECT id FROM publication_records WHERE id IN (${placeholders}) ORDER BY id`,
  ).bind(...ids).all();
  await env.DB.prepare(
    `DELETE FROM publication_records WHERE id IN (${placeholders})`,
  ).bind(...ids).run();
  return jsonResponse({ deleted_ids: (existing.results || []).map((row) => row.id) });
}

async function listPublishingAccountGroups(request, env) {
  const url = new URL(request.url);
  const businessLine = String(url.searchParams.get("business_line") || "").trim();
  if (businessLine && !ACCOUNT_GROUP_BUSINESS_LINES.includes(businessLine)) {
    throw new Error(`business_line 必须从 ${ACCOUNT_GROUP_BUSINESS_LINES.join(", ")} 中选择`);
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
    `SELECT m.id, COALESCE(a.platform_account_id, m.platform_account_id) AS platform_account_id,
            m.group_code, COALESCE(a.platform, m.platform) AS platform,
            COALESCE(a.connector, m.connector) AS connector, m.account_ref,
            COALESCE(a.display_name, m.display_name) AS display_name,
            m.position, m.enabled, m.created_at, m.updated_at,
            m.account_key, a.connector_account_id, a.credential_ref
     FROM publishing_account_group_members m
     LEFT JOIN publishing_accounts a ON a.account_key = m.account_key
     WHERE m.enabled = 1 AND (m.account_key IS NULL OR a.enabled = 1)
       AND m.group_code IN (${placeholders})
     ORDER BY m.group_code, m.position, m.platform, m.id`,
  ).bind(...groups.map((item) => item.code)).all();
  return jsonResponse({ groups, members: memberResult.results || [] });
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
       ON CONFLICT(business_line, run_id, title, platform, account_id, content_part) DO UPDATE SET
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

async function deleteProductionOutputs(request, env) {
  const body = await request.json();
  const recordIds = body.record_ids;
  if (!Array.isArray(recordIds) || recordIds.length < 1 || recordIds.length > 100) {
    throw new Error("record_ids 必须是包含 1 到 100 个记录 ID 的数组");
  }
  const ids = recordIds.map((value) => positiveInteger(value, "record_id", 2147483647));
  const placeholders = ids.map(() => "?").join(", ");
  const existing = await env.DB.prepare(
    `SELECT id FROM production_outputs WHERE id IN (${placeholders}) ORDER BY id`,
  ).bind(...ids).all();
  await env.DB.prepare(
    `DELETE FROM production_outputs WHERE id IN (${placeholders})`,
  ).bind(...ids).run();
  return jsonResponse({ deleted_ids: (existing.results || []).map((row) => row.id) });
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
  const languageRuns = [...new Set(records.filter(row => row.business_line === 'language_learning' && row.source === 'github_workflow').map(row => row.run_id))];
  for (const runId of languageRuns) {
    statements.push(env.DB.prepare(
      `UPDATE language_learning_packs SET used_at = COALESCE(used_at, strftime('%Y-%m-%dT%H:%M:%SZ', 'now')), reservation_expires_at = NULL, updated_at = CURRENT_TIMESTAMP
       WHERE run_id = ? AND status = 'claimed' AND (
         SELECT COUNT(DISTINCT content_kind || ':' || content_part) FROM production_outputs
         WHERE business_line = 'language_learning' AND source = 'github_workflow' AND run_id = ? AND r2_url IS NOT NULL
           AND ((content_kind IN ('en-zh', 'en-ko') AND content_part IN (1, 2))
             OR (content_kind IN ('en-zh-quiz', 'en-ko-quiz') AND content_part = 1))
       ) = 6`,
    ).bind(runId, runId));
  }
  const results = await env.DB.batch(statements);
  return jsonResponse({ records: results.slice(0, records.length).map((result) => result.results?.[0]).filter(Boolean) }, 201);
}

export { listPublicationRecords, deletePublicationRecords, listPublishingAccountGroups, commitPublicationRecords, listProductionOutputs, deleteProductionOutputs, commitProductionOutputs };
