"""
SQLite database layer.
All schema creation, CRUD operations, and query helpers.

Uses Python's built-in sqlite3 — no ORM overhead, no migrations.
Schema is created via CREATE TABLE IF NOT EXISTS on every init_db() call.

Thread safety: WAL mode enabled. Each call opens/closes its own connection.
"""

import json
import logging
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

DB_PATH: str = os.getenv("DATABASE_PATH", "data/sector_intel.db")


# ─── Connection ───────────────────────────────────────────────────────────────

def get_connection() -> sqlite3.Connection:
    """Return an sqlite3 connection with row_factory and WAL mode enabled."""
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ─── Schema ───────────────────────────────────────────────────────────────────

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS companies (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    sector      TEXT NOT NULL,
    ticker      TEXT,
    exchange    TEXT,
    ir_url      TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS documents (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id   TEXT NOT NULL REFERENCES companies(id),
    source_url   TEXT NOT NULL,
    doc_type     TEXT,
    period       TEXT,
    headline     TEXT,
    date_fetched TEXT,
    file_path    TEXT,
    parse_status TEXT NOT NULL DEFAULT 'pending',
    chunk_count  INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT DEFAULT (datetime('now')),
    UNIQUE(company_id, source_url)
);

CREATE TABLE IF NOT EXISTS metrics (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id    TEXT NOT NULL REFERENCES companies(id),
    period        TEXT NOT NULL,
    metric_name   TEXT NOT NULL,
    metric_value  REAL,
    unit          TEXT,
    direction     TEXT,
    source_doc_id INTEGER REFERENCES documents(id),
    extracted_at  TEXT NOT NULL DEFAULT (datetime('now')),
    validated     INTEGER NOT NULL DEFAULT 0,
    UNIQUE(company_id, period, metric_name)
);

CREATE TABLE IF NOT EXISTS synthesis (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    sector              TEXT NOT NULL,
    period_range        TEXT,
    synthesis_text      TEXT,
    investing_lens_text TEXT,
    generated_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS refresh_log (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at           TEXT NOT NULL DEFAULT (datetime('now')),
    sector           TEXT,
    docs_checked     INTEGER NOT NULL DEFAULT 0,
    new_docs_found   INTEGER NOT NULL DEFAULT 0,
    errors           TEXT NOT NULL DEFAULT '[]',
    duration_seconds REAL
);

CREATE INDEX IF NOT EXISTS idx_metrics_company_period
    ON metrics(company_id, period);

CREATE INDEX IF NOT EXISTS idx_metrics_company_name
    ON metrics(company_id, metric_name);

CREATE INDEX IF NOT EXISTS idx_documents_company
    ON documents(company_id);

CREATE INDEX IF NOT EXISTS idx_synthesis_sector
    ON synthesis(sector, generated_at);

CREATE TABLE IF NOT EXISTS chunks (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id       INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index  INTEGER NOT NULL,
    page_num     INTEGER,
    text         TEXT NOT NULL,
    char_count   INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT DEFAULT (datetime('now')),
    UNIQUE(doc_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_chunks_doc
    ON chunks(doc_id);
"""

def init_db() -> None:
    """
    Create all tables and indexes if they don't exist.
    Safe to call on every startup — idempotent.
    Runs ALTER TABLE migrations for columns added after initial schema.
    """
    with get_connection() as conn:
        conn.executescript(_SCHEMA_SQL)
        # ── Schema migrations (safe to run on existing databases) ─────────────
        for migration in [
            "ALTER TABLE documents ADD COLUMN headline TEXT",
            "ALTER TABLE documents ADD COLUMN file_path TEXT",
        ]:
            try:
                conn.execute(migration)
            except Exception:
                pass  # Column already exists — expected on fresh runs
    logger.info(f"Database ready at: {DB_PATH}")


# ─── Chunks CRUD ──────────────────────────────────────────────────────────────

def chunks_exist(doc_id: int) -> bool:
    """Return True if this document already has chunks stored."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM chunks WHERE doc_id = ?", (doc_id,)
        ).fetchone()
    return row[0] > 0


def insert_chunks(doc_id: int, chunks: list[dict]) -> int:
    """
    Insert chunks for a document. Each dict: chunk_index, page_num, text, char_count.
    Uses INSERT OR IGNORE — safe to call twice (idempotent).
    Returns number of rows actually inserted.
    """
    with get_connection() as conn:
        cursor = conn.executemany(
            """
            INSERT OR IGNORE INTO chunks (doc_id, chunk_index, page_num, text, char_count)
            VALUES (:doc_id, :chunk_index, :page_num, :text, :char_count)
            """,
            [{**c, "doc_id": doc_id} for c in chunks],
        )
        return cursor.rowcount


def get_chunks(doc_id: int) -> list[dict]:
    """Return all chunks for a document, ordered by chunk_index."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM chunks WHERE doc_id = ? ORDER BY chunk_index ASC",
            (doc_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def delete_chunks_for_doc(doc_id: int) -> int:
    """Delete all chunks for a document (for re-parsing). Returns count deleted."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
        return cursor.rowcount


# ─── Company CRUD ─────────────────────────────────────────────────────────────


def insert_company(
    company_id: str,
    name: str,
    sector: str,
    ticker: Optional[str] = None,
    exchange: Optional[str] = None,
    ir_url: Optional[str] = None,
) -> None:
    """Insert company if not already present (INSERT OR IGNORE)."""
    with get_connection() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO companies (id, name, sector, ticker, exchange, ir_url)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (company_id, name, sector, ticker, exchange, ir_url),
        )


def get_companies_by_sector(sector: str) -> list[dict]:
    """Return all companies for a sector, ordered by name."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM companies WHERE sector = ? ORDER BY name",
            (sector,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_all_sectors() -> list[str]:
    """Return distinct sector values from the companies table."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT DISTINCT sector FROM companies ORDER BY sector"
        ).fetchall()
    return [r["sector"] for r in rows]


def get_company(company_id: str) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM companies WHERE id = ?", (company_id,)
        ).fetchone()
    return dict(row) if row else None


# ─── Document CRUD ────────────────────────────────────────────────────────────

def document_exists(company_id: str, source_url: str) -> bool:
    """True if this URL has already been fetched for this company."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM documents WHERE company_id = ? AND source_url = ?",
            (company_id, source_url),
        ).fetchone()
    return row is not None


def insert_document(
    company_id: str,
    source_url: str,
    doc_type: str,
    period: str,
    parse_status: str = "pending",
    headline: Optional[str] = None,
) -> int:
    """
    Insert a document record. Returns the document id.
    If the URL already exists (UNIQUE constraint), returns the existing id.
    """
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO documents
                (company_id, source_url, doc_type, period, headline, date_fetched, parse_status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (company_id, source_url, doc_type, period, headline, now, parse_status),
        )
        if cursor.lastrowid and cursor.lastrowid != 0:
            return cursor.lastrowid
        # Row already existed — fetch its id
        row = conn.execute(
            "SELECT id FROM documents WHERE company_id = ? AND source_url = ?",
            (company_id, source_url),
        ).fetchone()
        return row["id"]


def update_file_path(doc_id: int, file_path: str) -> None:
    """Store the local downloaded file path and mark document as 'downloaded'."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE documents SET file_path = ?, parse_status = 'downloaded' WHERE id = ?",
            (file_path, doc_id),
        )


def update_document_status(doc_id: int, status: str, chunk_count: int = 0) -> None:
    """Update parse_status and chunk_count after processing."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE documents SET parse_status = ?, chunk_count = ? WHERE id = ?",
            (status, chunk_count, doc_id),
        )


def get_documents(company_id: str) -> list[dict]:
    """Return all documents for a company, newest period first."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM documents WHERE company_id = ? ORDER BY period DESC",
            (company_id,),
        ).fetchall()
    return [dict(r) for r in rows]


# ─── Metrics CRUD ─────────────────────────────────────────────────────────────

def upsert_metric(
    company_id: str,
    period: str,
    metric_name: str,
    metric_value: float,
    unit: Optional[str] = None,
    direction: Optional[str] = None,
    source_doc_id: Optional[int] = None,
    validated: int = 1,
) -> None:
    """
    Insert or update a single metric value.
    The UNIQUE(company_id, period, metric_name) constraint ensures idempotency.
    """
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO metrics
                (company_id, period, metric_name, metric_value, unit,
                 direction, source_doc_id, validated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(company_id, period, metric_name) DO UPDATE SET
                metric_value  = excluded.metric_value,
                unit          = excluded.unit,
                direction     = excluded.direction,
                source_doc_id = excluded.source_doc_id,
                validated     = excluded.validated,
                extracted_at  = datetime('now')
            """,
            (company_id, period, metric_name, metric_value,
             unit, direction, source_doc_id, validated),
        )


def get_previous_metric_value(
    company_id: str, metric_name: str, before_period: str
) -> Optional[float]:
    """
    Return the metric_value for the period immediately before before_period.
    Used to compute directional change.
    """
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT metric_value FROM metrics
            WHERE company_id = ? AND metric_name = ? AND period < ?
            ORDER BY period DESC
            LIMIT 1
            """,
            (company_id, metric_name, before_period),
        ).fetchone()
    return row["metric_value"] if row else None


def compute_direction(current: float, previous: Optional[float], threshold: float = 0.001) -> str:
    """Return 'up', 'down', or 'flat' based on change vs previous period."""
    if previous is None or current is None:
        return "flat"
    delta = current - previous
    if abs(delta) <= abs(previous) * threshold:
        return "flat"
    return "up" if delta > 0 else "down"


def get_metrics_dataframe(
    company_id: str,
    metric_names: Optional[list[str]] = None,
) -> pd.DataFrame:
    """
    Return a long-format DataFrame with columns:
    [period, metric_name, metric_value, unit, direction]
    Sorted by period ASC.
    """
    query = """
        SELECT period, metric_name, metric_value, unit, direction
        FROM metrics
        WHERE company_id = ?
    """
    params: list = [company_id]

    if metric_names:
        placeholders = ",".join("?" * len(metric_names))
        query += f" AND metric_name IN ({placeholders})"
        params.extend(metric_names)

    query += " ORDER BY period ASC, metric_name ASC"

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()

    if not rows:
        return pd.DataFrame(columns=["period", "metric_name", "metric_value", "unit", "direction"])

    return pd.DataFrame([dict(r) for r in rows])


def get_latest_metrics(company_id: str) -> dict[str, dict]:
    """
    Return the most recent value for each metric as a dict keyed by metric_name.
    Finds the latest period, then returns all metrics for that period.
    """
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT metric_name, metric_value, unit, direction, period
            FROM metrics
            WHERE company_id = ?
              AND period = (SELECT MAX(period) FROM metrics WHERE company_id = ?)
            """,
            (company_id, company_id),
        ).fetchall()
    return {r["metric_name"]: dict(r) for r in rows}


def get_metrics_summary_for_sector(sector: str, last_n_quarters: int = 4) -> list[dict]:
    """
    Return aggregated metric data for all companies in a sector over the last N quarters.
    Used by the synthesis engine.
    """
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT m.company_id, c.name as company_name, m.period,
                   m.metric_name, m.metric_value, m.unit, m.direction
            FROM metrics m
            JOIN companies c ON c.id = m.company_id
            WHERE c.sector = ?
              AND m.period IN (
                  SELECT DISTINCT period FROM metrics
                  WHERE company_id IN (
                      SELECT id FROM companies WHERE sector = ?
                  )
                  ORDER BY period DESC
                  LIMIT ?
              )
            ORDER BY m.company_id, m.period DESC, m.metric_name
            """,
            (sector, sector, last_n_quarters),
        ).fetchall()
    return [dict(r) for r in rows]


# ─── Synthesis CRUD ───────────────────────────────────────────────────────────

def insert_synthesis(
    sector: str,
    period_range: str,
    synthesis_text: str,
    investing_lens_text: str,
) -> None:
    """Insert a new synthesis row (history is preserved — rows are never overwritten)."""
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO synthesis (sector, period_range, synthesis_text, investing_lens_text)
            VALUES (?, ?, ?, ?)
            """,
            (sector, period_range, synthesis_text, investing_lens_text),
        )


def get_synthesis(sector: str) -> Optional[dict]:
    """Return the most recent synthesis for a sector, or None."""
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT * FROM synthesis
            WHERE sector = ?
            ORDER BY generated_at DESC
            LIMIT 1
            """,
            (sector,),
        ).fetchone()
    return dict(row) if row else None


# ─── Refresh Log ──────────────────────────────────────────────────────────────

def log_refresh(
    sector: str,
    docs_checked: int,
    new_docs_found: int,
    errors: list[str],
    duration_seconds: float,
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO refresh_log
                (sector, docs_checked, new_docs_found, errors, duration_seconds)
            VALUES (?, ?, ?, ?, ?)
            """,
            (sector, docs_checked, new_docs_found, json.dumps(errors), duration_seconds),
        )


def get_refresh_log(limit: int = 10) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM refresh_log ORDER BY run_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        # Deserialise errors JSON string → list
        try:
            d["errors"] = json.loads(d.get("errors", "[]"))
        except (json.JSONDecodeError, TypeError):
            d["errors"] = []
        result.append(d)
    return result
