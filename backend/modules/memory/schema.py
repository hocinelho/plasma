"""
Plasma memory — SQLite schema.

Three main tables, each with an FTS5 mirror for fast keyword search:
- conversations:  message history (role, content, session_id, timestamp)
- facts:          durable knowledge (e.g., "user prefers dark mode")
- skills_meta:    metadata about skills the agent has built (name, triggers, usage count)
"""

SCHEMA_SQL = """
-- Main conversations table
CREATE TABLE IF NOT EXISTS conversations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL,
    role        TEXT NOT NULL CHECK(role IN ('user','assistant','system','tool')),
    content     TEXT NOT NULL,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_conv_session ON conversations(session_id);
CREATE INDEX IF NOT EXISTS idx_conv_created ON conversations(created_at);

-- FTS5 mirror for conversations (content-only, external content table pattern)
CREATE VIRTUAL TABLE IF NOT EXISTS conversations_fts USING fts5(
    content,
    content='conversations',
    content_rowid='id',
    tokenize='porter unicode61'
);

-- Keep FTS in sync via triggers
CREATE TRIGGER IF NOT EXISTS conv_ai AFTER INSERT ON conversations BEGIN
    INSERT INTO conversations_fts(rowid, content) VALUES (new.id, new.content);
END;
CREATE TRIGGER IF NOT EXISTS conv_ad AFTER DELETE ON conversations BEGIN
    INSERT INTO conversations_fts(conversations_fts, rowid, content) VALUES('delete', old.id, old.content);
END;
CREATE TRIGGER IF NOT EXISTS conv_au AFTER UPDATE ON conversations BEGIN
    INSERT INTO conversations_fts(conversations_fts, rowid, content) VALUES('delete', old.id, old.content);
    INSERT INTO conversations_fts(rowid, content) VALUES (new.id, new.content);
END;

-- Facts: stable truths about the user and the world
CREATE TABLE IF NOT EXISTS facts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    category    TEXT NOT NULL,      -- e.g. 'preference', 'identity', 'project', 'person'
    content     TEXT NOT NULL,
    confidence  REAL DEFAULT 1.0,   -- 0.0 to 1.0
    source      TEXT,               -- e.g. 'user_stated', 'inferred', 'tool'
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_facts_category ON facts(category);

CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(
    content,
    content='facts',
    content_rowid='id',
    tokenize='porter unicode61'
);

CREATE TRIGGER IF NOT EXISTS facts_ai AFTER INSERT ON facts BEGIN
    INSERT INTO facts_fts(rowid, content) VALUES (new.id, new.content);
END;
CREATE TRIGGER IF NOT EXISTS facts_ad AFTER DELETE ON facts BEGIN
    INSERT INTO facts_fts(facts_fts, rowid, content) VALUES('delete', old.id, old.content);
END;
CREATE TRIGGER IF NOT EXISTS facts_au AFTER UPDATE ON facts BEGIN
    INSERT INTO facts_fts(facts_fts, rowid, content) VALUES('delete', old.id, old.content);
    INSERT INTO facts_fts(rowid, content) VALUES (new.id, new.content);
END;

-- Skills metadata (actual skill content lives as markdown files; this tracks usage)
CREATE TABLE IF NOT EXISTS skills_meta (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    description TEXT,
    triggers    TEXT,              -- JSON array of trigger phrases
    file_path   TEXT NOT NULL,     -- path to the skill's .md file
    usage_count INTEGER DEFAULT 0,
    last_used   TIMESTAMP,
    success_rate REAL DEFAULT 1.0,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_skills_name ON skills_meta(name);

CREATE VIRTUAL TABLE IF NOT EXISTS skills_fts USING fts5(
    name, description, triggers,
    content='skills_meta',
    content_rowid='id',
    tokenize='porter unicode61'
);

CREATE TRIGGER IF NOT EXISTS skills_ai AFTER INSERT ON skills_meta BEGIN
    INSERT INTO skills_fts(rowid, name, description, triggers)
    VALUES (new.id, new.name, new.description, new.triggers);
END;
CREATE TRIGGER IF NOT EXISTS skills_ad AFTER DELETE ON skills_meta BEGIN
    INSERT INTO skills_fts(skills_fts, rowid, name, description, triggers)
    VALUES('delete', old.id, old.name, old.description, old.triggers);
END;
CREATE TRIGGER IF NOT EXISTS skills_au AFTER UPDATE ON skills_meta BEGIN
    INSERT INTO skills_fts(skills_fts, rowid, name, description, triggers)
    VALUES('delete', old.id, old.name, old.description, old.triggers);
    INSERT INTO skills_fts(rowid, name, description, triggers)
    VALUES (new.id, new.name, new.description, new.triggers);
END;
"""