const EXECUTION_PREFIX = "runs/anime/executions/";

async function deleteCheckpointFiles(bucket, prefix) {
  let cursor;
  do {
    const page = await bucket.list({ prefix: `${prefix}/checkpoint-blocks/`, cursor, limit: 1000 });
    if (page.objects.length) await bucket.delete(page.objects.map((object) => object.key));
    cursor = page.truncated ? page.cursor : undefined;
  } while (cursor);
  await bucket.delete(`${prefix}/block-checkpoint.json`);
}

async function cleanupExecutionPolicy(bucket, prefix, now) {
  const key = `${prefix}/retention.json`;
  const object = await bucket.get(key);
  if (!object) return;
  const policy = await object.json();
  const executionId = policy.execution_id;
  if (!/^[a-f0-9]{32}$/.test(executionId || "") || policy.version !== 1
      || prefix !== `${EXECUTION_PREFIX}${executionId}`) {
    throw new Error(`动漫清理计划身份或路径不一致：${key}`);
  }
  // 先检查两种期限和全部文件名，异常计划禁止执行任何删除。
  for (const kind of ["checkpoint", "final"]) {
    if (!Number.isFinite(Date.parse(policy[`${kind}_expires_at`]))) {
      throw new Error(`动漫清理计划期限无效：${key}`);
    }
  }
  if (!Array.isArray(policy.final_files) || policy.final_files.some(
    (name) => name !== "manifest.json" && !/^part-\d+\.mp4$/.test(name),
  )) throw new Error(`动漫清理计划包含非成片文件：${key}`);
  for (const kind of ["checkpoint", "final"]) {
    if (policy[`${kind}_cleaned`] || Date.parse(policy[`${kind}_expires_at`]) > now) continue;
    if (kind === "checkpoint") {
      await deleteCheckpointFiles(bucket, prefix);
    } else {
      const keys = policy.final_files.map((name) => `${prefix}/${name}`);
      for (let offset = 0; offset < keys.length; offset += 1000) {
        await bucket.delete(keys.slice(offset, offset + 1000));
      }
    }
    // 删除成功才记录进度；失败时下次定时任务可以安全重试。
    policy[`${kind}_cleaned`] = true;
    await bucket.put(key, JSON.stringify(policy), { httpMetadata: { contentType: "application/json" } });
    console.log(JSON.stringify({ 执行任务: executionId, 清理类别: kind, 状态: "完成" }));
  }
}

export async function cleanupExpiredAnimeExecutionFiles(bucket, now = Date.now()) {
  let cursor;
  let checked = 0;
  let failures = 0;
  do {
    // 按执行目录列举，避免扫描每个视频对象。
    const page = await bucket.list({ prefix: EXECUTION_PREFIX, delimiter: "/", cursor, limit: 1000 });
    for (const directory of page.delimitedPrefixes) {
      const prefix = directory.replace(/\/$/, "");
      try {
        await cleanupExecutionPolicy(bucket, prefix, now);
        checked += 1;
      } catch (error) {
        failures += 1;
        console.error("动漫到期清理失败", prefix, error);
      }
    }
    cursor = page.truncated ? page.cursor : undefined;
  } while (cursor);
  console.log(JSON.stringify({ 检查目录数量: checked, 失败数量: failures }));
  if (failures) throw new Error(`${failures} 个动漫任务清理失败，下次继续重试`);
}
