-- 知识原文与索引任务独立于发布业务，变更通过触发器原子建立同步任务。
CREATE TABLE knowledge_bases (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL CHECK(kind IN ('generic', 'publisher-errors')),
  active_profile TEXT NOT NULL,
  profiles_json TEXT NOT NULL CHECK(json_valid(profiles_json)),
  generation INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE knowledge_documents (
  id TEXT PRIMARY KEY,
  knowledge_base TEXT NOT NULL REFERENCES knowledge_bases(id),
  title TEXT NOT NULL,
  content TEXT NOT NULL,
  metadata_json TEXT NOT NULL CHECK(json_valid(metadata_json)),
  fingerprint TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1,
  deleted INTEGER NOT NULL DEFAULT 0 CHECK(deleted IN (0,1)),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX knowledge_documents_fingerprint ON knowledge_documents(knowledge_base,fingerprint) WHERE deleted=0;
CREATE INDEX knowledge_documents_base ON knowledge_documents(knowledge_base,id);
CREATE TABLE knowledge_index_jobs (
  id TEXT PRIMARY KEY,
  knowledge_base TEXT NOT NULL REFERENCES knowledge_bases(id),
  document_id TEXT NOT NULL REFERENCES knowledge_documents(id),
  revision INTEGER NOT NULL,
  profile_id TEXT NOT NULL,
  operation TEXT NOT NULL CHECK(operation IN ('upsert','delete')),
  status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','processing','submitted','ready','failed')),
  lease_token TEXT,
  lease_until INTEGER,
  mutation_id TEXT,
  submitted_at INTEGER,
  error TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(document_id,revision,profile_id)
);
CREATE INDEX knowledge_jobs_status ON knowledge_index_jobs(knowledge_base,status,lease_until);
CREATE TABLE knowledge_chunks (
  id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL REFERENCES knowledge_index_jobs(id),
  document_id TEXT NOT NULL REFERENCES knowledge_documents(id),
  knowledge_base TEXT NOT NULL,
  revision INTEGER NOT NULL,
  profile_id TEXT NOT NULL,
  chunk_index INTEGER NOT NULL,
  start_index INTEGER NOT NULL,
  end_index INTEGER NOT NULL,
  content TEXT NOT NULL
);
CREATE INDEX knowledge_chunks_document ON knowledge_chunks(document_id,profile_id,revision);
CREATE TRIGGER knowledge_document_insert AFTER INSERT ON knowledge_documents BEGIN
  UPDATE knowledge_bases SET generation=generation+1 WHERE id=NEW.knowledge_base;
  INSERT INTO knowledge_index_jobs(id,knowledge_base,document_id,revision,profile_id,operation)
    SELECT lower(hex(randomblob(16))),NEW.knowledge_base,NEW.id,NEW.revision,key,'upsert'
    FROM json_each((SELECT profiles_json FROM knowledge_bases WHERE id=NEW.knowledge_base));
END;
CREATE TRIGGER knowledge_document_revision AFTER UPDATE OF revision ON knowledge_documents BEGIN
  UPDATE knowledge_bases SET generation=generation+1 WHERE id=NEW.knowledge_base;
  INSERT INTO knowledge_index_jobs(id,knowledge_base,document_id,revision,profile_id,operation)
    SELECT lower(hex(randomblob(16))),NEW.knowledge_base,NEW.id,NEW.revision,key,
      CASE WHEN NEW.deleted=1 THEN 'delete' ELSE 'upsert' END
    FROM json_each((SELECT profiles_json FROM knowledge_bases WHERE id=NEW.knowledge_base));
END;
