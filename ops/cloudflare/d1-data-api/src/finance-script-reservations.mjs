import { jsonResponse, requiredText, positiveInteger } from './api-common.mjs';

export async function cleanupExpiredScriptReservations(env) {
  const result = await env.DB.prepare(`DELETE FROM douyin_research_script_usage
    WHERE status = 'reserved' AND datetime(reservation_expires_at) <= datetime('now')`).run();
  return { released_count: result.meta.changes };
}

export async function releaseScriptReservation(request, env) {
  const body = await request.json();
  const awemeId = requiredText(body.aweme_id, 'aweme_id', 64);
  const workflow = requiredText(body.workflow, 'workflow', 64);
  const token = requiredText(body.reservation_token, 'reservation_token', 100);
  const result = await env.DB.prepare(`DELETE FROM douyin_research_script_usage
    WHERE aweme_id = ? AND workflow = ? AND reservation_token = ? AND status = 'reserved'`)
    .bind(awemeId, workflow, token).run();
  const existing = await env.DB.prepare('SELECT status FROM douyin_research_script_usage WHERE aweme_id = ? AND workflow = ?')
    .bind(awemeId, workflow).first();
  return jsonResponse({ released: result.meta.changes === 1, used: existing?.status === 'used' });
}

export async function renewScriptReservation(request, env) {
  const body = await request.json();
  const minutes = positiveInteger(body.reservation_minutes, 'reservation_minutes', 1440);
  const expires = new Date(Date.now() + minutes * 60000).toISOString();
  const result = await env.DB.prepare(`UPDATE douyin_research_script_usage SET reservation_expires_at = ?
    WHERE aweme_id = ? AND workflow = ? AND reservation_token = ? AND status = 'reserved'
    AND datetime(reservation_expires_at) > datetime('now')`)
    .bind(expires, requiredText(body.aweme_id, 'aweme_id', 64), requiredText(body.workflow, 'workflow', 64),
      requiredText(body.reservation_token, 'reservation_token', 100)).run();
  return jsonResponse({ renewed: result.meta.changes === 1 });
}
