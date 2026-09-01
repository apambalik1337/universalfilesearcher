"""
database.py

SQLite-backed storage and search index.

Tables:
  - files:   one row per indexed file (path, type, mtime, status, error)
  - records: one row per normalized searchable "hit" extracted from a file,
             mirrored into an FTS5 virtual table for fast full text search
             across every file type at once.
  - meta:    small key/value store -- indexed root folder, last-indexed
             timestamp, and the settings used for the last index run
             (used for "current folder only" scope and "index up to date"
             status).

Search features:
  - filename search (against files.file_name, independent of FTS content)
  - relevance ranking with tiers (exact phrase > multi-term match >
    filename match > partial match)
  - category/extension filtering
  - folder-scope filtering (recursive vs. top-level only)
  - results grouped by file, each carrying its individual matches
  - sorting by relevance / file name / file type / file path / match count

Design:
  - `records_fts` is an external-content FTS5 table pointing at `records`,
    so indexed text lives once and FTS5 just maintains a search index over
    it.
  - A full index wipes previous data so nothing is ever indexed twice. A
    rescan of the *same* root folder instead indexes incrementally: files
    whose `modified_time` hasn't changed since the last run are left
    untouched (see `get_file_mtimes` / `delete_files` in indexer.py), and
    files that disappeared from disk are removed.
  - `_ensure_column` lets older on-disk databases upgrade in place when a
    new version adds a column (e.g. `slide` for PPTX support), so users
    don't lose their index just because the app was updated.
"""

import os
import re
import sqlite3
import threading

SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT UNIQUE NOT NULL,
    file_name TEXT NOT NULL,
    extension TEXT NOT NULL,
    modified_time REAL,
    file_size INTEGER,
    status TEXT NOT NULL,          -- 'indexed' | 'failed' | 'unsupported' | 'skipped'
    error TEXT,
    warning TEXT,
    record_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    sheet TEXT,
    cell TEXT,
    row_num INTEGER,
    column_name TEXT,
    page INTEGER,
    slide INTEGER,
    location TEXT
);

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE INDEX IF NOT EXISTS idx_records_file_id ON records(file_id);
CREATE INDEX IF NOT EXISTS idx_files_extension ON files(extension);
CREATE INDEX IF NOT EXISTS idx_files_status ON files(status);

CREATE VIRTUAL TABLE IF NOT EXISTS records_fts USING fts5(
    content,
    content='records',
    content_rowid='id',
    tokenize='unicode61'
);

CREATE TRIGGER IF NOT EXISTS records_ai AFTER INSERT ON records BEGIN
    INSERT INTO records_fts(rowid, content) VALUES (new.id, new.content);
END;

CREATE TRIGGER IF NOT EXISTS records_ad AFTER DELETE ON records BEGIN
    INSERT INTO records_fts(records_fts, rowid, content) VALUES('delete', old.id, old.content);
END;

CREATE TRIGGER IF NOT EXISTS records_au AFTER UPDATE ON records BEGIN
    INSERT INTO records_fts(records_fts, rowid, content) VALUES('delete', old.id, old.content);
    INSERT INTO records_fts(rowid, content) VALUES (new.id, new.content);
END;
"""

# Score tiers used for relevance ranking. Higher wins.
SCORE_EXACT_PHRASE = 1000
SCORE_ALL_TERMS = 400
SCORE_FILENAME = 250
SCORE_PARTIAL = 100

CONTEXT_CHARS_BEFORE = 60
CONTEXT_CHARS_AFTER = 160
MAX_CANDIDATE_RECORDS = 2000  # safety cap before Python-side scoring


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._local = threading.local()
        conn = self._connect()
        conn.executescript(SCHEMA)
        conn.commit()
        _ensure_column(conn, "records", "slide", "INTEGER")
        _ensure_column(conn, "files", "file_size", "INTEGER")

    def _connect(self):
        if not hasattr(self._local, "conn"):
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            self._local.conn = conn
        return self._local.conn

    # ---------- indexing writes ----------

    def reset(self):
        conn = self._connect()
        conn.execute("DELETE FROM records")
        conn.execute("DELETE FROM files")
        conn.commit()

    def get_file_mtimes(self):
        """Return {file_path: modified_time} for every currently-stored file,
        regardless of status. Used by the indexer to decide, on a rescan of
        the same root folder, which files can be skipped because they
        haven't changed on disk since the last run."""
        conn = self._connect()
        rows = conn.execute("SELECT file_path, modified_time FROM files").fetchall()
        return {r["file_path"]: r["modified_time"] for r in rows}

    def delete_files(self, file_paths):
        """Remove rows (and their records, via ON DELETE CASCADE) for files
        that no longer exist on disk -- used during incremental rescans."""
        file_paths = list(file_paths)
        if not file_paths:
            return
        conn = self._connect()
        conn.executemany("DELETE FROM files WHERE file_path = ?", [(p,) for p in file_paths])
        conn.commit()

    def set_meta(self, key: str, value: str):
        conn = self._connect()
        conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        conn.commit()

    def get_meta(self, key: str, default=None):
        conn = self._connect()
        row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def upsert_file_indexed(self, file_path, file_name, extension, mtime, records, warning=None, file_size=None):
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("DELETE FROM files WHERE file_path = ?", (file_path,))
        cur.execute(
            """INSERT INTO files (file_path, file_name, extension, modified_time, file_size,
                                   status, error, warning, record_count)
               VALUES (?, ?, ?, ?, ?, 'indexed', NULL, ?, ?)""",
            (file_path, file_name, extension, mtime, file_size, warning, len(records)),
        )
        file_id = cur.lastrowid
        for rec in records:
            cur.execute(
                """INSERT INTO records (file_id, content, sheet, cell, row_num,
                                         column_name, page, slide, location)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (file_id, rec.content, rec.sheet, rec.cell, rec.row,
                 rec.column, rec.page, rec.slide, rec.location),
            )
        conn.commit()
        return file_id

    def upsert_file_failed(self, file_path, file_name, extension, mtime, error, file_size=None):
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("DELETE FROM files WHERE file_path = ?", (file_path,))
        cur.execute(
            """INSERT INTO files (file_path, file_name, extension, modified_time, file_size,
                                   status, error, record_count)
               VALUES (?, ?, ?, ?, ?, 'failed', ?, 0)""",
            (file_path, file_name, extension, mtime, file_size, error),
        )
        conn.commit()

    def upsert_file_unsupported(self, file_path, file_name, extension, mtime, file_size=None):
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("DELETE FROM files WHERE file_path = ?", (file_path,))
        cur.execute(
            """INSERT INTO files (file_path, file_name, extension, modified_time, file_size, status, record_count)
               VALUES (?, ?, ?, ?, ?, 'unsupported', 0)""",
            (file_path, file_name, extension, mtime, file_size),
        )
        conn.commit()

    def upsert_file_skipped(self, file_path, file_name, extension, mtime, reason, file_size=None):
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("DELETE FROM files WHERE file_path = ?", (file_path,))
        cur.execute(
            """INSERT INTO files (file_path, file_name, extension, modified_time, file_size,
                                   status, error, record_count)
               VALUES (?, ?, ?, ?, ?, 'skipped', ?, 0)""",
            (file_path, file_name, extension, mtime, file_size, reason),
        )
        conn.commit()

    # ---------- stats ----------

    def get_stats(self):
        conn = self._connect()
        row = conn.execute(
            """SELECT
                 SUM(CASE WHEN status='indexed' THEN 1 ELSE 0 END) as indexed,
                 SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) as failed,
                 SUM(CASE WHEN status='unsupported' THEN 1 ELSE 0 END) as unsupported,
                 SUM(CASE WHEN status='skipped' THEN 1 ELSE 0 END) as skipped,
                 COUNT(*) as total
               FROM files"""
        ).fetchone()
        return {
            "indexed": row["indexed"] or 0,
            "failed": row["failed"] or 0,
            "unsupported": row["unsupported"] or 0,
            "skipped": row["skipped"] or 0,
            "total": row["total"] or 0,
        }

    def get_failed_files(self):
        conn = self._connect()
        rows = conn.execute("SELECT file_name, file_path, error FROM files WHERE status='failed'").fetchall()
        return [dict(r) for r in rows]

    def get_unsupported_files(self):
        conn = self._connect()
        rows = conn.execute("SELECT file_name, file_path, extension FROM files WHERE status='unsupported'").fetchall()
        return [dict(r) for r in rows]

    def get_skipped_files(self):
        conn = self._connect()
        rows = conn.execute("SELECT file_name, file_path, error FROM files WHERE status='skipped'").fetchall()
        return [dict(r) for r in rows]

    # ---------- search ----------

    def search(self, query: str,
               search_content=True, search_filenames=True,
               categories=None, scope_folder=None, current_folder_only=False,
               sort_by="relevance", limit_files=200):
        """
        Returns a dict: {
            files: [ { file_path, file_name, extension, category, icon,
                       match_count, best_score,
                       matches: [ {content, snippet, location, match_type, score, ...} ] } ],
            total_matches, total_files
        }
        """
        from parsers import category_for, icon_for  # local import avoids a circular import at module load time

        query = (query or "").strip()
        if not query:
            return {"files": [], "total_matches": 0, "total_files": 0}

        conn = self._connect()

        candidates = []
        if search_content:
            candidates = self._fts_candidates(conn, query)

        terms = _tokenize(query)
        scored = []
        for row in candidates:
            content = row["content"]
            score, match_type = _score_content(content, query, terms)
            if score is None:
                continue
            scored.append((score, match_type, row))

        if search_filenames:
            for row in self._filename_candidates(conn, query, terms):
                score, match_type = _score_filename(row["file_name"], query, terms)
                if score is not None:
                    scored.append((score, match_type, row))

        files_map = {}
        for score, match_type, row in scored:
            extension = row["extension"]
            category = category_for(extension)
            if categories and category not in categories:
                continue

            file_path = row["file_path"]
            if scope_folder:
                if current_folder_only:
                    if os.path.dirname(file_path) != scope_folder.rstrip("/\\"):
                        continue
                else:
                    try:
                        if os.path.commonpath([os.path.abspath(file_path), os.path.abspath(scope_folder)]) != os.path.abspath(scope_folder):
                            continue
                    except ValueError:
                        continue  # different drives on Windows, etc.

            group = files_map.setdefault(file_path, {
                "file_path": file_path,
                "file_name": row["file_name"],
                "extension": extension,
                "category": category,
                "icon": icon_for(extension),
                "matches": [],
                "best_score": 0,
            })

            if match_type == "filename":
                snippet = row["file_name"]
                content_val = row["file_name"]
            else:
                snippet = _build_snippet(row["content"], terms)
                content_val = row["content"]

            match_entry = {
                "content": content_val,
                "snippet": snippet,
                "match_type": match_type,  # 'filename' | 'content'
                "score": score,
                "sheet": row["sheet"] if "sheet" in row.keys() else None,
                "cell": row["cell"] if "cell" in row.keys() else None,
                "row_num": row["row_num"] if "row_num" in row.keys() else None,
                "column_name": row["column_name"] if "column_name" in row.keys() else None,
                "page": row["page"] if "page" in row.keys() else None,
                "slide": row["slide"] if "slide" in row.keys() else None,
                "location": row["location"] if "location" in row.keys() else None,
            }
            group["matches"].append(match_entry)
            group["best_score"] = max(group["best_score"], score)

        for group in files_map.values():
            seen = set()
            deduped = []
            for m in group["matches"]:
                key = (m["match_type"], m["content"], m["location"], m["cell"], m["page"], m["slide"], m["row_num"])
                if key in seen:
                    continue
                seen.add(key)
                deduped.append(m)
            deduped.sort(key=lambda m: -m["score"])
            group["matches"] = deduped
            group["match_count"] = len(deduped)

        files_list = list(files_map.values())
        _sort_files(files_list, sort_by)
        files_list = files_list[:limit_files]

        total_matches = sum(f["match_count"] for f in files_list)
        return {
            "files": files_list,
            "total_matches": total_matches,
            "total_files": len(files_list),
        }

    def _fts_candidates(self, conn, query):
        fts_query = _build_fts_query(query)
        try:
            rows = conn.execute(
                """
                SELECT f.file_path, f.file_name, f.extension,
                       r.content, r.sheet, r.cell, r.row_num, r.column_name,
                       r.page, r.slide, r.location
                FROM records_fts
                JOIN records r ON r.id = records_fts.rowid
                JOIN files f ON f.id = r.file_id
                WHERE records_fts MATCH ?
                LIMIT ?
                """,
                (fts_query, MAX_CANDIDATE_RECORDS),
            ).fetchall()
            return rows
        except sqlite3.OperationalError:
            like_query = f"%{query}%"
            rows = conn.execute(
                """
                SELECT f.file_path, f.file_name, f.extension,
                       r.content, r.sheet, r.cell, r.row_num, r.column_name,
                       r.page, r.slide, r.location
                FROM records r
                JOIN files f ON f.id = r.file_id
                WHERE r.content LIKE ? ESCAPE '\\'
                LIMIT ?
                """,
                (like_query, MAX_CANDIDATE_RECORDS),
            ).fetchall()
            return rows

    def _filename_candidates(self, conn, query, terms):
        search_terms = terms or [query]
        clauses = " OR ".join(["file_name LIKE ? ESCAPE '\\'"] * len(search_terms))
        params = [f"%{t}%" for t in search_terms]
        rows = conn.execute(
            f"""
            SELECT file_path, file_name, extension, NULL as content, NULL as sheet,
                   NULL as cell, NULL as row_num, NULL as column_name, NULL as page,
                   NULL as slide, NULL as location
            FROM files
            WHERE status = 'indexed' AND ({clauses})
            LIMIT ?
            """,
            (*params, MAX_CANDIDATE_RECORDS),
        ).fetchall()
        return rows


def _ensure_column(conn, table, column, coltype):
    """Add a column if it doesn't already exist -- lets old DBs upgrade in place."""
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")
        conn.commit()


def _tokenize(query: str):
    cleaned = "".join(ch if (ch.isalnum() or ch.isspace()) else " " for ch in query)
    return [t for t in cleaned.split() if t.upper() not in ("AND", "OR", "NOT")]


def _build_fts_query(query: str) -> str:
    """
    Build a broad-recall FTS5 MATCH query. Precise ranking (exact phrase vs.
    partial match) happens afterwards in Python so the FTS query here only
    needs to fetch a generous candidate set.
    """
    if re.search(r"\bAND\b|\bOR\b", query):
        tokens = query.split()
        parts = []
        for tok in tokens:
            if tok in ("AND", "OR", "NOT"):
                parts.append(tok)
            else:
                cleaned_tok = "".join(ch for ch in tok if ch.isalnum())
                if cleaned_tok:
                    parts.append(f"{cleaned_tok}*")
        return " ".join(parts) if parts else f"{query}*"

    terms = _tokenize(query)
    if not terms:
        return f'"{query}"'
    return " ".join(f"{t}*" for t in terms)


def _score_content(content: str, query: str, terms):
    """Returns (score, match_type) or (None, None) if this candidate should be excluded."""
    lower_content = content.lower()
    lower_query = query.lower().strip()

    contains_phrase = lower_query in lower_content
    if contains_phrase and len(terms) > 1:
        return SCORE_EXACT_PHRASE, "content"

    matched_terms = sum(1 for t in terms if t.lower() in lower_content)
    if terms and matched_terms == len(terms) and len(terms) > 1:
        return SCORE_ALL_TERMS, "content"
    if matched_terms > 0:
        return SCORE_PARTIAL + matched_terms * 10, "content"

    return None, None


def _score_filename(file_name: str, query: str, terms):
    lower_name = file_name.lower()
    lower_query = query.lower().strip()

    if lower_query in lower_name:
        return SCORE_FILENAME + 50, "filename"

    matched = sum(1 for t in terms if t.lower() in lower_name)
    if matched > 0:
        return SCORE_FILENAME - (len(terms) - matched) * 10, "filename"

    return None, None


def _build_snippet(content: str, terms) -> str:
    """
    Extract a short window of text around the first matched term so result
    cards show relevant context instead of the whole record.
    """
    if not content:
        return ""
    if len(content) <= CONTEXT_CHARS_BEFORE + CONTEXT_CHARS_AFTER:
        return content

    lower_content = content.lower()
    pos = -1
    for t in terms:
        idx = lower_content.find(t.lower())
        if idx != -1 and (pos == -1 or idx < pos):
            pos = idx
    if pos == -1:
        pos = 0

    start = max(0, pos - CONTEXT_CHARS_BEFORE)
    end = min(len(content), pos + CONTEXT_CHARS_AFTER)
    snippet = content[start:end]
    if start > 0:
        snippet = "..." + snippet
    if end < len(content):
        snippet = snippet + "..."
    return snippet


def _sort_files(files_list, sort_by):
    if sort_by == "name":
        files_list.sort(key=lambda f: f["file_name"].lower())
    elif sort_by == "type":
        files_list.sort(key=lambda f: (f["category"], f["file_name"].lower()))
    elif sort_by == "path":
        files_list.sort(key=lambda f: f["file_path"].lower())
    elif sort_by == "matches":
        files_list.sort(key=lambda f: -f.get("match_count", 0))
    else:  # relevance (default)
        files_list.sort(key=lambda f: (-f["best_score"], f["file_name"].lower()))
