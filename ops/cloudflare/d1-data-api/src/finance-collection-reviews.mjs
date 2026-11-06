import { errorResponse, jsonResponse, optionalText, requiredText } from "./api-common.mjs";

export async function recordFinanceCollectionReview(request, env) {
  const review = await request.json();
  const awemeId = requiredText(review.aweme_id, "aweme_id", 64);
  const decision = requiredText(review.decision, "decision", 20);
  const reason = requiredText(review.reason, "reason", 2000);
  const authorId = optionalText(review.author_id, "author_id", 200) || "";
  const authorName = requiredText(review.author_name, "author_name", 200);
  const profileUrl = optionalText(review.author_profile_url, "author_profile_url", 2000) || "";
  const source = requiredText(review.source, "source", 30);
  const awemeUrl = requiredText(review.aweme_url, "aweme_url", 2000);
  const characterCount = review.source_character_count;
  if (!/^\d+$/.test(awemeId) || !["normal", "ad", "off_topic", "length"].includes(decision)
      || !["direct_link", "author_homepage"].includes(source) || !Number.isSafeInteger(characterCount) || characterCount < 0) {
    return errorResponse("INVALID_FINANCE_REVIEW", "审核记录的作品 ID、结论、来源或字数不正确");
  }
  await env.DB.prepare(
    `INSERT INTO finance_collection_reviews
     (aweme_id, decision, reason, author_id, author_name, author_profile_url, source, aweme_url, source_character_count)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(aweme_id) DO NOTHING`,
  ).bind(awemeId, decision, reason, authorId, authorName, profileUrl, source, awemeUrl, characterCount).run();
  return jsonResponse({ aweme_id: awemeId });
}

export async function financeCollectionReviewStats(env) {
  const [summary, reasons, authors, recent] = await env.DB.batch([
    env.DB.prepare(`SELECT COUNT(*) AS reviewed_count, COUNT(CASE WHEN decision != 'normal' THEN 1 END) AS rejected_count,
                           MIN(created_at) AS tracking_started_at FROM finance_collection_reviews`),
    env.DB.prepare(`SELECT decision, COUNT(*) AS rejected_count FROM finance_collection_reviews
                    WHERE decision != 'normal' GROUP BY decision ORDER BY rejected_count DESC, decision`),
    env.DB.prepare(`SELECT author_id, author_name, author_profile_url, source, COUNT(*) AS reviewed_count,
                           COUNT(CASE WHEN decision != 'normal' THEN 1 END) AS rejected_count
                    FROM finance_collection_reviews GROUP BY author_id, author_name, author_profile_url, source
                    ORDER BY rejected_count DESC, author_name, source`),
    env.DB.prepare(`SELECT * FROM finance_collection_reviews WHERE decision != 'normal'
                    ORDER BY created_at DESC, aweme_id DESC LIMIT 20`),
  ]);
  const withRate = (row) => ({ ...row, rejection_rate: row.reviewed_count ? row.rejected_count / row.reviewed_count : null });
  return jsonResponse({
    ...withRate(summary.results[0]),
    by_reason: reasons.results,
    by_author_source: authors.results.map(withRate),
    recent_rejections: recent.results,
  });
}
