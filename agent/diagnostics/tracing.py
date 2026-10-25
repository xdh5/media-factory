"""在现有 Agent SQLite 内保存脱敏调用链路。"""

from contextlib import contextmanager
import json
import sqlite3
import time
import uuid

from .redaction import redact


class TraceStore:
    def __init__(self, database):
        self.database = database
        with self.connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS agent_runs (
                    id TEXT PRIMARY KEY, task_id TEXT, started REAL, ended REAL,
                    status TEXT, verified_success INTEGER, label_source TEXT);
                CREATE TABLE IF NOT EXISTS agent_spans (
                    id TEXT PRIMARY KEY, run_id TEXT, parent_id TEXT, kind TEXT,
                    name TEXT, started REAL, duration REAL, status TEXT,
                    payload TEXT, prompt_tokens INTEGER, completion_tokens INTEGER);
                CREATE INDEX IF NOT EXISTS agent_spans_run ON agent_spans(run_id, started);
                CREATE TABLE IF NOT EXISTS agent_evaluations (
                    id TEXT PRIMARY KEY, created REAL, kind TEXT, report TEXT);
            """)

    def connect(self):
        connection = sqlite3.connect(self.database, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    def start(self, task_id):
        identity = uuid.uuid4().hex
        with self.connect() as connection:
            connection.execute("INSERT INTO agent_runs VALUES (?, ?, ?, NULL, 'running', NULL, NULL)",
                               (identity, task_id, time.time()))
        return identity

    def finish(self, identity, status):
        with self.connect() as connection:
            connection.execute("UPDATE agent_runs SET ended=?, status=? WHERE id=?", (time.time(), status, identity))

    def finish_interrupted(self, identity):
        with self.connect() as connection:
            connection.execute("UPDATE agent_runs SET ended=?, status='interrupted' WHERE id=? AND status='running'", (time.time(), identity))

    def add(self, run_id, kind, name, started, status, payload, usage=None, parent_id=None):
        usage = usage or {}
        identity = uuid.uuid4().hex
        with self.connect() as connection:
            connection.execute("INSERT INTO agent_spans VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (
                identity, run_id, parent_id, kind, name, started, time.time() - started, status,
                json.dumps(redact(payload), ensure_ascii=False, default=str), usage.get("prompt_tokens"), usage.get("completion_tokens")))
        return identity

    def list_runs(self):
        with self.connect() as connection:
            return [dict(row) for row in connection.execute("SELECT * FROM agent_runs ORDER BY started DESC LIMIT 200")]

    def chain(self, run_id):
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM agent_spans WHERE run_id=? ORDER BY started", (run_id,)).fetchall()
        return [{**dict(row), "payload": json.loads(row["payload"])} for row in rows]

    def label(self, run_id, success, source):
        if not source.strip():
            raise ValueError("需要填写人工验收依据")
        with self.connect() as connection:
            if not connection.execute("SELECT 1 FROM agent_runs WHERE id=? AND ended IS NOT NULL", (run_id,)).fetchone():
                raise ValueError("只能标注已结束的真实执行")
            connection.execute("UPDATE agent_runs SET verified_success=?, label_source=? WHERE id=?",
                               (int(success), redact(source), run_id))

    def save_evaluation(self, kind, report):
        identity = uuid.uuid4().hex
        with self.connect() as connection:
            connection.execute("INSERT INTO agent_evaluations VALUES (?, ?, ?, ?)",
                               (identity, time.time(), kind, json.dumps(redact(report), ensure_ascii=False)))
        return identity

    def evaluations(self):
        with self.connect() as connection:
            return [{**dict(row), "report": json.loads(row["report"])} for row in connection.execute(
                "SELECT * FROM agent_evaluations ORDER BY created DESC LIMIT 50")]

    def label_diagnosis(self, evaluation_id, case_id, correct, evidence):
        if type(correct) is not bool or not evidence.strip():
            raise ValueError("需要明确的正确性标签和实际复核依据")
        with self.connect() as connection:
            row = connection.execute("SELECT report FROM agent_evaluations WHERE id=? AND kind='rag'", (evaluation_id,)).fetchone()
            if not row:
                raise ValueError("RAG 评估不存在")
            report = json.loads(row[0])
            case = next((case for case in report["cases"] if case["id"] == case_id), None)
            if not case:
                raise ValueError("评估样本不存在")
            case.update({"human_correct": correct, "review_evidence": redact(evidence)})
            reviewed = [case for case in report["cases"] if type(case.get("human_correct")) is bool]
            report["diagnosis_reviewed_count"] = len(reviewed)
            report["diagnosis_accuracy"] = sum(case["human_correct"] for case in reviewed) / len(reviewed)
            connection.execute("UPDATE agent_evaluations SET report=? WHERE id=?", (json.dumps(report, ensure_ascii=False), evaluation_id))
        return report


class RunObserver:
    def __init__(self, store, run_id, emit=None, knowledge=None):
        self.store, self.run_id, self.emit, self.knowledge = store, run_id, emit, knowledge
        self.diagnoses = {}

    async def event(self, kind, name, payload, started=None, status="ok", usage=None):
        self.store.add(self.run_id, kind, name, started or time.time(), status, payload, usage)
        if self.emit:
            def artifacts(value):
                if isinstance(value, dict):
                    return [path for item in value.values() for path in artifacts(item)]
                if isinstance(value, list):
                    return [path for item in value for path in artifacts(item)]
                return [value] if isinstance(value, str) and value.lower().endswith((".mp4", ".webm", ".mov")) else []
            await self.emit({"kind": kind, "name": name, "status": status, "payload": redact(payload), "artifacts": artifacts(payload)})

    async def diagnose(self, error):
        if not self.knowledge:
            return []
        clean = redact(error)
        # 参数解析错误由调用方修正，额度错误直接报告，无需 Embedding 或模型诊断。
        text = json.dumps(clean, ensure_ascii=False, default=str)
        if any(marker in text for marker in ("JSONDecodeError", "Expecting ',' delimiter", "AllocationQuota.", "Free quota exhausted")):
            return []
        query = text[:4000]
        if query in self.diagnoses:
            return self.diagnoses[query]
        try:
            result = await self.knowledge.search(query, k=4)
            self.diagnoses[query] = result
            return result
        except Exception as exc:
            self.diagnoses[query] = []
            await self.event("retrieval", "故障检索失败", {"error": str(exc)}, status="error")
            return []
