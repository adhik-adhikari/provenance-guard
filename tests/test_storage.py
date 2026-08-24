"""
Tests for storage.py — the SQLite persistence layer.

Each test gets a fresh, isolated database through the `tmp_db` fixture in
conftest.py, so tests never interfere with each other, never pollute the real
provenance_guard.db, and are deterministic regardless of run order.
"""

import pytest
import storage
from timestamps import now_iso


def make_record(content_id="test-id-001", creator_id="alice", attribution="likely_human",
                llm_score=0.1, stylometric_score=0.2):
    """Helper to build a minimal valid submission record."""
    return {
        "content_id": content_id,
        "creator_id": creator_id,
        "text": "Sample text for testing.",
        "timestamp": now_iso(),
        "llm_score": llm_score,
        "stylometric_score": stylometric_score,
        "combined_score": 0.7 * llm_score + 0.3 * stylometric_score,
        "confidence": 0.74,
        "attribution": attribution,
        "label": "Likely Human-Written — test label.",
        "status": "classified",
        "appeal_reasoning": None,
        "appeal_timestamp": None,
    }


# --- Basic insert + retrieve ---

def test_insert_and_retrieve_submission(tmp_db):
    record = make_record()
    storage.insert_submission(record)
    retrieved = storage.get_submission("test-id-001")
    assert retrieved is not None
    assert retrieved["creator_id"] == "alice"
    assert retrieved["attribution"] == "likely_human"


def test_get_submission_returns_none_for_missing_id(tmp_db):
    result = storage.get_submission("does-not-exist")
    assert result is None


def test_inserted_numeric_fields_round_trip_correctly(tmp_db):
    """All float fields written must come back with same values."""
    record = make_record()
    storage.insert_submission(record)
    retrieved = storage.get_submission("test-id-001")
    for key in ["llm_score", "stylometric_score", "combined_score", "confidence"]:
        assert retrieved[key] == pytest.approx(record[key])


# --- get_log ---

def test_get_log_returns_most_recent_first(tmp_db):
    """Log entries should be ordered newest-first (for the reviewer UI)."""
    storage.insert_submission(make_record("id-001", "alice"))
    storage.insert_submission(make_record("id-002", "bob"))
    log = storage.get_log()
    assert log[0]["content_id"] == "id-002"
    assert log[1]["content_id"] == "id-001"


def test_get_log_empty_returns_empty_list(tmp_db):
    log = storage.get_log()
    assert log == []


# --- update_appeal ---

def test_appeal_updates_status_to_under_review(tmp_db):
    storage.insert_submission(make_record())
    storage.update_appeal("test-id-001", "I wrote this myself.", now_iso())
    retrieved = storage.get_submission("test-id-001")
    assert retrieved["status"] == "under_review"
    assert retrieved["appeal_reasoning"] == "I wrote this myself."


def test_appeal_preserves_original_classification(tmp_db):
    """Appealing must not change the classification — only status and reasoning."""
    storage.insert_submission(make_record(attribution="likely_ai"))
    storage.update_appeal("test-id-001", "I wrote it.", now_iso())
    retrieved = storage.get_submission("test-id-001")
    assert retrieved["attribution"] == "likely_ai"


# --- get_analytics ---

def test_analytics_on_empty_db(tmp_db):
    result = storage.get_analytics()
    assert result["total_submissions"] == 0
    assert result["appeal_rate"] == 0.0


def test_analytics_counts_attributions_correctly(tmp_db):
    storage.insert_submission(make_record("id-1", attribution="likely_ai"))
    storage.insert_submission(make_record("id-2", attribution="likely_human"))
    storage.insert_submission(make_record("id-3", attribution="uncertain"))

    result = storage.get_analytics()
    assert result["total_submissions"] == 3
    counts = result["detection_pattern"]["counts"]
    assert counts["likely_ai"] == 1
    assert counts["likely_human"] == 1
    assert counts["uncertain"] == 1


def test_analytics_appeal_rate(tmp_db):
    storage.insert_submission(make_record("id-1"))
    storage.insert_submission(make_record("id-2"))
    storage.update_appeal("id-1", "reason", now_iso())  # 1 of 2 under review
    result = storage.get_analytics()
    assert result["appeal_rate"] == pytest.approx(0.5)


def test_analytics_signal_agreement_rate(tmp_db):
    """
    Signal agreement: both signals on the same side of 0.5.
    llm=0.8, stylo=0.7 → both AI-side → agree.
    llm=0.8, stylo=0.2 → disagree.
    Agreement rate = 1/2 = 0.5.
    """
    r1 = make_record("id-1", llm_score=0.8, stylometric_score=0.7)
    storage.insert_submission(r1)
    r2 = make_record("id-2", llm_score=0.8, stylometric_score=0.2)
    storage.insert_submission(r2)

    result = storage.get_analytics()
    assert result["signal_agreement_rate"] == pytest.approx(0.5)
