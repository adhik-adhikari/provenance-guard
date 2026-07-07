import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "provenance_guard.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS submissions (
    content_id TEXT PRIMARY KEY,
    creator_id TEXT,
    text TEXT,
    timestamp TEXT,
    llm_score REAL,
    stylometric_score REAL,
    combined_score REAL,
    confidence REAL,
    attribution TEXT,
    label TEXT,
    status TEXT,
    appeal_reasoning TEXT,
    appeal_timestamp TEXT
)
"""


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    conn.execute(SCHEMA)
    conn.commit()
    conn.close()


def insert_submission(record):
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO submissions (
            content_id, creator_id, text, timestamp,
            llm_score, stylometric_score, combined_score, confidence,
            attribution, label, status, appeal_reasoning, appeal_timestamp
        ) VALUES (
            :content_id, :creator_id, :text, :timestamp,
            :llm_score, :stylometric_score, :combined_score, :confidence,
            :attribution, :label, :status, :appeal_reasoning, :appeal_timestamp
        )
        """,
        record,
    )
    conn.commit()
    conn.close()


def get_submission(content_id):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM submissions WHERE content_id = ?", (content_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def update_appeal(content_id, creator_reasoning, timestamp):
    conn = get_connection()
    conn.execute(
        """
        UPDATE submissions
        SET status = 'under_review',
            appeal_reasoning = ?,
            appeal_timestamp = ?
        WHERE content_id = ?
        """,
        (creator_reasoning, timestamp, content_id),
    )
    conn.commit()
    conn.close()


def get_log(limit=50):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM submissions ORDER BY timestamp DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]
