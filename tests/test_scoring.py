"""
Tests for scoring.py — the confidence scorer and verdict thresholder.

Boundary conditions are tested explicitly:
- Exactly at the thresholds (0.70 and 0.30) to confirm >= vs > is correct.
- At the exact midpoint (0.50) to confirm "uncertain" and a confidence of 0.
- At the extremes (0.0 and 1.0) to confirm confidence reaches 1.0.
- A disagreeing-signal case to confirm the weighted formula is wired correctly.
"""

import pytest
from scoring import score_confidence


# --- Attribution thresholds ---

def test_score_at_ai_threshold_is_likely_ai():
    """combined_score == 0.70 should just cross into likely_ai."""
    # To hit exactly 0.70: 0.7*llm + 0.3*stylo = 0.70
    # Simplest: llm=1.0, stylo=0.0 → 0.70*1.0 + 0.30*0.0 = 0.70
    result = score_confidence(llm_score=1.0, stylometric_score=0.0)
    assert result["attribution"] == "likely_ai"


def test_score_just_below_ai_threshold_is_uncertain():
    """combined_score just under 0.70 should be uncertain, not likely_ai."""
    # llm=0.9, stylo=0.0 → 0.63 → uncertain
    result = score_confidence(llm_score=0.9, stylometric_score=0.0)
    assert result["attribution"] == "uncertain"


def test_score_at_human_threshold_is_likely_human():
    """combined_score == 0.30 should just cross into likely_human."""
    # 0.7*0.0 + 0.3*1.0 = 0.30
    result = score_confidence(llm_score=0.0, stylometric_score=1.0)
    assert result["attribution"] == "likely_human"


def test_score_just_above_human_threshold_is_uncertain():
    """combined_score just above 0.30 should be uncertain."""
    # llm=0.4, stylo=0.4 → 0.28+0.12 = 0.40 → uncertain
    result = score_confidence(llm_score=0.4, stylometric_score=0.4)
    assert result["attribution"] == "uncertain"


def test_score_at_midpoint_is_uncertain_with_zero_confidence():
    """A combined_score of exactly 0.5 is maximally uncertain."""
    # 0.7*0.5 + 0.3*0.5 = 0.5
    result = score_confidence(llm_score=0.5, stylometric_score=0.5)
    assert result["attribution"] == "uncertain"
    assert result["confidence"] == pytest.approx(0.0, abs=1e-9)


# --- Confidence magnitude ---

def test_confidence_is_zero_at_midpoint():
    result = score_confidence(0.5, 0.5)
    assert result["confidence"] == pytest.approx(0.0, abs=1e-9)


def test_confidence_is_one_at_full_ai():
    """All signals at 1.0 → combined_score=1.0 → confidence=1.0."""
    result = score_confidence(1.0, 1.0)
    assert result["confidence"] == pytest.approx(1.0)


def test_confidence_is_one_at_full_human():
    """All signals at 0.0 → combined_score=0.0 → confidence=1.0."""
    result = score_confidence(0.0, 0.0)
    assert result["confidence"] == pytest.approx(1.0)


# --- Combined score formula ---

def test_combined_score_uses_correct_weights():
    """70/30 weighting: verify the formula isn't accidentally 60/40 or 50/50."""
    result = score_confidence(llm_score=0.8, stylometric_score=0.2)
    expected = 0.7 * 0.8 + 0.3 * 0.2  # = 0.56 + 0.06 = 0.62
    assert result["combined_score"] == pytest.approx(expected)


def test_disagreeing_signals_land_in_uncertain():
    """When LLM says AI and stylometric says human, result should be uncertain."""
    # llm=0.8 (AI), stylo=0.1 (human): 0.7*0.8 + 0.3*0.1 = 0.56 + 0.03 = 0.59 → uncertain
    result = score_confidence(llm_score=0.8, stylometric_score=0.1)
    assert result["attribution"] == "uncertain"


def test_result_dict_has_all_expected_keys():
    result = score_confidence(0.5, 0.5)
    assert set(result.keys()) == {"combined_score", "confidence", "attribution"}
