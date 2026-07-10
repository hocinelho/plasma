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
            # PA-66 migration: per-user facts. NULL user = shared/global fact.
            try:
                c.execute("ALTER TABLE facts ADD COLUMN user TEXT")
            except sqlite3.OperationalError:
                pass  # column already exists

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
        user: Optional[str] = None,
    ) -> int:
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO facts(category, content, confidence, source, user) "
                "VALUES (?, ?, ?, ?, ?)",
                (category, content, confidence, source, user),
            )
            return int(cur.lastrowid)

    def get_facts_all(self, limit: int = 500) -> list[dict]:
        """Return all facts across all users/categories, newest first."""
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM facts ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_facts(
        self,
        category: Optional[str] = None,
        limit: int = 100,
        user: Optional[str] = None,
    ) -> list[dict]:
        """Fetch facts. With user=<name>, returns that user's facts PLUS shared
        (user IS NULL) facts — personal context layered on top of global."""
        where: list[str] = []
        params: list = []
        if category:
            where.append("category = ?")
            params.append(category)
        if user:
            where.append("(user IS NULL OR user = ?)")
            params.append(user)
        clause = ("WHERE " + " AND ".join(where)) if where else ""
        params.append(limit)
        with self._conn() as c:
            rows = c.execute(
                f"SELECT * FROM facts {clause} ORDER BY updated_at DESC LIMIT ?",
                params,
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

    def get_skills_meta(self) -> list[dict]:
        """Return skills sorted by usage_count descending (alias for list_skills)."""
        return self.list_skills()

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
    # Request latency log
    # ---------------------------------------------------------------
    def log_request(
        self,
        session_id: str,
        turn: int,
        asr_ms: Optional[float] = None,
        llm_ms: Optional[float] = None,
        tts_ms: Optional[float] = None,
        total_ms: Optional[float] = None,
        skill_used: Optional[str] = None,
    ) -> int:
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO request_log(session_id, turn, asr_ms, llm_ms, tts_ms, total_ms, skill_used) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (session_id, turn, asr_ms, llm_ms, tts_ms, total_ms, skill_used),
            )
            return int(cur.lastrowid)

    def get_request_log(self, session_id: str) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT id, session_id, turn, asr_ms, llm_ms, tts_ms, total_ms, skill_used, created_at "
                "FROM request_log WHERE session_id = ? ORDER BY turn ASC",
                (session_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    # ---------------------------------------------------------------
    # Utility
    # ---------------------------------------------------------------
    def close(self) -> None:
        pass  # using per-call connections; nothing to close