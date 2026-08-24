"""
Tests for the stylometric signal in signals.py.

The stylometric signal is pure Python with no API call, so it can be tested
exhaustively with synthetic inputs where the expected score direction is known.
The LLM signal is tested separately using mocking.

Key behaviors verified:
- Too-short text returns a neutral 0.5 (not a misleading score)
- Uniform sentence lengths score higher than varied lengths
- Repeated words (low vocabulary diversity) score higher
- Score always stays within [0, 1]
"""

import pytest
from signals import (
    get_stylometric_score,
    _sentence_length_variance_score,
    _type_token_ratio_score,
    _punctuation_density_score,
    _split_sentences,
)


# --- Edge cases: too-short text ---

def test_empty_text_does_not_crash():
    """Empty string can't be meaningfully scored — should not crash."""
    score = get_stylometric_score("")
    assert 0.0 <= score <= 1.0


def test_single_sentence_variance_is_neutral():
    """With only one sentence, variance is undefined — returns 0.5 (neutral)."""
    score = _sentence_length_variance_score(["This is a single sentence."])
    assert score == 0.5


def test_very_short_text_ttr_is_neutral():
    """With fewer than 5 words, TTR can't be meaningful — returns 0.5."""
    score = _type_token_ratio_score("hi there")
    assert score == 0.5


# --- Sentence length variance: uniform = AI-like (high score) ---

def test_uniform_sentences_score_higher_than_varied():
    """AI text tends to have similar sentence lengths; human text varies more."""
    uniform = [
        "The cat sat on the mat.",
        "The dog ran to the park.",
        "The bird flew over the tree.",
        "The fish swam in the lake.",
    ]
    varied = [
        "Hi.",
        "I've been thinking about this for a while and I'm genuinely not sure what to make of it.",
        "OK.",
        "The situation is complicated and deserves a longer explanation than I can give here.",
    ]
    assert _sentence_length_variance_score(uniform) > _sentence_length_variance_score(varied)


# --- Type-token ratio: repetition = AI-like (high score) ---

def test_repetitive_text_scores_higher_than_diverse():
    """Low vocabulary diversity (lots of repeated words) → higher AI-likelihood."""
    repetitive = "the the the the cat cat cat sat sat mat mat mat mat mat"
    diverse = "Extraordinary circumstances demand unprecedented creative solutions from passionate individuals"
    assert _type_token_ratio_score(repetitive) > _type_token_ratio_score(diverse)


# --- Output range invariant ---

SAMPLE_TEXTS = [
    "This is a simple sentence.",
    "AI systems often produce uniform, hedging, structured text with predictable phrasing.",
    "yo what's up lol I've been thinking and idk maybe we should just go.",
    "a " * 50,
    ". ".join([f"Sentence number {i} has exactly six words" for i in range(10)]),
]

@pytest.mark.parametrize("text", SAMPLE_TEXTS)
def test_stylometric_score_always_in_range(text):
    """The stylometric score must always be in [0, 1] regardless of input."""
    score = get_stylometric_score(text)
    assert 0.0 <= score <= 1.0, f"Score {score} out of [0,1] for: {text[:40]!r}"


# --- Punctuation density ---

def test_heavy_punctuation_scores_higher():
    """Lots of commas, semicolons, colons per sentence → higher AI-likelihood."""
    heavy_text = "First, however, we must consider, on balance, the following: items A, B, and C."
    light_text = "I went to the store and bought milk."
    heavy_sentences = [heavy_text]
    light_sentences = [light_text]
    assert _punctuation_density_score(heavy_text, heavy_sentences) > \
           _punctuation_density_score(light_text, light_sentences)
