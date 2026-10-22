"""工具调用回执，弥补外部副作用与图检查点之间的提交窗口。"""

import json
import sqlite3


class CallJournal:
    def __init__(self, path):
        self.connection = sqlite3.connect(path)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("""CREATE TABLE IF NOT EXISTS agent_calls (
            task_id TEXT NOT NULL, call_key TEXT NOT NULL, status TEXT NOT NULL,
            result TEXT, PRIMARY KEY(task_id, call_key))""")
        self.connection.execute("""CREATE TABLE IF NOT EXISTS agent_pauses (
            task_id TEXT PRIMARY KEY)""")
        self.connection.commit()

    def get(self, task_id, key):
        row = self.connection.execute(
            "SELECT status, result FROM agent_calls WHERE task_id=? AND call_key=?",
            (task_id, key)).fetchone()
        return (row[0], json.loads(row[1]) if row[1] else None) if row else None

    def save(self, task_id, key, status, result=None):
        with self.connection:
            self.connection.execute("INSERT OR REPLACE INTO agent_calls VALUES (?, ?, ?, ?)",
                                    (task_id, key, status, json.dumps(result, ensure_ascii=False)))

    def pause(self, task_id):
        with self.connection:
            self.connection.execute("INSERT OR IGNORE INTO agent_pauses VALUES (?)", (task_id,))

    def paused(self, task_id):
        return self.connection.execute("SELECT 1 FROM agent_pauses WHERE task_id=?",
                                       (task_id,)).fetchone() is not None

    def clear_pause(self, task_id):
        with self.connection:
            self.connection.execute("DELETE FROM agent_pauses WHERE task_id=?", (task_id,))

    def close(self):
        self.connection.close()
