import { jsonResponse, errorResponse, requiredText, positiveInteger } from './api-common.mjs';

class KnowledgeError extends Error {
  constructor(message, status = 400) { super(message); this.status = status; }
}
const fail = (message, status = 400) => { throw new KnowledgeError(message, status); };
const text = (value, name, max = 64) => requiredText(value, name, max);
const rows = async (statement) => (await statement.all()).results;
async function sha256(value) {
  return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(value))),x=>x.toString(16).padStart(2,'0')).join('');
}
function canonical(value) {
  if(Array.isArray(value)) return value.map(canonical);
  if(value && typeof value==='object') return Object.fromEntries(Object.keys(value).sort().map(key=>[key,canonical(value[key])]));
  return value;
}
const document = (row) => row && ({ ...row, metadata: JSON.parse(row.metadata_json), metadata_json: undefined });
const baseOutput = (row) => ({ ...row, profiles: JSON.parse(row.profiles_json), profiles_json: undefined });
async function base(env, id) {
  const result = await env.DB.prepare('SELECT * FROM knowledge_bases WHERE id=?').bind(text(id, 'knowledge_base')).first();
  if (!result) fail('知识库不存在', 404);
  return result;
}
function profileConfig(env, config) {
  const bindings = JSON.parse(env.KNOWLEDGE_INDEXES || '{}');
  const binding = bindings[config.index_name];
  if (!binding || !env[binding.binding]) fail(`索引未绑定：${config.index_name}`, 503);
  if (binding.dimensions !== config.dimensions || binding.metric !== config.metric) fail('索引部署配置与 profile 不一致',409);
  return env[binding.binding];
}
async function indexFor(env, kb, profileId) {
  const configs = JSON.parse(kb.profiles_json);
  const config = configs[profileId];
  if (!config) fail('profile 尚未注册', 404);
  const index = profileConfig(env, config);
  const info = await index.describe();
  if (info.dimensions !== config.dimensions) fail('索引实际维度与 profile 不一致', 409);
  return { index, info, config };
}
function metadata(value, kind) {
  if (!value || typeof value !== 'object' || Array.isArray(value) || JSON.stringify(value).length > 12000) fail('metadata 必须是至多 12000 字符的对象');
  for (const name of ['business_line', 'platform', 'stage']) {
    if (value[name] !== undefined && (typeof value[name] !== 'string' || !/^[a-z0-9_-]{1,64}$/.test(value[name]))) fail(`${name} 必须是至多 64 位的小写分类标识`);
  }
  if (value.verified !== undefined && typeof value.verified !== 'boolean') fail('verified 必须是布尔值');
  if (kind === 'publisher-errors') {
    for (const name of ['business_line', 'platform', 'stage', 'error_summary', 'root_cause', 'applicability', 'verified_at']) text(value[name], name, 4000);
    if (value.verified !== true) fail('发布经验必须经过实际验证');
    if (!Array.isArray(value.solution_steps) || !value.solution_steps.length || value.solution_steps.some(x => typeof x !== 'string' || !x.trim())) fail('solution_steps 必须包含实际解决步骤');
    if (!Array.isArray(value.evidence) || !value.evidence.length || value.evidence.some(x => !['receipt', 'observation', 'log'].includes(x.type) || typeof x.reference !== 'string' || !x.reference.trim())) fail('evidence 必须包含业务回执、观察或日志依据');
    if (Number.isNaN(Date.parse(value.verified_at)) || !/(Z|[+-]\d\d:\d\d)$/.test(value.verified_at)) fail('verified_at 必须包含时区');
  }
  return JSON.stringify(value);
}
function validateProfile(config, id) {
  if (!/^[a-f0-9]{32}$/.test(id)) fail('profile_id 格式错误');
  if (!config || typeof config !== 'object') fail('profile 必须是对象');
  for (const key of Object.keys(config)) if (/key|token|secret/i.test(key)) fail('profile 不能保存凭据字段');
  for (const key of ['provider', 'model', 'endpoint', 'index_name', 'splitter_version']) text(config[key], key, 2048);
  if (!['cosine', 'euclidean', 'dot-product'].includes(config.metric)) fail('metric 格式错误');
  positiveInteger(config.dimensions, 'dimensions', 1536);
  positiveInteger(config.chunk_size, 'chunk_size', 8000);
  if (!Number.isInteger(config.chunk_overlap) || config.chunk_overlap < 0 || config.chunk_overlap >= config.chunk_size) fail('chunk_overlap 格式错误');
}
async function jobLease(env, b) {
  const job = await env.DB.prepare("SELECT * FROM knowledge_index_jobs WHERE id=? AND lease_token=? AND lease_until>unixepoch() AND status='processing'")
    .bind(text(b.job_id, 'job_id'), text(b.lease_token, 'lease_token')).first();
  if (!job) fail('同步租约过期或已被其他进程领取', 409);
  return job;
}
async function dispatch(action, b, env) {
  if (action === 'bases') return { bases: (await rows(env.DB.prepare('SELECT * FROM knowledge_bases ORDER BY id'))).map(baseOutput) };
  if (action === 'register') {
    const id = text(b.knowledge_base, 'knowledge_base');
    if (!/^[a-z0-9][a-z0-9_-]{0,63}$/.test(id)) fail('知识库标识格式错误');
    if (!['generic', 'publisher-errors'].includes(b.kind)) fail('kind 格式错误');
    validateProfile(b.profile, b.profile_id);
    profileConfig(env, b.profile);
    await env.DB.prepare('INSERT INTO knowledge_bases(id,kind,active_profile,profiles_json) VALUES(?,?,?,?) ON CONFLICT(id) DO NOTHING')
      .bind(id, b.kind, b.profile_id, JSON.stringify({ [b.profile_id]: b.profile })).run();
    const kb = await base(env, id);
    if (kb.kind !== b.kind || kb.active_profile !== b.profile_id) fail('知识库已存在且配置不同，请使用重建入口', 409);
    return { base: baseOutput(kb) };
  }
  const kb = await base(env, b.knowledge_base);
  if (action === 'add' || action === 'update') {
    const content = text(b.content, 'content', 100000).replace(/\r\n?/g,'\n').normalize('NFC'), title = text(b.title, 'title', 300);
    const meta = metadata(b.metadata, kb.kind);
    const fingerprint = await sha256(JSON.stringify(canonical({knowledge_base:kb.id,content,metadata:b.metadata})));
    if (action === 'add') {
      const id = crypto.randomUUID();
      await env.DB.prepare('INSERT INTO knowledge_documents(id,knowledge_base,title,content,metadata_json,fingerprint) VALUES(?,?,?,?,?,?) ON CONFLICT DO NOTHING')
        .bind(id, kb.id, title, content, meta, fingerprint).run();
      const record = await env.DB.prepare('SELECT * FROM knowledge_documents WHERE knowledge_base=? AND fingerprint=? AND deleted=0').bind(kb.id, fingerprint).first();
      const jobs = await rows(env.DB.prepare('SELECT profile_id,status FROM knowledge_index_jobs WHERE document_id=? AND revision=?').bind(record.id,record.revision));
      return { document: document(record), duplicate: record.id !== id, index_status: jobs };
    }
    const result = await env.DB.prepare("UPDATE knowledge_documents SET title=?,content=?,metadata_json=?,fingerprint=?,revision=revision+1,updated_at=CURRENT_TIMESTAMP WHERE id=? AND knowledge_base=? AND revision=? AND deleted=0 RETURNING *")
      .bind(title, content, meta, fingerprint, text(b.document_id, 'document_id'), kb.id, positiveInteger(b.expected_revision, 'expected_revision', 2147483647)).first();
    if (!result) fail('文档不存在、已删除或版本冲突', 409);
    return { document: document(result), index_status: 'pending' };
  }
  if (action === 'get') {
    const row = await env.DB.prepare('SELECT * FROM knowledge_documents WHERE knowledge_base=? AND id=?').bind(kb.id, text(b.document_id, 'document_id')).first();
    if (!row) fail('文档不存在', 404);
    return { document: document(row), jobs: await rows(env.DB.prepare('SELECT * FROM knowledge_index_jobs WHERE document_id=? ORDER BY created_at,id').bind(row.id)) };
  }
  if (action === 'list') {
    const limit = positiveInteger(b.limit ?? 20, 'limit', 100);
    const result = await rows(env.DB.prepare('SELECT * FROM knowledge_documents WHERE knowledge_base=? AND id>? AND deleted=0 ORDER BY id LIMIT ?').bind(kb.id, b.cursor || '', limit + 1));
    return { documents: result.slice(0, limit).map(document), next_cursor: result.length > limit ? result[limit - 1].id : null };
  }
  if (action === 'delete') {
    const result = await env.DB.prepare('UPDATE knowledge_documents SET deleted=1,revision=revision+1,updated_at=CURRENT_TIMESTAMP WHERE knowledge_base=? AND id=? AND revision=? AND deleted=0 RETURNING id,revision,deleted')
      .bind(kb.id, text(b.document_id, 'document_id'), positiveInteger(b.expected_revision, 'expected_revision', 2147483647)).first();
    if (!result) fail('文档不存在、已删除或版本冲突', 409);
    return { document: result, index_status: 'pending' };
  }
  if (action === 'reindex') {
    validateProfile(b.profile, b.profile_id);
    await indexFor(env, { ...kb, profiles_json: JSON.stringify({ [b.profile_id]: b.profile }) }, b.profile_id);
    const existing = JSON.parse(kb.profiles_json)[b.profile_id];
    if (existing && JSON.stringify(existing) !== JSON.stringify(b.profile)) fail('profile 标识与已保存配置不一致', 409);
    // 同一个事务先注册目标配置，再覆盖当前文档；并发变更由触发器补齐。
    await env.DB.batch([
      env.DB.prepare('UPDATE knowledge_bases SET profiles_json=json_set(profiles_json,?,json(?)) WHERE id=?').bind(`$.${b.profile_id}`, JSON.stringify(b.profile), kb.id),
      env.DB.prepare("INSERT INTO knowledge_index_jobs(id,knowledge_base,document_id,revision,profile_id,operation) SELECT lower(hex(randomblob(16))),knowledge_base,id,revision,?,CASE WHEN deleted=1 THEN 'delete' ELSE 'upsert' END FROM knowledge_documents WHERE knowledge_base=? ON CONFLICT(document_id,revision,profile_id) DO NOTHING").bind(b.profile_id, kb.id),
    ]);
    return { base: baseOutput(await base(env, kb.id)) };
  }
  if (action === 'activate') {
    await indexFor(env, kb, b.profile_id);
    const changed = await env.DB.prepare("UPDATE knowledge_bases SET active_profile=? WHERE id=? AND generation=? AND NOT EXISTS(SELECT 1 FROM knowledge_documents d WHERE d.knowledge_base=? AND NOT EXISTS(SELECT 1 FROM knowledge_index_jobs j WHERE j.document_id=d.id AND j.revision=d.revision AND j.profile_id=? AND j.status='ready')) RETURNING *")
      .bind(b.profile_id, kb.id, b.expected_generation, kb.id, b.profile_id).first();
    if (!changed) fail('文档集合已变化或目标索引尚未全部可见', 409);
    return { base: baseOutput(changed) };
  }
  if (action === 'status') return {
    base: baseOutput(kb),
    counts: await rows(env.DB.prepare('SELECT profile_id,status,count(*) AS count FROM knowledge_index_jobs WHERE knowledge_base=? GROUP BY profile_id,status').bind(kb.id)),
    jobs: await rows(env.DB.prepare('SELECT * FROM knowledge_index_jobs WHERE knowledge_base=? AND id>? ORDER BY id LIMIT ?').bind(kb.id, b.cursor || '', positiveInteger(b.limit ?? 50, 'limit', 100))),
  };
  if (action === 'claim') {
    const token = crypto.randomUUID();
    const excluded=b.exclude_job_ids||[];
    if(!Array.isArray(excluded)||excluded.length>20||excluded.some(x=>typeof x!=='string'||!/^[a-f0-9]{32}$/.test(x)))fail('exclude_job_ids 格式错误');
    const job = await env.DB.prepare(`UPDATE knowledge_index_jobs SET status='processing',lease_token=?,lease_until=unixepoch()+300,attempts=attempts+1,error=NULL,updated_at=CURRENT_TIMESTAMP WHERE id=(SELECT j.id FROM knowledge_index_jobs j WHERE knowledge_base=? AND (status='pending' OR (status='failed' AND ?=1) OR (status='processing' AND lease_until<=unixepoch())) ${excluded.length?`AND j.id NOT IN (${excluded.map(()=>'?').join(',')})`:''} AND NOT EXISTS(SELECT 1 FROM knowledge_index_jobs other WHERE other.id<>j.id AND other.document_id=j.document_id AND other.profile_id=j.profile_id AND other.status='processing' AND other.lease_until>unixepoch()) ORDER BY created_at,revision,id LIMIT 1) RETURNING *`)
      .bind(token, kb.id, b.retry_failed === true ? 1 : 0,...excluded).first();
    if (!job) return { job: null };
    const doc = await env.DB.prepare('SELECT * FROM knowledge_documents WHERE id=?').bind(job.document_id).first();
    return { job, document: document(doc), base: baseOutput(kb) };
  }
  if (action === 'fail') {
    const job = await jobLease(env, b);
    if (job.knowledge_base !== kb.id) fail('任务与知识库不一致');
    await env.DB.prepare("UPDATE knowledge_index_jobs SET status='failed',error=?,lease_token=NULL,lease_until=NULL WHERE id=? AND lease_token=?")
      .bind(text(b.error, 'error', 500), job.id, b.lease_token).run();
    return { status: 'failed' };
  }
  if (action === 'submit') {
    const job = await jobLease(env, b);
    if (job.knowledge_base !== kb.id) fail('任务与知识库不一致');
    const doc = await env.DB.prepare('SELECT * FROM knowledge_documents WHERE id=?').bind(job.document_id).first();
    const { index, config } = await indexFor(env, kb, job.profile_id);
    if (!Array.isArray(b.chunks) || b.chunks.length > 256) fail('chunks 必须是至多 256 项的数组');
    const current = doc.deleted === 0 && doc.revision === job.revision;
    const chunks = current ? b.chunks : [];
    if (current && !chunks.length) fail('当前文档不能提交空片段');
    for (const [chunkIndex,c] of chunks.entries()) {
      if (!/^[a-f0-9]{64}$/.test(c.id)) fail('片段 ID 格式错误');
      const identity='['+[kb.id,doc.id,job.revision,job.profile_id,chunkIndex].map(x=>JSON.stringify(x)).join(', ')+']';
      if(c.chunk_index!==chunkIndex || c.id!==await sha256(identity)) fail('片段 ID 与任务身份不一致');
      if (!Number.isInteger(c.start_index) || !Number.isInteger(c.end_index) || c.start_index < 0 || c.end_index <= c.start_index || Array.from(doc.content).slice(c.start_index,c.end_index).join('') !== c.content) fail('片段原文位置不一致');
      if (!Array.isArray(c.values) || c.values.length !== config.dimensions || c.values.some(x => typeof x !== 'number' || !Number.isFinite(x))) fail('向量维度或数值格式错误');
    }
    // 在任何向量副作用前持久记录 ID，失败或租约回收仍可清理。
    if (chunks.length) await env.DB.batch(chunks.map(c => env.DB.prepare('INSERT INTO knowledge_chunks(id,job_id,document_id,knowledge_base,revision,profile_id,chunk_index,start_index,end_index,content) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING')
      .bind(c.id,job.id,doc.id,kb.id,job.revision,job.profile_id,c.chunk_index,c.start_index,c.end_index,c.content)));
    const old = await rows(env.DB.prepare('SELECT id FROM knowledge_chunks WHERE document_id=? AND profile_id=? AND (revision<? OR (?=0 AND revision=?))').bind(doc.id, job.profile_id, job.revision, current ? 1 : 0, job.revision));
    let mutation;
    for (let i=0; i<old.length; i+=500) mutation = await index.deleteByIds(old.slice(i,i+500).map(c=>c.id));
    if (chunks.length) {
      const meta = JSON.parse(doc.metadata_json);
      mutation = await index.upsert(chunks.map(c=>({id:c.id,values:c.values,metadata:{knowledge_base:kb.id,profile_id:job.profile_id,document_id:doc.id,revision:job.revision,...Object.fromEntries(['business_line','platform','stage','verified'].filter(k=>meta[k]!==undefined).map(k=>[k,meta[k]]))}})));
    }
    const submittedAt = Math.floor(Date.now()/1000);
    const result = await env.DB.prepare("UPDATE knowledge_index_jobs SET status='submitted',mutation_id=?,submitted_at=?,lease_token=NULL,lease_until=NULL WHERE id=? AND lease_token=? AND lease_until>unixepoch() AND status='processing' AND error IS NULL RETURNING id")
      .bind(mutation?.mutationId || null, submittedAt, job.id,b.lease_token).first();
    if (!result) {
      // 迟到的旧进程留下可追溯 ID，并重新排入清理；不覆盖其他进程的有效租约。
      if(chunks.length) await env.DB.batch(chunks.map(c=>env.DB.prepare('INSERT INTO knowledge_chunks(id,job_id,document_id,knowledge_base,revision,profile_id,chunk_index,start_index,end_index,content) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING').bind(c.id,job.id,doc.id,kb.id,job.revision,job.profile_id,c.chunk_index,c.start_index,c.end_index,c.content)));
      await env.DB.prepare("UPDATE knowledge_index_jobs SET status=CASE WHEN status='processing' THEN status ELSE 'pending' END,error='LATE_MUTATION_CLEANUP',mutation_id=NULL WHERE id=?").bind(job.id).run();
      fail('向量写入已受理，但租约已失效；请恢复同步',409);
    }
    return { status:'submitted',mutation_id:mutation?.mutationId || null, current_revision:current };
  }
  if (action === 'refresh') {
    const jobs = await rows(env.DB.prepare("SELECT * FROM knowledge_index_jobs WHERE knowledge_base=? AND status='submitted' ORDER BY id LIMIT 50").bind(kb.id));
    const result=[];
    for (const job of jobs) {
      const { info } = await indexFor(env,kb,job.profile_id);
      const watermark = Date.parse(info.processedUpToDatetime || '')/1000;
      const visible = !job.mutation_id || info.processedUpToMutation === job.mutation_id || watermark > job.submitted_at + 1;
      if (visible) {
        await env.DB.batch([
          env.DB.prepare("UPDATE knowledge_index_jobs SET status='ready',updated_at=CURRENT_TIMESTAMP WHERE id=? AND status='submitted' AND mutation_id IS ?").bind(job.id,job.mutation_id),
          env.DB.prepare("DELETE FROM knowledge_chunks WHERE document_id=? AND profile_id=? AND (revision<? OR EXISTS(SELECT 1 FROM knowledge_documents WHERE id=? AND deleted=1)) AND NOT EXISTS(SELECT 1 FROM knowledge_index_jobs running WHERE running.id=knowledge_chunks.job_id AND running.status='processing')").bind(job.document_id,job.profile_id,job.revision,job.document_id),
          env.DB.prepare("UPDATE knowledge_documents SET title='',content='',metadata_json='{}' WHERE id=? AND deleted=1 AND NOT EXISTS(SELECT 1 FROM knowledge_index_jobs WHERE document_id=? AND status<>'ready')").bind(job.document_id,job.document_id),
        ]);
      }
      result.push({job_id:job.id,status:visible?'ready':'submitted',processed_up_to:info.processedUpToMutation});
    }
    return {jobs:result};
  }
  if (action === 'query') {
    const profileId = kb.active_profile;
    const {index,config}=await indexFor(env,kb,profileId);
    if(b.profile_id!==profileId) fail('查询期间生效 profile 已切换，请重新检索',409);
    if(!Array.isArray(b.vector)||b.vector.length!==config.dimensions||b.vector.some(x=>typeof x!=='number'||!Number.isFinite(x))) fail('查询向量格式或维度错误');
    const filter={knowledge_base:kb.id,profile_id:profileId};
    const filters=b.filters||{};
    for(const name of Object.keys(filters)) {
      if(!['business_line','platform','stage','verified'].includes(name)) fail('检索过滤字段不支持');
      if(name==='verified') { if(typeof filters[name]!=='boolean') fail('verified 必须是布尔值'); }
      else if(typeof filters[name]!=='string'||!/^[a-z0-9_-]{1,64}$/.test(filters[name])) fail('分类过滤值格式错误');
      filter[name]=filters[name];
    }
    if(kb.kind==='publisher-errors' && filters.verified===false) return {matches:[],profile_id:profileId,metric:config.metric};
    if(kb.kind==='publisher-errors') filter.verified=true;
    const query=await index.query(b.vector,{topK:positiveInteger(b.limit??20,'limit',100),returnValues:false,returnMetadata:'none',filter});
    const ids=query.matches.map(x=>x.id);
    if(!ids.length)return {matches:[],profile_id:profileId,metric:config.metric};
    const candidates=[];
    for(let offset=0;offset<ids.length;offset+=90) {
      const page=ids.slice(offset,offset+90);
      candidates.push(...await rows(env.DB.prepare(`SELECT c.*,d.title,d.metadata_json FROM knowledge_chunks c JOIN knowledge_documents d ON d.id=c.document_id WHERE c.id IN (${page.map(()=>'?').join(',')}) AND c.knowledge_base=? AND c.profile_id=? AND d.deleted=0 AND d.revision=c.revision`).bind(...page,kb.id,profileId)));
    }
    const scores=new Map(query.matches.map(x=>[x.id,x.score]));
    return {matches:candidates.map(x=>({...x,metadata:JSON.parse(x.metadata_json),metadata_json:undefined,score:scores.get(x.id)})).filter(x=>Object.entries(filter).every(([k,v])=>['knowledge_base','profile_id'].includes(k)||x.metadata[k]===v)),profile_id:profileId,metric:config.metric};
  }
  fail('知识接口不存在',404);
}

export async function handleKnowledge(request,env,url) {
  if(!url.pathname.startsWith('/v1/knowledge/')) return null;
  if(request.method!=='POST')return errorResponse('METHOD_NOT_ALLOWED','知识接口使用 POST',405);
  try { return jsonResponse(await dispatch(url.pathname.slice('/v1/knowledge/'.length),await request.json(),env)); }
  catch(error) {
    if(error instanceof KnowledgeError)return errorResponse(error.status===409?'KNOWLEDGE_CONFLICT':'KNOWLEDGE_ERROR',error.message,error.status);
    if(error instanceof SyntaxError)return errorResponse('INVALID_JSON','请求必须是有效 JSON',400);
    if(/UNIQUE constraint failed/.test(error.message))return errorResponse('KNOWLEDGE_CONFLICT','同库内容及元数据重复',409);
    if(/必须|不能|格式/.test(error.message))return errorResponse('INVALID_PARAMETER',error.message,400);
    throw error;
  }
}
