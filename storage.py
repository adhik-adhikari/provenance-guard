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


def get_analytics():
    conn = get_connection()
    rows = [dict(row) for row in conn.execute("SELECT * FROM submissions").fetchall()]
    conn.close()

    total = len(rows)
    if total == 0:
        return {
            "total_submissions": 0,
            "detection_pattern": {"likely_ai": 0, "uncertain": 0, "likely_human": 0},
            "appeal_rate": 0.0,
            "signal_agreement_rate": 0.0,
        }

    counts = {"likely_ai": 0, "uncertain": 0, "likely_human": 0}
    appealed = 0
    agreeing = 0
    for row in rows:
        counts[row["attribution"]] += 1
        if row["status"] == "under_review":
            appealed += 1
        if (row["llm_score"] >= 0.5) == (row["stylometric_score"] >= 0.5):
            agreeing += 1

    return {
        "total_submissions": total,
        "detection_pattern": {
            "counts": counts,
            "ratios": {k: v / total for k, v in counts.items()},
        },
        "appeal_rate": appealed / total,
        "signal_agreement_rate": agreeing / total,
    }


def seed_demo_data():
    """Insert example submissions if the database is empty.

    Render's free tier uses ephemeral disk, so the database resets on each
    redeploy. Seeding ensures the analytics panel and log table always show
    meaningful data when someone visits the live demo for the first time.
    The seed runs only once — if any rows already exist, it does nothing.
    """
    conn = get_connection()
    count = conn.execute("SELECT COUNT(*) FROM submissions").fetchone()[0]
    if count > 0:
        conn.close()
        return

    seed_rows = [
        {
            "content_id": "demo-001",
            "creator_id": "demo-user",
            "text": "Artificial intelligence is transforming industries at an unprecedented rate. "
                    "The implications for the global workforce are significant and multifaceted.",
            "timestamp": "2026-08-20T10:00:00Z",
            "llm_score": 0.87,
            "stylometric_score": 0.74,
            "combined_score": 0.831,
            "confidence": 0.83,
            "attribution": "likely_ai",
            "label": "Likely AI-Generated — Our analysis found strong indications that this content was produced by an AI language model.",
            "status": "classified",
            "appeal_reasoning": None,
            "appeal_timestamp": None,
        },
        {
            "content_id": "demo-002",
            "creator_id": "demo-user",
            "text": "honestly i don't even know where to start lol. like yeah i finished the project "
                    "but it took way longer than i expected and i kept hitting weird bugs",
            "timestamp": "2026-08-20T11:30:00Z",
            "llm_score": 0.11,
            "stylometric_score": 0.22,
            "combined_score": 0.143,
            "confidence": 0.86,
            "attribution": "likely_human",
            "label": "Likely Human-Written — Our analysis did not find meaningful signs of AI generation in this content.",
            "status": "under_review",
            "appeal_reasoning": "I wrote this myself in a Discord message.",
            "appeal_timestamp": "2026-08-20T12:00:00Z",
        },
        {
            "content_id": "demo-003",
            "creator_id": "reviewer-1",
            "text": "The report outlines several key findings from the quarterly review. "
                    "Each department has been asked to submit updated projections by Friday.",
            "timestamp": "2026-08-21T09:15:00Z",
            "llm_score": 0.61,
            "stylometric_score": 0.38,
            "combined_score": 0.541,
            "confidence": 0.08,
            "attribution": "uncertain",
            "label": "Uncertain Origin — The two signals disagreed. This content shows mixed characteristics.",
            "status": "classified",
            "appeal_reasoning": None,
            "appeal_timestamp": None,
        },
        {
            "content_id": "demo-004",
            "creator_id": "demo-user",
            "text": "In conclusion, the synthesis of heterogeneous data sources presents both "
                    "opportunities and challenges for modern machine learning pipelines.",
            "timestamp": "2026-08-22T14:00:00Z",
            "llm_score": 0.91,
            "stylometric_score": 0.68,
            "combined_score": 0.841,
            "confidence": 0.84,
            "attribution": "likely_ai",
            "label": "Likely AI-Generated — Our analysis found strong indications that this content was produced by an AI language model.",
            "status": "classified",
            "appeal_reasoning": None,
            "appeal_timestamp": None,
        },
    ]

    for row in seed_rows:
        conn.execute(
            """
            INSERT OR IGNORE INTO submissions (
                content_id, creator_id, text, timestamp,
                llm_score, stylometric_score, combined_score, confidence,
                attribution, label, status, appeal_reasoning, appeal_timestamp
            ) VALUES (
                :content_id, :creator_id, :text, :timestamp,
                :llm_score, :stylometric_score, :combined_score, :confidence,
                :attribution, :label, :status, :appeal_reasoning, :appeal_timestamp
            )
            """,
            row,
        )
    conn.commit()
    conn.close()
