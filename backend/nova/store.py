import json
import sqlite3
from datetime import datetime, timezone
from .config import settings

def connect():
    db = sqlite3.connect(settings.database_path)
    db.row_factory = sqlite3.Row
    return db

def initialize():
    with connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS messages(id TEXT PRIMARY KEY, role TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL, metadata TEXT NOT NULL DEFAULT '{}');
        CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, kind TEXT NOT NULL, status TEXT NOT NULL, request TEXT NOT NULL, result TEXT NOT NULL DEFAULT '{}', events TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY, name TEXT NOT NULL, path TEXT NOT NULL, stack TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS approvals(id TEXT PRIMARY KEY, task_id TEXT NOT NULL, action TEXT NOT NULL, details TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL);
        """)

def now(): return datetime.now(timezone.utc).isoformat()

def save_message(message_id, role, content, metadata=None):
    with connect() as db:
        db.execute("INSERT OR REPLACE INTO messages VALUES(?,?,?,?,?)", (message_id, role, content, now(), json.dumps(metadata or {})))

def messages(limit=100):
    with connect() as db:
        rows = db.execute("SELECT * FROM messages ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) | {"metadata": json.loads(r["metadata"])} for r in reversed(rows)]

def create_task(task_id, kind, request, status="queued"):
    stamp = now()
    with connect() as db:
        db.execute("INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?)", (task_id, kind, status, request, "{}", "[]", stamp, stamp))

def update_task(task_id, status=None, result=None, event=None):
    with connect() as db:
        row = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not row: return None
        events = json.loads(row["events"])
        if event: events.append({"message": event, "at": now()})
        db.execute("UPDATE tasks SET status=?,result=?,events=?,updated_at=? WHERE id=?", (status or row["status"], json.dumps(result if result is not None else json.loads(row["result"])), json.dumps(events), now(), task_id))
        return get_task(task_id)

def get_task(task_id):
    with connect() as db: row = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    return dict(row) | {"result": json.loads(row["result"]), "events": json.loads(row["events"])} if row else None

def list_tasks(limit=30):
    with connect() as db: rows = db.execute("SELECT id FROM tasks ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return [get_task(r["id"]) for r in rows]

def save_project(pid, name, path, stack):
    with connect() as db: db.execute("INSERT OR REPLACE INTO projects VALUES(?,?,?,?,?)", (pid, name, str(path), stack, now()))

def get_project(pid=None):
    with connect() as db:
        row = db.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone() if pid else db.execute("SELECT * FROM projects ORDER BY created_at DESC LIMIT 1").fetchone()
    return dict(row) if row else None

def projects():
    with connect() as db: rows = db.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]

def create_approval(aid, task_id, action, details):
    with connect() as db: db.execute("INSERT INTO approvals VALUES(?,?,?,?,?,?)", (aid, task_id, action, json.dumps(details), "pending", now()))

def resolve_approval(aid, approved):
    with connect() as db:
        updated = db.execute("UPDATE approvals SET status=? WHERE id=? AND status='pending'", ("approved" if approved else "rejected", aid))
        if updated.rowcount != 1:
            return None
        row = db.execute("SELECT * FROM approvals WHERE id=?", (aid,)).fetchone()
    return dict(row) | {"details": json.loads(row["details"])} if row else None

def pending_approvals():
    with connect() as db: rows = db.execute("SELECT * FROM approvals WHERE status='pending' ORDER BY created_at").fetchall()
    return [dict(r) | {"details": json.loads(r["details"])} for r in rows]
