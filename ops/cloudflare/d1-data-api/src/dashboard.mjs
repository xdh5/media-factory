import { productionDate } from "./api-common.mjs";

const DASHBOARD_ORIGIN = "https://xdh5.github.io";

function dashboardCorsHeaders(extra = {}) {
  return {
    "Cache-Control": "no-store",
    "Access-Control-Allow-Origin": DASHBOARD_ORIGIN,
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Vary": "Origin",
    ...extra,
  };
}

function dashboardResponse(payload, status = 200) {
  return Response.json(payload, {
    status,
    headers: dashboardCorsHeaders(),
  });
}

function downloadFilename(fileUrl, fallback = "video.mp4") {
  try {
    const name = decodeURIComponent(new URL(fileUrl).pathname.split("/").pop() || "");
    return name || fallback;
  } catch {
    return fallback;
  }
}

function contentDisposition(filename) {
  const ascii = String(filename || "video.mp4").replace(/[^\x20-\x7E]/g, "_").replace(/["\\]/g, "_") || "video.mp4";
  return `attachment; filename="${ascii}"; filename*=UTF-8''${encodeURIComponent(filename)}`;
}

function runDate(runId, fallback) {
  const matched = /^run-(\d{4})(\d{2})(\d{2})$/.exec(String(runId || ""));
  if (matched) return `${matched[1]}-${matched[2]}-${matched[3]}`;
  const timestamp = Date.parse(fallback);
  return Number.isFinite(timestamp) ? new Date(timestamp + 8 * 60 * 60 * 1000).toISOString().slice(0, 10) : "";
}

// 成片应发平台按账号组区分，不把同一业务线下的其他组混进来。
function dashboardAccountGroupName(item) {
  const kind = String(item.content_kind || "");
  if (kind.startsWith("en-zh")) return "chinese";
  if (kind.startsWith("en-ko")) return "korean";
  if (item.business_line === "finance") return "finance";
  return "";
}

async function dashboardRecords(request, env) {
  const url = new URL(request.url);
  const selectedDate = String(url.searchParams.get("date") || "").trim();
  const rangeFrom = String(url.searchParams.get("from") || "").trim();
  const rangeTo = String(url.searchParams.get("to") || "").trim();
  if (selectedDate) productionDate(selectedDate);
  if (rangeFrom || rangeTo) {
    productionDate(rangeFrom);
    productionDate(rangeTo);
    if (rangeFrom > rangeTo) throw new Error("from 不能晚于 to");
  }
  const outputStatement = rangeFrom
    ? env.DB.prepare(
      `SELECT production_id, run_id, publish_date, business_line, content_kind,
              content_part, title, hashtags, source, local_path, r2_url, r2_expires_at
       FROM production_outputs WHERE business_line != 'anime' AND publish_date >= ? AND publish_date <= ?
       ORDER BY publish_date, business_line, content_kind, content_part`,
    ).bind(rangeFrom, rangeTo)
    : selectedDate
    ? env.DB.prepare(
      `SELECT production_id, run_id, publish_date, business_line, content_kind,
              content_part, title, hashtags, source, local_path, r2_url, r2_expires_at
       FROM production_outputs WHERE business_line != 'anime' AND publish_date = ?
       ORDER BY business_line, content_kind, content_part`,
    ).bind(selectedDate)
    : env.DB.prepare(
      `SELECT production_id, run_id, publish_date, business_line, content_kind,
              content_part, title, hashtags, source, local_path, r2_url, r2_expires_at
       FROM production_outputs WHERE business_line != 'anime' ORDER BY publish_date DESC, business_line, content_kind, content_part
       LIMIT 1000`,
    );
  // 补发按内容的计划日期归组；无日期批次使用北京时间实际发送日期。
  const calendarDateSql = `CASE
    WHEN run_id GLOB 'run-[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]'
      THEN substr(run_id, 5, 4) || '-' || substr(run_id, 9, 2) || '-' || substr(run_id, 11, 2)
    ELSE date(publish_at, '+8 hours') END`;
  const publicationStatement = rangeFrom
    ? env.DB.prepare(
      `SELECT publication_id, run_id, business_line, platform, content_part, title,
              publish_mode, publish_at, status, external_url
       FROM publication_records
       WHERE business_line != 'anime' AND ${calendarDateSql} >= ? AND ${calendarDateSql} <= ?
       ORDER BY publish_at, business_line, title, content_part, platform`,
    ).bind(rangeFrom, rangeTo)
    : selectedDate
    ? env.DB.prepare(
      `SELECT publication_id, run_id, business_line, platform, content_part, title,
              publish_mode, publish_at, status, external_url
       FROM publication_records WHERE business_line != 'anime' AND ${calendarDateSql} = ?
       ORDER BY business_line, title, content_part, platform`,
    ).bind(selectedDate)
    : env.DB.prepare(
      `SELECT publication_id, run_id, business_line, platform, content_part, title,
              publish_mode, publish_at, status, external_url
       FROM publication_records WHERE business_line != 'anime' ORDER BY id DESC LIMIT 1000`,
    );
  const [outputResult, publicationResult, platformResult] = await Promise.all([
    outputStatement.all(),
    publicationStatement.all(),
    env.DB.prepare(
      `SELECT DISTINCT g.business_line, g.name AS account_group,
              COALESCE(a.platform, m.platform) AS platform
       FROM publishing_account_groups g
       JOIN publishing_account_group_members m ON m.group_code = g.code
       LEFT JOIN publishing_accounts a ON a.account_key = m.account_key
       WHERE g.enabled = 1 AND m.enabled = 1 AND g.business_line != 'anime'
         AND (m.account_key IS NULL OR a.enabled = 1)
       ORDER BY g.business_line, g.name, platform`,
    ).all(),
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
  const platformRows = platformResult.results || [];
  const platformsByGroup = new Map();
  for (const row of platformRows) {
    if (!platformsByGroup.has(row.account_group)) {
      platformsByGroup.set(row.account_group, []);
    }
    const platforms = platformsByGroup.get(row.account_group);
    if (row.platform && !platforms.includes(row.platform)) platforms.push(row.platform);
  }
  const dates = new Map();
  for (const item of byKey.values()) {
    const groupName = dashboardAccountGroupName(item);
    const sameLine = platformRows.filter((row) => row.business_line === item.business_line);
    const lineGroups = [...new Set(sameLine.map((row) => row.account_group))];
    item.platforms = platformsByGroup.get(groupName)
      || (lineGroups.length === 1 ? platformsByGroup.get(lineGroups[0]) : [])
      || [];
    if (!dates.has(item.publish_date)) dates.set(item.publish_date, []);
    dates.get(item.publish_date).push(item);
  }
  return dashboardResponse({
    platforms_by_business_line: Object.fromEntries(
      [...new Set(platformRows.map((row) => row.business_line))]
        .map((line) => [line, [...new Set(platformRows.filter((row) => row.business_line === line).map((row) => row.platform))]]),
    ),
    platforms_by_account_group: Object.fromEntries(platformsByGroup),
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

async function dashboardAnime(env) {
  const result = await env.DB.prepare(
    `SELECT run_id, content_part, title, platform, publish_at, external_url
     FROM publication_records
     WHERE business_line = 'anime' AND status = 'published'
     ORDER BY publish_at DESC, id DESC`,
  ).all();
  const contents = new Map();
  for (const row of result.results || []) {
    const key = `${row.run_id}|${row.content_part}`;
    if (!contents.has(key)) {
      contents.set(key, { title: row.title, published_at: row.publish_at, publications: [] });
    }
    contents.get(key).publications.push({
      platform: row.platform, status: "published", publish_at: row.publish_at,
      external_url: row.external_url || "",
    });
  }
  return dashboardResponse({ contents: [...contents.values()] });
}

async function dashboardLanguagePacks(env) {
  const result = await env.DB.prepare(
    `SELECT pack_id, topic, words_json, image_urls_json, status,
            run_id, publish_date, claimed_at, created_at, updated_at
     FROM language_learning_packs
     ORDER BY CASE status WHEN 'ready' THEN 0 ELSE 1 END, created_at DESC, pack_id`,
  ).all();
  const packs = (result.results || []).map((row) => ({
    pack_id: row.pack_id,
    topic: row.topic,
    words: JSON.parse(row.words_json || "{}"),
    image_urls: JSON.parse(row.image_urls_json || "[]"),
    status: row.status,
    run_id: row.run_id,
    publish_date: row.publish_date,
    claimed_at: row.claimed_at,
    created_at: row.created_at,
    updated_at: row.updated_at,
  }));
  return dashboardResponse({
    packs,
    summary: {
      total: packs.length,
      ready: packs.filter((item) => item.status === "ready").length,
      claimed: packs.filter((item) => item.status === "claimed").length,
    },
  });
}

async function dashboardFinanceArticles(env) {
  const result = await env.DB.prepare(
    `SELECT c.aweme_id, c.author_name, c.caption,
            COALESCE(json_extract(e.content_json, '$.article'), c.transcript_corrected) AS article,
            json_extract(e.content_json, '$.title') AS title,
            json_extract(e.content_json, '$.topic') AS topic,
            json_extract(e.content_json, '$.source_hook') AS source_hook,
            json_extract(e.content_json, '$.short_title') AS short_title,
            c.aweme_url, c.cover_url, c.created_at,
            GROUP_CONCAT(DISTINCT d.search_keyword) AS search_keywords,
            COALESCE(u.status, CASE WHEN e.aweme_id IS NULL THEN 'pending_editorial' ELSE 'ready' END) AS status,
            u.reserved_at, u.used_at, u.run_id
     FROM douyin_research_contents c
     JOIN douyin_research_discoveries d
       ON d.aweme_id = c.aweme_id AND d.collection_code = 'finance'
     LEFT JOIN finance_editorial_drafts e ON e.aweme_id = c.aweme_id AND e.source_transcript = c.transcript_corrected
     LEFT JOIN douyin_research_script_usage u
       ON u.aweme_id = c.aweme_id AND u.workflow = 'finance'
     GROUP BY c.aweme_id
     ORDER BY CASE COALESCE(u.status, 'ready')
                WHEN 'ready' THEN 0 WHEN 'reserved' THEN 1 ELSE 2
              END,
              c.created_at DESC, c.aweme_id`,
  ).all();
  const articles = (result.results || []).map((row) => ({
    ...row,
    search_keywords: String(row.search_keywords || "")
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean),
  }));
  return dashboardResponse({
    articles,
    summary: {
      total: articles.length,
      ready: articles.filter((item) => item.status === "ready").length,
      pending_editorial: articles.filter((item) => item.status === "pending_editorial").length,
      reserved: articles.filter((item) => item.status === "reserved").length,
      used: articles.filter((item) => item.status === "used").length,
    },
  });
}

async function dashboardDownload(request, env) {
  let fileUrl = "";
  if (request.method === "POST") {
    const form = await request.formData();
    fileUrl = String(form.get("url") || "").trim();
  } else {
    const page = new URL(request.url);
    fileUrl = String(page.searchParams.get("url") || "").trim();
  }
  if (!fileUrl) {
    return dashboardResponse({ error: { code: "INVALID_PARAMETER", message: "url 不能为空" } }, 400);
  }
  const row = await env.DB.prepare(
    `SELECT r2_url, r2_expires_at, title
     FROM production_outputs
     WHERE r2_url = ?
     LIMIT 1`,
  ).bind(fileUrl).first();
  if (!row?.r2_url) {
    return dashboardResponse({ error: { code: "NOT_FOUND", message: "找不到对应产物" } }, 404);
  }
  if (row.r2_expires_at && Date.parse(row.r2_expires_at) <= Date.now()) {
    return dashboardResponse({ error: { code: "GONE", message: "产物已过期" } }, 410);
  }
  const upstream = await fetch(row.r2_url);
  if (!upstream.ok || !upstream.body) {
    return dashboardResponse({ error: { code: "UPSTREAM_ERROR", message: "拉取产物失败" } }, 502);
  }
  const filename = downloadFilename(row.r2_url, `${row.title || "video"}.mp4`);
  const headers = dashboardCorsHeaders({
    "Content-Type": upstream.headers.get("Content-Type") || "video/mp4",
    "Content-Disposition": contentDisposition(filename),
    "Access-Control-Expose-Headers": "Content-Disposition",
  });
  const length = upstream.headers.get("Content-Length");
  if (length) headers["Content-Length"] = length;
  return new Response(upstream.body, { status: 200, headers });
}

async function handleDashboard(request, env, url) {
  if (request.method === "OPTIONS" && url.pathname.startsWith("/v1/dashboard/")) {
    return new Response(null, {
      status: 204,
      headers: dashboardCorsHeaders(),
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
  if (request.method === "GET" && url.pathname === "/v1/dashboard/anime") {
    try {
      return await dashboardAnime(env);
    } catch (error) {
      console.error(error);
      return dashboardResponse({ error: { code: "D1_ERROR", message: "读取动画发布记录失败" } }, 500);
    }
  }
  if (request.method === "GET" && url.pathname === "/v1/dashboard/language-packs") {
    try {
      return await dashboardLanguagePacks(env);
    } catch (error) {
      console.error(error);
      return dashboardResponse({ error: { code: "D1_ERROR", message: "读取语言词包失败" } }, 500);
    }
  }
  if (request.method === "GET" && url.pathname === "/v1/dashboard/finance-articles") {
    try {
      return await dashboardFinanceArticles(env);
    } catch (error) {
      console.error(error);
      return dashboardResponse({ error: { code: "D1_ERROR", message: "读取财经文章失败" } }, 500);
    }
  }
  if (["GET", "POST"].includes(request.method) && url.pathname === "/v1/dashboard/download") {
    try {
      return await dashboardDownload(request, env);
    } catch (error) {
      if (error instanceof Error && /必须|不能|格式/.test(error.message)) {
        return dashboardResponse({ error: { code: "INVALID_PARAMETER", message: error.message } }, 400);
      }
      console.error(error);
      return dashboardResponse({ error: { code: "D1_ERROR", message: "下载产物失败" } }, 500);
    }
  }
  return null;
}

export { handleDashboard };
