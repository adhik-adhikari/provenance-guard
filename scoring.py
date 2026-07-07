LLM_WEIGHT = 0.7
STYLOMETRIC_WEIGHT = 0.3

AI_THRESHOLD = 0.70
HUMAN_THRESHOLD = 0.30


def score_confidence(llm_score, stylometric_score):
    """Combines the two signal scores into a single verdict.

    Returns a dict with combined_score, confidence, and attribution — see
    planning.md section 4 for the reasoning behind the weights and thresholds.
    """
    combined_score = LLM_WEIGHT * llm_score + STYLOMETRIC_WEIGHT * stylometric_score
    confidence = abs(combined_score - 0.5) * 2

    if combined_score >= AI_THRESHOLD:
        attribution = "likely_ai"
    elif combined_score <= HUMAN_THRESHOLD:
        attribution = "likely_human"
    else:
        attribution = "uncertain"

    return {
        "combined_score": combined_score,
        "confidence": confidence,
        "attribution": attribution,
    }
