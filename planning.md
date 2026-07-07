# Provenance Guard — Planning

## 1. Architecture Narrative

A creator submits a piece of text to `POST /submit` along with a `creator_id`. The
request first passes through **rate limiting** (Flask-Limiter) so a single creator or
script can't flood the pipeline. If it passes, the text is sent to two independent
**detection signals**:

1. An **LLM-based signal** (Groq `llama-3.3-70b-versatile`) that reads the text
   holistically and returns a 0–1 score for "how much this reads like AI-generated
   text."
2. A **stylometric signal** (pure Python) that computes surface statistics —
   sentence length variance, vocabulary diversity (type-token ratio), and
   punctuation density — and converts them into its own 0–1 AI-likelihood score.

Both scores go to the **confidence scorer**, which combines them into a single
`combined_score` (a weighted average) and derives two outputs from it: an
`attribution` verdict (`likely_ai` / `uncertain` / `likely_human`) using fixed
thresholds, and a `confidence` value that measures how far the combined score sits
from the "coin flip" midpoint (0.5) — i.e., how sure the system is, independent of
which direction it leans.

The **label generator** maps the attribution verdict to one of three fixed pieces of
plain-language text. Every submission — regardless of verdict — is written to the
**audit log** (SQLite) with both individual signal scores, the combined score,
confidence, attribution, label, and a timestamp. The endpoint then returns all of
this as JSON.

If a creator disagrees with their verdict, they call `POST /appeal` with the
`content_id` from their submission response and a free-text `creator_reasoning`. This
updates that same log record's `status` to `under_review` and stores the reasoning
and appeal timestamp — so the appeal is always visible right next to the original
classification, not as a disconnected event.

## 2. Architecture Diagram

```
                              SUBMISSION FLOW
                              ---------------
 Client
   |  POST /submit  {text, creator_id}
   v
[Flask route] --(request count)--> [Flask-Limiter: 10/min, 100/day]
   |  (raw text)                         |
   |                                 429 if exceeded --> Client
   v
[Signal 1: Groq LLM classifier] --(llm_score 0-1)-->
   |                                                  \
   v                                                   \
[Signal 2: Stylometric heuristics] --(stylometric_score 0-1)--> [Confidence Scorer]
                                                                      |
                                          combined_score = 0.6*llm + 0.4*stylo
                                          confidence = |combined_score - 0.5| * 2
                                          attribution = threshold(combined_score)
                                                                      |
                                                                      v
                                                          [Label Generator]
                                                          (attribution -> label text)
                                                                      |
                                                                      v
                                                          [Audit Logger] --(writes row)--> SQLite
                                                                      |
                                                                      v
                                                          JSON response --> Client
                                                          {content_id, attribution,
                                                           confidence, label,
                                                           llm_score, stylometric_score}


                                APPEAL FLOW
                                -----------
 Client
   |  POST /appeal {content_id, creator_reasoning}
   v
[Flask route] --lookup content_id--> [SQLite record]
   |                                        |
   |                          update: status="under_review",
   |                          appeal_reasoning, appeal_timestamp
   v
[Audit Logger] --(updates same row)--> SQLite
   |
   v
JSON response {content_id, status: "under_review"} --> Client

GET /log --> reads all SQLite rows, ordered by timestamp desc --> JSON array
```

## 3. Detection Signals

| Signal | What it measures | Output | Why chosen | What it misses |
|---|---|---|---|---|
| **LLM classifier (Groq)** | Semantic and stylistic coherence, holistically — does the *overall voice* of the passage read as generated (predictable phrasing, hedging patterns, generic transitions) or as an individual human voice? | Float 0–1, where 1 = "reads as AI-generated" | Captures things heuristics can't: tone, cliché phrasing, generic "on one hand / on the other hand" structuring, and idea-level genericness. | Can be fooled by heavily-edited AI text or by a human writing in a plain/formal register that happens to resemble "generic" prose (e.g., a non-native speaker, or someone writing a five-paragraph essay). It's also a black box — it can't explain *which* words triggered its score, just a holistic guess. |
| **Stylometric heuristics** | Surface-level statistical regularity: (1) sentence length variance — AI text tends toward uniform sentence lengths; (2) type-token ratio (unique words / total words) — AI text tends to reuse a narrower vocabulary over a passage; (3) punctuation density (commas/semicolons per sentence) — AI text tends to over-use certain connective punctuation. | Float 0–1, where 1 = "structurally uniform, matches AI pattern" | Purely computable, no external dependency, deterministic, and fast. Independent of the LLM's judgment — it measures *structure*, not *meaning*, so it catches cases where an LLM might be swayed by topic or fooled by fluent phrasing. | Blind to meaning entirely — a human writing in a very controlled, repetitive style (technical documentation, legal writing, a poem using deliberate repetition) will score as "AI-like" even though a person wrote it. Also unreliable on very short text, where 2–3 metrics don't have enough data to be statistically meaningful. |

These two signals are genuinely independent: one is semantic (what is being said),
one is structural (how uniformly it's said). Because their blind spots don't overlap,
combining them is more informative than either alone — a passage that both flags is
much stronger evidence than one either flags alone.

## 4. Uncertainty Representation

- `llm_score` and `stylometric_score` are both floats in `[0, 1]`, where **1.0 means
  "strongly resembles AI-generated text"** and **0.0 means "strongly resembles
  human-written text."**
- **Combination:** `combined_score = 0.6 * llm_score + 0.4 * stylometric_score`. The
  LLM signal is weighted higher (0.6) because it evaluates meaning and voice, which
  is generally a stronger indicator than surface statistics alone; the stylometric
  signal (0.4) still meaningfully pulls the score when the two signals disagree,
  since it catches cases the LLM signal is blind to.
- **`confidence`** is derived from `combined_score`, not reported as the raw
  score itself: `confidence = abs(combined_score - 0.5) * 2`. This produces a value
  in `[0, 1]` that answers "how far from a coin flip is this?" — a `combined_score`
  of 0.51 or 0.49 (near the midpoint) produces `confidence ≈ 0.02` (essentially no
  confidence), while a `combined_score` of 0.95 produces `confidence = 0.90` (very
  confident). This is what makes 0.51 and 0.95 produce meaningfully different
  outputs, per the spec's requirement.
- **Thresholds** (applied to `combined_score`, not `confidence`):
  - `combined_score >= 0.70` → `attribution = "likely_ai"`
  - `combined_score <= 0.30` → `attribution = "likely_human"`
  - otherwise (`0.30 < combined_score < 0.70`) → `attribution = "uncertain"`
  - **Why 0.70 for AI but 0.30 for human (not a symmetric 0.5 split):** on a
    creative writing platform, wrongly accusing a human of using AI (a false
    positive) does more damage — to trust and to the creator — than wrongly
    clearing AI-generated text (a false negative). Requiring `combined_score` to
    clear 0.70 before calling something "likely AI" means it takes stronger,
    more one-sided evidence to level that accusation, while a much lower bar
    (0.30) is enough to call something "likely human." The wide uncertain band
    (0.30–0.70) is the direct expression of "when in doubt, don't accuse."

## 5. Transparency Label Design

Exact text returned in the `label` field, selected by `attribution`:

| Attribution | Label text |
|---|---|
| `likely_ai` | "Likely AI-Generated — Our analysis found strong signals that this content was created by AI rather than written by a person." |
| `uncertain` | "Uncertain Origin — We couldn't confidently tell whether this was written by a person or by AI. No verdict is being applied, and this content is not flagged." |
| `likely_human` | "Likely Human-Written — Our analysis did not find meaningful signs of AI generation in this content." |

No numeric scores, no words like "classifier," "logit," or "signal" appear in the
label text itself — those stay in the underlying JSON fields for developers. The
label is what an end reader sees; the raw signal scores are there for anyone who
wants to dig deeper (or for the audit log), but the label alone should be
understandable to someone with zero ML background.

## 6. Appeals Workflow

- **Who:** any creator whose content received an `attribution` of `likely_ai` (in
  practice, anyone can call the endpoint — we don't gate on attribution, since a
  creator might also want to contest an `uncertain` verdict).
- **What they provide:** `content_id` (from their original `/submit` response) and
  `creator_reasoning` (free text explaining why they believe the verdict is wrong).
- **What the system does:**
  1. Looks up the record by `content_id`. Returns `404` if not found.
  2. Sets that record's `status` to `"under_review"`.
  3. Stores `appeal_reasoning` and `appeal_timestamp` on the **same record** (not a
     separate table) — so `GET /log` shows the appeal directly alongside the
     original classification, scores, and label.
  4. Returns a confirmation JSON body with the new status.
- **What a reviewer would see:** calling `GET /log` and finding entries where
  `status == "under_review"` — each one already carries the full original
  classification context (both signal scores, combined score, confidence,
  attribution, label) plus the creator's stated reasoning, so a human reviewer
  doesn't have to cross-reference anything else.
- Automated re-classification is explicitly out of scope — a human is expected to
  make the final call.

## 7. Anticipated Edge Cases

1. **Very short submissions (under ~40 words).** The stylometric signal needs
   enough sentences to compute meaningful variance and type-token ratio; on a
   two-sentence excerpt these metrics are mostly noise. Expected failure mode: the
   stylometric score swings unpredictably, which can drag `combined_score` toward
   either extreme without real justification. Mitigation is honesty, not a fix: the
   system doesn't special-case this in v1, so short submissions are more likely to
   land in `uncertain` than they logically should — that's a known limitation, not
   a bug.
2. **Formal/technical human writing (academic abstracts, legal text, dense
   business writing).** This kind of writing is naturally uniform in sentence
   length and structure and reuses domain vocabulary heavily — exactly the pattern
   the stylometric signal is designed to flag as "AI-like." A human expert writing
   in a constrained genre can trigger a false-positive-leaning stylometric score.
   This is why the LLM signal is weighted higher (0.6) and why the AI threshold is
   set high (0.70) — a stylometric flag alone usually isn't enough to cross it.
3. **Heavily-edited AI output.** A human who takes an AI draft and substantially
   rewrites it will likely produce genuinely mixed signals — some AI-like
   structural remnants, but human-level semantic voice. This is arguably the
   *correct* behavior for our system (it should land in `uncertain` rather than
   confidently guessing either way), but it means the system cannot reliably tell
   "genuinely uncertain original text" apart from "collaboratively written text" —
   both produce the same label.

## AI Tool Plan

- **M3 (submission endpoint + first signal):** Provide the AI tool with the
  "Detection Signals" section (§3, LLM row only) and the architecture diagram (§2,
  submission flow). Ask it to generate: (1) a Flask app skeleton with a
  `POST /submit` route stub returning a hardcoded JSON shape, and (2) a standalone
  `get_llm_score(text) -> float` function that calls Groq with a prompt asking for
  a 0–1 AI-likelihood score. Verify by calling `get_llm_score` directly on 2–3
  sample texts (one obviously AI, one obviously human) before wiring it into the
  route, and by checking the route with `curl` before adding real logic.

- **M4 (second signal + confidence scoring):** Provide the "Detection Signals"
  section (§3, stylometric row), the "Uncertainty Representation" section (§4),
  and the diagram. Ask for: (1) a `get_stylometric_score(text) -> float` function
  implementing the three named metrics, and (2) a `score_confidence(llm_score,
  stylometric_score) -> dict` function implementing the exact weighting and
  threshold formulas from §4. Verify by checking the generated thresholds and
  weights against §4 line-by-line (AI tools sometimes "round" 0.6/0.4 to 0.5/0.5 or
  use symmetric thresholds instead of the deliberate 0.70/0.30 asymmetry — this
  must be checked, not assumed), then run the four test inputs from Milestone 4 of
  the spec and confirm the scores move in the expected direction.

- **M5 (production layer):** Provide the "Transparency Label Design" (§5) and
  "Appeals Workflow" (§6) sections, plus the diagram (appeal flow). Ask for: (1) a
  `get_label(attribution) -> str` function returning the exact three strings from
  §5 (verbatim, not paraphrased), and (2) the `POST /appeal` route implementing the
  four steps in §6. Verify by calling `get_label` for all three attribution values
  and diffing the output against §5 character-for-character, and by submitting
  then appealing a piece of content and confirming via `GET /log` that `status`
  flips to `under_review` and both the original scores and the appeal reasoning
  appear on the same entry.

## Stretch Feature: Analytics Dashboard

Added after the required milestones, per the "update planning.md before starting
any stretch feature" instruction.

- **What it is:** a `GET /analytics` endpoint that aggregates over every row
  already in the SQLite audit log — no new signals, no new storage, purely a
  read-side view over existing data.
- **Metrics (3, as required):**
  1. **Detection pattern** — counts and ratios of `likely_ai` / `uncertain` /
     `likely_human` across all submissions.
  2. **Appeal rate** — `appealed_count / total_submissions`.
  3. **Signal agreement rate** (chosen metric) — the fraction of submissions
     where the LLM signal and the stylometric signal land on the same side of
     0.5 (both lean AI or both lean human). This is a diagnostic metric for the
     pipeline itself: a low agreement rate would mean the two signals are
     frequently contradicting each other, which is useful context for
     interpreting why some verdicts land in `uncertain`.
- **Why these three:** the first two are the ones the rubric names directly;
  the third was chosen because it's specific to *this* system's two-signal
  design rather than a generic metric — it tells a reviewer something about
  signal quality, not just outcome counts.
