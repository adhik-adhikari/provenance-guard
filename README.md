# Provenance Guard

A backend system that any creative sharing platform could plug into to classify
submitted content, score confidence in that classification, surface a transparency
label to users, and handle appeals from creators who believe they've been
misclassified.

See [`planning.md`](planning.md) for the full design spec (signals, thresholds,
architecture diagram, AI tool plan) written before implementation.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file in the repo root (not committed):

```
GROQ_API_KEY=your_key_here
```

Run the server (uses port `5050` — macOS's built-in AirPlay Receiver already
occupies port 5000):

```bash
python app.py
```

## Architecture Overview

A submission's path from input to label:

1. `POST /submit` receives `{text, creator_id}`. Flask-Limiter checks the rate
   limit first.
2. **Signal 1 — Groq LLM classifier** reads the text holistically and returns a
   0–1 "AI-likelihood" score based on tone, phrasing, and structure.
3. **Signal 2 — stylometric heuristics** compute sentence-length uniformity,
   vocabulary diversity, and punctuation density in pure Python, and combine them
   into a second 0–1 AI-likelihood score.
4. The **confidence scorer** combines both into a `combined_score`, derives a
   `confidence` value (distance from the 0.5 midpoint), and applies thresholds to
   produce an `attribution` (`likely_ai` / `uncertain` / `likely_human`).
5. The **label generator** maps `attribution` to fixed, plain-language text.
6. The **audit logger** writes every field (both signal scores, combined score,
   confidence, attribution, label, timestamp) to a SQLite row, and the endpoint
   returns the result as JSON.

Appeals (`POST /appeal`) look up that same SQLite row by `content_id`, set its
`status` to `under_review`, and attach the creator's reasoning — so the appeal is
never a separate, disconnected record from the original classification.

Full diagram: [`planning.md` § Architecture](planning.md#2-architecture-diagram).

## Detection Signals

| Signal | What it measures | What it misses |
|---|---|---|
| **LLM classifier (Groq `llama-3.3-70b-versatile`)** | Holistic semantic/stylistic coherence — generic phrasing, hedging ("it is important to note"), predictable structure, lack of a distinct personal voice. | Can be fooled by heavily-edited AI text, or by a human writing in a plain/formal register that happens to look "generic." It's a black box — no explanation of *which* words drove the score. |
| **Stylometric heuristics (pure Python)** | Sentence-length variance, type-token ratio (vocabulary diversity), and punctuation density — surface statistics that tend to be more uniform in AI-generated text. | Blind to meaning entirely. A human writing in a deliberately controlled, repetitive style (legal writing, technical docs, a poem using repetition) scores "AI-like" even though a person wrote it. Also unreliable on short passages, where there isn't enough data for the statistics to mean anything. |

They're combined as `combined_score = 0.7 * llm_score + 0.3 * stylometric_score` —
see [Spec Reflection](#spec-reflection) for why the weighting changed from the
original 60/40 plan.

## Confidence Scoring

`confidence = abs(combined_score - 0.5) * 2` — this measures how far the combined
score sits from a coin flip (0.5), independent of which direction (AI or human) it
leans. A `combined_score` near 0.5 produces a `confidence` near 0; a
`combined_score` near 0 or 1 produces a `confidence` near 1.

Thresholds (on `combined_score`):

- `>= 0.70` → `likely_ai`
- `<= 0.30` → `likely_human`
- otherwise → `uncertain`

The thresholds are **intentionally asymmetric** around 0.5. On a creative writing
platform, wrongly accusing a human of using AI (a false positive) does more
reputational damage than wrongly clearing AI-generated text. Requiring a
`combined_score` of 0.70+ before saying "likely AI" — versus only 0.30 or below for
"likely human" — means it takes stronger, more one-sided evidence to level the
accusation.

**Validation:** I tested the pipeline with the 4 example inputs from the project
spec (clearly-AI boilerplate, clearly-human casual writing, formal human writing,
and lightly-edited AI text) plus an even more boilerplate-heavy AI paragraph, and
checked that the direction and spread of scores matched intuition before moving on
(see [Spec Reflection](#spec-reflection) for a case where it initially didn't).

**Two example submissions with noticeably different confidence:**

High-confidence case (`creator_id: "alice"`, casual human writing):
```json
{
  "attribution": "likely_human",
  "confidence": 0.7902159399064524,
  "llm_score": 0.1,
  "stylometric_score": 0.11630676682257923,
  "label": "Likely Human-Written — Our analysis did not find meaningful signs of AI generation in this content."
}
```

Lower-confidence case (`creator_id: "bob"`, AI-boilerplate paragraph):
```json
{
  "attribution": "likely_ai",
  "confidence": 0.48369066558344875,
  "llm_score": 0.9,
  "stylometric_score": 0.37281777597241444,
  "label": "Likely AI-Generated — Our analysis found strong signals that this content was created by AI rather than written by a person."
}
```

Both land on the correct side of the threshold, but the second is much closer to
the uncertain band — the stylometric signal (0.37) disagreed more with the LLM
signal (0.9) than in the first case, which pulls confidence down even though the
verdict itself is still clearly `likely_ai`.

## Transparency Label

Exact text returned in the `label` field:

| Attribution | Label text |
|---|---|
| `likely_ai` | "Likely AI-Generated — Our analysis found strong signals that this content was created by AI rather than written by a person." |
| `uncertain` | "Uncertain Origin — We couldn't confidently tell whether this was written by a person or by AI. No verdict is being applied, and this content is not flagged." |
| `likely_human` | "Likely Human-Written — Our analysis did not find meaningful signs of AI generation in this content." |

No jargon ("classifier," "logit," "signal score") appears in the label text itself
— that language stays in the underlying JSON fields for developers/reviewers, not
in what a reader sees.

## Appeals Workflow

`POST /appeal` with `{content_id, creator_reasoning}`:

```bash
curl -s -X POST http://localhost:5050/appeal \
  -H "Content-Type: application/json" \
  -d '{"content_id": "0611ba38-4c66-421c-85ce-5a9f9ba28576", "creator_reasoning": "I wrote this myself for a business communications class assignment; the formal tone was intentional, not AI-generated."}'
```

Response:
```json
{
  "content_id": "0611ba38-4c66-421c-85ce-5a9f9ba28576",
  "status": "under_review",
  "message": "Appeal received and logged for human review."
}
```

This updates the *same* audit log row (not a separate table) — `status` flips to
`under_review` and `appeal_reasoning` / `appeal_timestamp` are filled in, so a
reviewer sees the appeal directly next to the original classification (see
[Audit Log](#audit-log) below). Automated re-classification is out of scope; a
human is expected to review and act.

## Rate Limiting

`POST /submit` is limited to **10 requests per minute and 100 per day** per client
(via Flask-Limiter, keyed on IP address).

**Reasoning:** a real creator submitting their own writing for review would
realistically submit a handful of pieces in one sitting — a few poems, a chapter
draft, maybe revising and resubmitting a couple of times. 10/minute comfortably
covers that with headroom, while still blocking a script attempting to flood the
pipeline with rapid-fire requests (each of which costs an LLM API call). The
100/day ceiling exists for the same reason at a longer time scale — even a very
prolific writer submitting many short pieces across a work session stays well
under 100, but a scraper or abuse script trying to brute-force many submissions in
a day gets cut off.

**Evidence** (12 rapid requests against a freshly-started server; limit is 10/min):

```
200
200
200
200
200
200
200
200
200
200
429
429
```

## Audit Log

`GET /log` returns structured JSON entries, most recent first. Every entry
includes the timestamp, both individual signal scores, the combined score,
confidence, attribution, and label; appealed entries also carry the appeal
reasoning and timestamp right on the same record. Sample (3 entries, one
appealed):

```json
{
  "entries": [
    {
      "content_id": "63d602a7-54e9-4ff2-8b43-3785ae73d3df",
      "creator_id": "carla",
      "timestamp": "2026-07-07T19:57:04.322535+00:00",
      "llm_score": 0.7,
      "stylometric_score": 0.16812046702197234,
      "combined_score": 0.5404361401065916,
      "confidence": 0.08087228021318316,
      "attribution": "uncertain",
      "label": "Uncertain Origin — We couldn't confidently tell whether this was written by a person or by AI. No verdict is being applied, and this content is not flagged.",
      "status": "classified",
      "appeal_reasoning": null,
      "appeal_timestamp": null
    },
    {
      "content_id": "0611ba38-4c66-421c-85ce-5a9f9ba28576",
      "creator_id": "bob",
      "timestamp": "2026-07-07T19:57:03.941108+00:00",
      "llm_score": 0.9,
      "stylometric_score": 0.37281777597241444,
      "combined_score": 0.7418453327917244,
      "confidence": 0.48369066558344875,
      "attribution": "likely_ai",
      "label": "Likely AI-Generated — Our analysis found strong signals that this content was created by AI rather than written by a person.",
      "status": "under_review",
      "appeal_reasoning": "I wrote this myself for a business communications class assignment; the formal tone was intentional, not AI-generated.",
      "appeal_timestamp": "2026-07-07T19:57:09.358499+00:00"
    },
    {
      "content_id": "be47af2c-291a-48a5-ba95-6f9c6afd1570",
      "creator_id": "alice",
      "timestamp": "2026-07-07T19:57:03.562731+00:00",
      "llm_score": 0.1,
      "stylometric_score": 0.11630676682257923,
      "combined_score": 0.10489203004677376,
      "confidence": 0.7902159399064524,
      "attribution": "likely_human",
      "label": "Likely Human-Written — Our analysis did not find meaningful signs of AI generation in this content.",
      "status": "classified",
      "appeal_reasoning": null,
      "appeal_timestamp": null
    }
  ]
}
```

## Known Limitations

**Lightly-edited AI-generated text is likely to be misclassified as
human-written.** When I tested a passage that read like AI output a person had
lightly rewritten for a more natural voice ("I've been thinking a lot about remote
work lately. There are genuine tradeoffs..."), the LLM signal scored it `0.20`
(reads as human) and the stylometric signal scored it `0.27`, combining to
`combined_score = 0.22` — `likely_human`. This is a direct consequence of both
signals: the LLM signal evaluates holistic voice and tone, which light editing is
specifically good at normalizing, and the stylometric signal's structural
statistics (sentence variance, vocabulary diversity) are also smoothed out by the
same editing pass. Neither signal is measuring "was any part of this AI-assisted,"
only "does the final text read as AI-like" — so content that started as AI output
and was meaningfully rewritten will tend to evade detection by design, not by bug.

## Stretch Feature: Analytics Dashboard

`GET /analytics` aggregates over every submission in the audit log and returns
three metrics — no new signals or storage, purely a read-side view:

1. **Detection pattern** — counts and ratios of `likely_ai` / `uncertain` /
   `likely_human` verdicts.
2. **Appeal rate** — fraction of submissions currently `under_review`.
3. **Signal agreement rate** (chosen metric) — how often the LLM and
   stylometric signals land on the same side of 0.5. This is specific to this
   system's two-signal design: a low agreement rate is a diagnostic signal that
   the two detectors are frequently disagreeing, which helps explain why a
   given submission landed in `uncertain`.

Example response (against the 3 log entries shown above):

```json
{
  "total_submissions": 3,
  "detection_pattern": {
    "counts": {"likely_ai": 1, "likely_human": 1, "uncertain": 1},
    "ratios": {"likely_ai": 0.333, "likely_human": 0.333, "uncertain": 0.333}
  },
  "appeal_rate": 0.333,
  "signal_agreement_rate": 0.333
}
```

## Spec Reflection

**How the spec helped:** writing out the exact label text and the 0.70/0.30
threshold values in `planning.md` *before* touching code meant the label generator
and confidence scorer in Milestone 5 were almost mechanical to implement — there
was no ambiguity to resolve mid-implementation about what "uncertain" should mean
or what text a reader would see.

**Where implementation diverged:** the original plan weighted the two signals
`0.6 * llm_score + 0.4 * stylometric_score`. During Milestone 4 testing, I ran the
spec's "clearly AI-generated" boilerplate example through the pipeline and it came
back as `uncertain` (`combined_score = 0.63`) instead of `likely_ai`, even though
the LLM signal alone was confident (`0.80–0.90`). Printing both signal scores
separately (as the spec's debugging hint suggested) showed the stylometric
sub-scores were noisy and low on that short passage — not because the passage was
human-like, but because 3–4 sentences isn't enough data for sentence-variance and
vocabulary-diversity statistics to be meaningful. Since this directly matches a
blind spot I'd already named for the stylometric signal in `planning.md`, I
re-weighted to `0.7 * llm_score + 0.3 * stylometric_score`, giving the more
reliable signal more say while still letting stylometrics meaningfully move the
score when the two agree. I re-ran all test cases after the change to confirm the
verdicts and confidence spread still made sense.

## AI Usage

1. **Generating the stylometric signal and confidence scorer.** I gave the AI tool
   the "Detection Signals" and "Uncertainty Representation" sections from
   `planning.md`, plus the architecture diagram, and asked it to implement
   `get_stylometric_score` and `score_confidence` exactly per those specs. The
   first version used the planned `0.6/0.4` weighting faithfully — but as described
   above, testing showed that weighting misclassified the spec's own "clearly AI"
   example. I overrode the AI-generated weighting to `0.7/0.3` myself after
   diagnosing the cause, rather than accepting the spec-faithful default, since the
   test results were the more authoritative signal at that point.

2. **Picking the Flask port.** The project's recommended stack defaults to Flask
   on port 5000. When I asked the AI tool to scaffold the app and then tested it
   with `curl`, requests were rejected with a `403 Forbidden` from an `AirTunes`
   server header instead of a normal Flask response — macOS's AirPlay Receiver
   service already listens on port 5000 by default. I decided to move the app to
   port 5050 rather than disabling a system service, and updated the `curl`
   examples and `app.run()` call accordingly.

3. **Wording the transparency labels.** I gave the AI tool the exact label
   requirements from `planning.md` §5 and asked it to implement `get_label`. Its
   first draft of the `likely_ai` text included the phrase "AI signals" inside the
   user-facing string itself, which conflicts with the "no jargon" requirement —
   "signal" is a term for the underlying detection mechanism, not something a
   non-technical reader should have to parse. I rewrote the label text to keep
   "signals"-type language out of what's shown to end users, restricting it to the
   raw JSON fields returned alongside the label.
