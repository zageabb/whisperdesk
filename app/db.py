from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import current_app, g


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE_PATH"])
    return g.db


def close_db(_error: Exception | None = None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_schema(path: str | Path) -> None:
    conn = connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                original_name TEXT NOT NULL,
                stored_path TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('queued','processing','completed','failed')),
                created_at TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT,
                model TEXT NOT NULL,
                language TEXT,
                duration_seconds REAL,
                progress_seconds REAL NOT NULL DEFAULT 0,
                transcript_path TEXT,
                timestamped_path TEXT,
                partial_transcript_path TEXT,
                partial_timestamped_path TEXT,
                error TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_jobs_status_created
                ON jobs(status, created_at);
            """
        )
        columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()
        }
        migrations = {
            "progress_seconds": "REAL NOT NULL DEFAULT 0",
            "partial_transcript_path": "TEXT",
            "partial_timestamped_path": "TEXT",
        }
        for name, definition in migrations.items():
            if name not in columns:
                conn.execute(f"ALTER TABLE jobs ADD COLUMN {name} {definition}")
        conn.commit()
    finally:
        conn.close()


def create_job(job: dict[str, Any]) -> None:
    db = get_db()
    db.execute(
        """
        INSERT INTO jobs (
            id, original_name, stored_path, status, created_at, model
        ) VALUES (?, ?, ?, 'queued', ?, ?)
        """,
        (
            job["id"],
            job["original_name"],
            job["stored_path"],
            utc_now(),
            job["model"],
        ),
    )
    db.commit()


def get_job(job_id: str) -> sqlite3.Row | None:
    return get_db().execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()


def list_jobs(limit: int = 100) -> list[sqlite3.Row]:
    return get_db().execute(
        "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()


def job_counts() -> dict[str, int]:
    rows = get_db().execute(
        "SELECT status, COUNT(*) AS total FROM jobs GROUP BY status"
    ).fetchall()
    counts = {"queued": 0, "processing": 0, "completed": 0, "failed": 0}
    for row in rows:
        counts[row["status"]] = row["total"]
    return counts


def recover_interrupted_jobs(path: str | Path) -> None:
    conn = connect(path)
    try:
        conn.execute(
            """
            UPDATE jobs
               SET status = 'queued',
                   error = 'Recovered after application restart'
             WHERE status = 'processing'
            """
        )
        conn.commit()
    finally:
        conn.close()


def claim_next_job(path: str | Path) -> dict[str, Any] | None:
    conn = connect(path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """
            SELECT * FROM jobs
             WHERE status = 'queued'
             ORDER BY created_at ASC
             LIMIT 1
            """
        ).fetchone()
        if row is None:
            conn.commit()
            return None

        changed = conn.execute(
            """
            UPDATE jobs
               SET status = 'processing', started_at = ?, error = NULL
             WHERE id = ? AND status = 'queued'
            """,
            (utc_now(), row["id"]),
        ).rowcount
        conn.commit()
        if changed != 1:
            return None
        return dict(row)
    finally:
        conn.close()


def update_progress(
    path: str | Path,
    job_id: str,
    *,
    language: str | None,
    duration_seconds: float | None,
    progress_seconds: float,
    partial_transcript_path: str,
    partial_timestamped_path: str,
) -> None:
    conn = connect(path)
    try:
        conn.execute(
            """
            UPDATE jobs
               SET language = COALESCE(?, language),
                   duration_seconds = COALESCE(?, duration_seconds),
                   progress_seconds = ?,
                   partial_transcript_path = ?,
                   partial_timestamped_path = ?,
                   error = NULL
             WHERE id = ?
            """,
            (
                language,
                duration_seconds,
                progress_seconds,
                partial_transcript_path,
                partial_timestamped_path,
                job_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def complete_job(
    path: str | Path,
    job_id: str,
    *,
    language: str | None,
    duration_seconds: float | None,
    transcript_path: str,
    timestamped_path: str,
) -> None:
    conn = connect(path)
    try:
        conn.execute(
            """
            UPDATE jobs
               SET status = 'completed', completed_at = ?, language = ?,
                   duration_seconds = ?, transcript_path = ?, timestamped_path = ?,
                   progress_seconds = COALESCE(?, progress_seconds),
                   partial_transcript_path = NULL,
                   partial_timestamped_path = NULL,
                   error = NULL
             WHERE id = ?
            """,
            (
                utc_now(),
                language,
                duration_seconds,
                transcript_path,
                timestamped_path,
                duration_seconds,
                job_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def fail_job(path: str | Path, job_id: str, message: str) -> None:
    conn = connect(path)
    try:
        conn.execute(
            """
            UPDATE jobs
               SET status = 'failed', completed_at = ?, error = ?
             WHERE id = ?
            """,
            (utc_now(), message[:4000], job_id),
        )
        conn.commit()
    finally:
        conn.close()
