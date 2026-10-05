"""SQLite persistence for single-user ShellSage."""
from __future__ import annotations
import json, sqlite3, threading
from pathlib import Path
from contextlib import contextmanager
from typing import Any, Iterator
SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY,title TEXT NOT NULL DEFAULT '',status TEXT NOT NULL DEFAULT 'active',created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY AUTOINCREMENT,session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,role TEXT NOT NULL,content TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY,session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,goal TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'running',created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,finished_at TEXT);
CREATE TABLE IF NOT EXISTS tool_calls(id INTEGER PRIMARY KEY AUTOINCREMENT,task_id TEXT REFERENCES tasks(id) ON DELETE SET NULL,session_id TEXT REFERENCES sessions(id) ON DELETE SET NULL,tool TEXT NOT NULL,arguments_json TEXT NOT NULL DEFAULT '{}',result_json TEXT NOT NULL DEFAULT '{}',success INTEGER NOT NULL DEFAULT 0,duration_ms REAL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS approvals(id TEXT PRIMARY KEY,task_id TEXT REFERENCES tasks(id) ON DELETE CASCADE,tool TEXT NOT NULL,arguments_json TEXT NOT NULL DEFAULT '{}',status TEXT NOT NULL DEFAULT 'pending',created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,resolved_at TEXT);
CREATE TABLE IF NOT EXISTS audit_events(id INTEGER PRIMARY KEY AUTOINCREMENT,session_id TEXT,task_id TEXT,source TEXT NOT NULL,tool TEXT NOT NULL,arguments_json TEXT NOT NULL DEFAULT '{}',result_json TEXT NOT NULL DEFAULT '{}',success INTEGER,duration_ms REAL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
"""
class Database:
    def __init__(self,path:str|Path):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True);self._local=threading.local();self.initialize()
    def _conn(self):
        c=getattr(self._local,"conn",None)
        if c is None:
            c=sqlite3.connect(self.path,timeout=30,isolation_level=None);c.row_factory=sqlite3.Row;c.execute("PRAGMA foreign_keys=ON");c.execute("PRAGMA busy_timeout=30000");self._local.conn=c
        return c
    def initialize(self):self._conn().executescript(SCHEMA)
    @contextmanager
    def transaction(self)->Iterator[sqlite3.Connection]:
        c=self._conn();c.execute("BEGIN IMMEDIATE")
        try:yield c
        except Exception:c.execute("ROLLBACK");raise
        else:c.execute("COMMIT")
    def create_session(self,session_id,title=""):self._conn().execute("INSERT OR IGNORE INTO sessions(id,title) VALUES(?,?)",(session_id,title))
    def save_message(self,session_id:str,message:dict[str,Any]):
        self._conn().execute("INSERT INTO messages(session_id,role,content) VALUES(?,?,?)",(session_id,message.get("role","unknown"),json.dumps(message,ensure_ascii=False)))
        self._conn().execute("UPDATE sessions SET updated_at=CURRENT_TIMESTAMP WHERE id=?",(session_id,))
    def load_history(self,session_id:str)->list[dict[str,Any]]:
        rows=self._conn().execute("SELECT content FROM messages WHERE session_id=? ORDER BY id",(session_id,)).fetchall()
        out=[]
        for row in rows:
            try:out.append(json.loads(row["content"]))
            except (TypeError,json.JSONDecodeError):out.append({"role":"user","content":row["content"]})
        return out
    def create_task(self,task_id,session_id,goal):self._conn().execute("INSERT INTO tasks(id,session_id,goal) VALUES(?,?,?)",(task_id,session_id,goal))
    def finish_task(self,task_id,status):self._conn().execute("UPDATE tasks SET status=?,updated_at=CURRENT_TIMESTAMP,finished_at=CURRENT_TIMESTAMP WHERE id=?",(status,task_id))
    def record_tool_call(self,task_id,session_id,tool,args,result,duration_ms):self._conn().execute("INSERT INTO tool_calls(task_id,session_id,tool,arguments_json,result_json,success,duration_ms) VALUES(?,?,?,?,?,?,?)",(task_id,session_id,tool,json.dumps(args,ensure_ascii=False),json.dumps(result,ensure_ascii=False),int(bool(result.get("success"))),duration_ms))
    def record_audit(self,source,tool,args,result,duration_ms,session_id=None,task_id=None):self._conn().execute("INSERT INTO audit_events(session_id,task_id,source,tool,arguments_json,result_json,success,duration_ms) VALUES(?,?,?,?,?,?,?,?)",(session_id,task_id,tool,json.dumps(args,ensure_ascii=False),json.dumps(result,ensure_ascii=False),int(bool(result.get("success"))),duration_ms))
    def create_approval(self,approval_id,task_id,tool,args):self._conn().execute("INSERT INTO approvals(id,task_id,tool,arguments_json) VALUES(?,?,?,?)",(approval_id,task_id,tool,json.dumps(args,ensure_ascii=False)))
    def consume_approval(self,approval_id):
        with self.transaction() as c:
            row=c.execute("SELECT id,task_id,tool,arguments_json FROM approvals WHERE id=? AND status='pending'",(approval_id,)).fetchone()
            if row is None:return None
            c.execute("UPDATE approvals SET status='approved',resolved_at=CURRENT_TIMESTAMP WHERE id=? AND status='pending'",(approval_id,))
            return {"id":row["id"],"task_id":row["task_id"],"tool":row["tool"],"arguments":json.loads(row["arguments_json"])}
    def reject_approval(self,approval_id):return self._conn().execute("UPDATE approvals SET status='rejected',resolved_at=CURRENT_TIMESTAMP WHERE id=? AND status='pending'",(approval_id,)).rowcount==1
