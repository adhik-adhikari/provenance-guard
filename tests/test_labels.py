"""
Tests for labels.py — the transparency label generator.

Verifies that user-facing label strings exist for every valid attribution
and that no internal jargon ("signal", "logit", "classifier", etc.) appears
in what a reader sees. The no-jargon requirement was a deliberate design
decision — "signal" is an internal term, not for end users.
"""

import pytest
from labels import get_label, LABELS


# --- All three attributions return a non-empty string ---

def test_get_label_likely_ai():
    label = get_label("likely_ai")
    assert isinstance(label, str) and len(label) > 0


def test_get_label_uncertain():
    label = get_label("uncertain")
    assert isinstance(label, str) and len(label) > 0


def test_get_label_likely_human():
    label = get_label("likely_human")
    assert isinstance(label, str) and len(label) > 0


# --- Labels contain the right sentiment keywords ---

def test_likely_ai_label_mentions_ai():
    label = get_label("likely_ai")
    assert "AI" in label or "ai" in label.lower()


def test_likely_human_label_mentions_human():
    label = get_label("likely_human")
    assert "Human" in label or "human" in label.lower()


def test_uncertain_label_says_content_is_not_flagged():
    """The uncertain label must explicitly say content is NOT flagged — UX guarantee."""
    label = get_label("uncertain")
    assert "not flagged" in label


# --- No jargon in user-facing text ---

JARGON_TERMS = ["signal", "logit", "classifier", "heuristic", "score", "threshold"]

@pytest.mark.parametrize("attribution", ["likely_ai", "uncertain", "likely_human"])
def test_no_jargon_in_label(attribution):
    """User-facing labels must not contain internal technical jargon."""
    label = get_label(attribution).lower()
    for term in JARGON_TERMS:
        assert term not in label, f"Jargon term '{term}' found in {attribution!r} label"


# --- Unknown attribution raises KeyError (fail-loud contract) ---

def test_unknown_attribution_raises():
    with pytest.raises(KeyError):
        get_label("unknown_value")


# --- LABELS dict has exactly the three expected keys ---

def test_labels_dict_completeness():
    assert set(LABELS.keys()) == {"likely_ai", "uncertain", "likely_human"}
