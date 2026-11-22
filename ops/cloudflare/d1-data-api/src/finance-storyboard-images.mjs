import { jsonResponse } from './api-common.mjs';

export async function listStoryboardImages(request, env) {
  const url = new URL(request.url);
  const rows = await env.DB.prepare(`SELECT * FROM finance_storyboard_image_sets
    WHERE aweme_id = ? AND storyboard_hash = ? AND deleted_at IS NULL`)
    .bind(url.searchParams.get('aweme_id'), url.searchParams.get('storyboard_hash')).all();
  return jsonResponse({ records: rows.results.map(row => ({ ...row, images: JSON.parse(row.images_json), images_json: undefined })) });
}

export async function saveStoryboardImages(request, env) {
  const { aweme_id, storyboard_hash, images } = await request.json();
  const draft = await env.DB.prepare(`SELECT content_json FROM finance_editorial_drafts WHERE aweme_id = ?`).bind(aweme_id).first();
  if (!draft) throw new Error('稿件没有定稿');
  const storyboard = JSON.parse(draft.content_json).storyboard;
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(storyboard));
  const actual = Array.from(new Uint8Array(digest), n => n.toString(16).padStart(2, '0')).join('');
  if (actual !== storyboard_hash) throw new Error('图片对应的分镜已变化');
  const prefix = `finance/storyboard-images/${aweme_id}/${storyboard_hash}/`;
  if (!images || !Object.keys(images).length || Object.values(images).some(image => !image.key.startsWith(prefix))) {
    throw new Error('分镜图片必须位于本稿件的专用 R2 目录');
  }
  await env.DB.prepare(`INSERT INTO finance_storyboard_image_sets(aweme_id, storyboard_hash, images_json)
    VALUES (?, ?, ?) ON CONFLICT(aweme_id, storyboard_hash) DO UPDATE SET
    images_json=excluded.images_json, deleted_at=NULL, updated_at=CURRENT_TIMESTAMP`)
    .bind(aweme_id, storyboard_hash, JSON.stringify(images)).run();
  return jsonResponse({ saved_count: Object.keys(images).length });
}

export async function bindStoryboardImages(request, env) {
  const { aweme_id, storyboard_hash, production_id, publish_date } = await request.json();
  if (!/^local_mcp:finance:run-\d{8}:finance:[1-9]\d*$/.test(production_id)) throw new Error('财经成片标识无效');
  await env.DB.prepare(`UPDATE finance_storyboard_image_sets SET production_id=?, publish_date=?, updated_at=CURRENT_TIMESTAMP
    WHERE aweme_id=? AND storyboard_hash=? AND deleted_at IS NULL`)
    .bind(production_id, publish_date, aweme_id, storyboard_hash).run();
  return jsonResponse({ bound: true });
}

export async function cleanupStoryboardImages(request, env) {
  // 删除由绑定 R2 桶的 Worker 执行，资格查询和完成登记均在服务端。
  const rows = await env.DB.prepare(`SELECT s.* FROM finance_storyboard_image_sets s
    JOIN production_outputs p ON p.production_id=s.production_id AND p.business_line='finance'
    WHERE s.deleted_at IS NULL AND s.publish_date < date('now', '+8 hours')
    AND EXISTS (SELECT 1 FROM production_publication_targets t WHERE t.production_id=s.production_id)
    AND NOT EXISTS (
      SELECT 1 FROM production_publication_targets t WHERE t.production_id=s.production_id
      AND NOT EXISTS (SELECT 1 FROM publication_records r WHERE r.publication_id=t.production_id
        AND r.platform=t.platform AND r.account_id=t.account_id
        AND (r.status='published' OR (r.status='scheduled' AND datetime(r.publish_at)<=datetime('now'))))
    )`).all();
  const deleted = [];
  for (const row of rows.results) {
    const images = Object.values(JSON.parse(row.images_json));
    const prefix = `finance/storyboard-images/${row.aweme_id}/${row.storyboard_hash}/`;
    if (images.some(image => !image.key.startsWith(prefix))) throw new Error('拒绝删除分镜图片目录之外的对象');
    let cursor;
    let imageCount = 0;
    do {
      const page = await env.STORYBOARD_IMAGES.list({ prefix, cursor });
      if (page.objects.length) await env.STORYBOARD_IMAGES.delete(page.objects.map(object => object.key));
      imageCount += page.objects.length;
      cursor = page.truncated ? page.cursor : undefined;
    } while (cursor);
    await env.DB.prepare(`UPDATE finance_storyboard_image_sets SET deleted_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP
      WHERE aweme_id=? AND storyboard_hash=?`).bind(row.aweme_id, row.storyboard_hash).run();
    deleted.push({ production_id: row.production_id, image_count: imageCount });
  }
  return jsonResponse({ deleted });
}

export async function savePublicationTargets(request, env) {
  const { records } = await request.json();
  await env.DB.batch(records.map(row => env.DB.prepare(`INSERT INTO production_publication_targets(production_id,platform,account_id)
    VALUES (?,?,?) ON CONFLICT DO NOTHING`).bind(row.production_id, row.platform, row.account_id)));
  return jsonResponse({ saved_count: records.length });
}

