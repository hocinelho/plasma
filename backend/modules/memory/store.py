"""
Plasma memory store — CRUD + search on top of SQLite FTS5.

Design choices:
- Synchronous sqlite3 for simplicity; wrap in asyncio.to_thread() from async code.
- Connection per call, check_same_thread=False. FastAPI serves concurrently, sqlite handles it.
- Database lives under .plasma/memory.sqlite (gitignored).
"""
from __future__ import annotations
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from .schema import SCHEMA_SQL

# Default DB location: ./.plasma/memory.sqlite relative to project root
DEFAULT_DB_PATH = Path(__file__).resolve().parents[3] / ".plasma" / "memory.sqlite"


class MemoryStore:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(
            self.db_path,
            check_same_thread=False,
            isolation_level=None,  # autocommit
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        try:
            yield conn
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._conn() as c:
            c.executescript(SCHEMA_SQL)

    # ---------------------------------------------------------------
    # Conversations
    # ---------------------------------------------------------------
    def add_message(self, session_id: str, role: str, content: str) -> int:
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO conversations(session_id, role, content) VALUES (?, ?, ?)",
                (session_id, role, content),
            )
            return int(cur.lastrowid)

    def get_conversation(self, session_id: str, limit: int = 50) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT id, session_id, role, content, created_at "
                "FROM conversations WHERE session_id = ? "
                "ORDER BY id ASC LIMIT ?",
                (session_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def search_conversations(self, query: str, limit: int = 10) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT c.id, c.session_id, c.role, c.content, c.created_at "
                "FROM conversations_fts f JOIN conversations c ON c.id = f.rowid "
                "WHERE conversations_fts MATCH ? "
                "ORDER BY rank LIMIT ?",
                (query, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    # ---------------------------------------------------------------
    # Facts
    # ---------------------------------------------------------------
    def add_fact(
        self,
        category: str,
        content: str,
        confidence: float = 1.0,
        source: Optional[str] = None,
    ) -> int:
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO facts(category, content, confidence, source) VALUES (?, ?, ?, ?)",
                (category, content, confidence, source),
            )
            return int(cur.lastrowid)

    def get_facts(self, category: Optional[str] = None, limit: int = 100) -> list[dict]:
        with self._conn() as c:
            if category:
                rows = c.execute(
                    "SELECT * FROM facts WHERE category = ? ORDER BY updated_at DESC LIMIT ?",
                    (category, limit),
                ).fetchall()
            else:
                rows = c.execute(
                    "SELECT * FROM facts ORDER BY updated_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [dict(r) for r in rows]

    def search_facts(self, query: str, limit: int = 10) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT f.* FROM facts_fts ft JOIN facts f ON f.id = ft.rowid "
                "WHERE facts_fts MATCH ? ORDER BY rank LIMIT ?",
                (query, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def delete_fact(self, fact_id: int) -> bool:
        with self._conn() as c:
            cur = c.execute("DELETE FROM facts WHERE id = ?", (fact_id,))
            return cur.rowcount > 0

    # ---------------------------------------------------------------
    # Skills metadata
    # ---------------------------------------------------------------
    def register_skill(
        self,
        name: str,
        description: str,
        triggers: list[str],
        file_path: str,
    ) -> int:
        with self._conn() as c:
            cur = c.execute(
                "INSERT OR REPLACE INTO skills_meta(name, description, triggers, file_path) "
                "VALUES (?, ?, ?, ?)",
                (name, description, json.dumps(triggers), file_path),
            )
            return int(cur.lastrowid)

    def list_skills(self) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM skills_meta ORDER BY usage_count DESC, name ASC"
            ).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                try:
                    d["triggers"] = json.loads(d["triggers"]) if d["triggers"] else []
                except json.JSONDecodeError:
                    d["triggers"] = []
                result.append(d)
            return result

    def search_skills(self, query: str, limit: int = 5) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT s.* FROM skills_fts f JOIN skills_meta s ON s.id = f.rowid "
                "WHERE skills_fts MATCH ? ORDER BY rank LIMIT ?",
                (query, limit),
            ).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                try:
                    d["triggers"] = json.loads(d["triggers"]) if d["triggers"] else []
                except json.JSONDecodeError:
                    d["triggers"] = []
                out.append(d)
            return out

    def mark_skill_used(self, name: str, success: bool = True) -> None:
        with self._conn() as c:
            row = c.execute(
                "SELECT usage_count, success_rate FROM skills_meta WHERE name = ?",
                (name,),
            ).fetchone()
            if not row:
                return
            n = row["usage_count"] + 1
            new_rate = ((row["success_rate"] * row["usage_count"]) + (1.0 if success else 0.0)) / n
            c.execute(
                "UPDATE skills_meta SET usage_count = ?, success_rate = ?, last_used = CURRENT_TIMESTAMP "
                "WHERE name = ?",
                (n, new_rate, name),
            )

    # ---------------------------------------------------------------
    # Utility
    # ---------------------------------------------------------------
    def close(self) -> None:
        pass  # using per-call connections; nothing to close