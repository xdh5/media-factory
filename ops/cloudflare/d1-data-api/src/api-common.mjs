const PUBLICATION_BUSINESS_LINES = ["finance", "language_learning", "psychology_quiz", "anime"];
const ACCOUNT_GROUP_BUSINESS_LINES = PUBLICATION_BUSINESS_LINES;
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

export { PUBLICATION_BUSINESS_LINES, ACCOUNT_GROUP_BUSINESS_LINES, PUBLICATION_PLATFORMS, PUBLICATION_MODES, PUBLICATION_STATUSES, PRODUCTION_SOURCES, jsonResponse, errorResponse, requiredText, positiveInteger, optionalText, publicationTimestamp, optionalTimestamp, productionDate, cutoffTimestamp };
