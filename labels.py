LABELS = {
    "likely_ai": (
        "Likely AI-Generated — Our analysis found strong indications that this "
        "content was created by AI rather than written by a person."
    ),
    "uncertain": (
        "Uncertain Origin — We couldn't confidently tell whether this was "
        "written by a person or by AI. No verdict is being applied, and this "
        "content is not flagged."
    ),
    "likely_human": (
        "Likely Human-Written — Our analysis did not find meaningful signs "
        "of AI generation in this content."
    ),
}


def get_label(attribution):
    return LABELS[attribution]
