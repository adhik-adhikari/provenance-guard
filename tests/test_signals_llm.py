"""
Tests for the LLM signal in signals.py — using mocking to avoid real API calls.

The Groq API is mocked via unittest.mock.patch rather than called directly:
calling a live API in a test suite is slow, non-deterministic, requires a live
key, and costs money per call. Mocking replaces the Groq client with a
controlled fake at the boundary between this codebase and the external service,
so the parsing, clamping, and error-handling logic inside get_llm_score can
still be exercised in full.
"""

import json
import pytest
from unittest.mock import MagicMock, patch


def _make_mock_response(ai_likelihood: float, reason: str = "test") -> MagicMock:
    """Helper: build a fake Groq API response with the given score."""
    mock_response = MagicMock()
    mock_response.choices[0].message.content = json.dumps(
        {"ai_likelihood": ai_likelihood, "reason": reason}
    )
    return mock_response


@patch("signals._get_client")
def test_llm_score_returns_float_from_api(mock_get_client):
    """Happy path: API returns valid JSON, we parse and return the float."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _make_mock_response(0.85)
    mock_get_client.return_value = mock_client

    from signals import get_llm_score
    score = get_llm_score("Some text to analyze.")

    assert score == pytest.approx(0.85)
    mock_client.chat.completions.create.assert_called_once()


@patch("signals._get_client")
def test_llm_score_clamps_above_one(mock_get_client):
    """If the LLM somehow returns > 1.0, we clamp it to 1.0 rather than crashing."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _make_mock_response(1.5)
    mock_get_client.return_value = mock_client

    from signals import get_llm_score
    score = get_llm_score("text")
    assert score == pytest.approx(1.0)


@patch("signals._get_client")
def test_llm_score_clamps_below_zero(mock_get_client):
    """If the LLM returns a negative number, we clamp it to 0.0."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _make_mock_response(-0.3)
    mock_get_client.return_value = mock_client

    from signals import get_llm_score
    score = get_llm_score("text")
    assert score == pytest.approx(0.0)


@patch("signals._get_client")
def test_llm_score_raises_on_unparseable_response(mock_get_client):
    """If the API returns garbage (not JSON), we raise a clear ValueError."""
    mock_client = MagicMock()
    bad_response = MagicMock()
    bad_response.choices[0].message.content = "Sorry, I cannot do that."
    mock_client.chat.completions.create.return_value = bad_response
    mock_get_client.return_value = mock_client

    from signals import get_llm_score
    with pytest.raises(ValueError, match="parseable JSON"):
        get_llm_score("text")


@patch("signals._get_client")
def test_llm_score_uses_temperature_zero(mock_get_client):
    """
    The LLM must be called with temperature=0 for deterministic output.
    A non-zero temperature makes the same text produce different scores on each
    call — which would make the audit log unreproducible.
    """
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _make_mock_response(0.5)
    mock_get_client.return_value = mock_client

    from signals import get_llm_score
    get_llm_score("text")

    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert call_kwargs.get("temperature") == 0


@patch("signals._get_client")
def test_llm_score_result_is_in_range(mock_get_client):
    """Score must always be in [0, 1]."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _make_mock_response(0.42)
    mock_get_client.return_value = mock_client

    from signals import get_llm_score
    score = get_llm_score("Any text.")
    assert 0.0 <= score <= 1.0
