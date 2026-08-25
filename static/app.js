// ── State ──────────────────────────────────────────────────────────────────
let currentContentId = null;   // content_id from the most recent analysis
let appealTargetId   = null;   // content_id being appealed (from result card OR log table)

// ── DOM refs ────────────────────────────────────────────────────────────────
const textInput      = document.getElementById('text-input');
const creatorInput   = document.getElementById('creator-id');
const analyzeBtn     = document.getElementById('analyze-btn');
const errorMsg       = document.getElementById('error-msg');
const resultSection  = document.getElementById('result-section');

const verdictBadge   = document.getElementById('verdict-badge');
const confidenceText = document.getElementById('confidence-text');
const confBarFill    = document.getElementById('confidence-bar-fill');
const labelText      = document.getElementById('verdict-label-text');
const llmVal         = document.getElementById('llm-score-val');
const styloVal       = document.getElementById('stylo-score-val');
const llmBar         = document.getElementById('llm-bar');
const styloBar       = document.getElementById('stylo-bar');
const appealBtn      = document.getElementById('appeal-btn');
const newAnalysisBtn = document.getElementById('new-analysis-btn');
const contentIdVal   = document.getElementById('content-id-val');

const modalOverlay   = document.getElementById('modal-overlay');
const modalClose     = document.getElementById('modal-close');
const cancelAppeal   = document.getElementById('cancel-appeal');
const appealText     = document.getElementById('appeal-text');
const submitAppealBtn= document.getElementById('submit-appeal-btn');

const toast          = document.getElementById('toast');

// ── Constants ───────────────────────────────────────────────────────────────
const MIN_TEXT_LENGTH = 20;   // characters
const MAX_TEXT_LENGTH = 8000; // characters — prevent absurdly large inputs

const VERDICTS = {
  likely_ai:    { label: 'LIKELY AI-GENERATED', cls: 'ai' },
  likely_human: { label: 'LIKELY HUMAN-WRITTEN', cls: 'human' },
  uncertain:    { label: 'UNCERTAIN ORIGIN',     cls: 'uncertain' },
};

// ── Helpers ─────────────────────────────────────────────────────────────────

function showToast(msg, duration = 3500) {
  toast.textContent = msg;
  toast.classList.remove('hidden');
  setTimeout(() => toast.classList.add('hidden'), duration);
}

function showError(msg) {
  errorMsg.textContent = msg;
  errorMsg.classList.remove('hidden');
}

function clearError() {
  errorMsg.textContent = '';
  errorMsg.classList.add('hidden');
}

function setLoading(on) {
  analyzeBtn.disabled = on;
  analyzeBtn.textContent = on ? 'Analyzing…' : 'Analyze';
}

function fmt(n) {
  return typeof n === 'number' ? n.toFixed(2) : '—';
}

function pct(n) {
  return typeof n === 'number' ? Math.round(n * 100) + '%' : '—';
}

function timeAgo(isoString) {
  const diff = (Date.now() - new Date(isoString).getTime()) / 1000;
  if (diff < 60)   return 'just now';
  if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
  if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
  return Math.floor(diff / 86400) + 'd ago';
}

function escHtml(str) {
  return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ── Input validation ─────────────────────────────────────────────────────────
// Full authentication (login/password) would be overkill for a demo tool
// where the rate limiter already handles abuse. Instead we validate inputs
// client-side before they're sent to the API, which prevents empty submissions,
// accidental pastes of huge documents, and malformed creator IDs.

function validateInput(text, creatorId) {
  if (!text) return 'Please paste some text first.';
  if (text.length < MIN_TEXT_LENGTH)
    return `Text is too short — paste at least ${MIN_TEXT_LENGTH} characters for a meaningful result.`;
  if (text.length > MAX_TEXT_LENGTH)
    return `Text is too long (${text.length} chars). Please trim it to under ${MAX_TEXT_LENGTH} characters.`;
  if (creatorId && !/^[a-zA-Z0-9_\-\.@]{1,64}$/.test(creatorId))
    return 'Creator ID can only contain letters, numbers, _, -, . and @ (max 64 chars).';
  return null; // valid
}

// ── Analyze ──────────────────────────────────────────────────────────────────

analyzeBtn.addEventListener('click', async () => {
  const text      = textInput.value.trim();
  const creatorId = creatorInput.value.trim();

  clearError();

  const validationError = validateInput(text, creatorId);
  if (validationError) { showError(validationError); return; }

  setLoading(true);

  try {
    const res = await fetch('/submit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, creator_id: creatorId || 'anonymous' }),
    });

    if (res.status === 429) {
      showError('Rate limit reached — wait a minute and try again.');
      return;
    }

    const data = await res.json();
    if (!res.ok) { showError(data.error || 'Something went wrong.'); return; }

    showResult(data);
    loadAnalytics();
    loadLog();
  } catch (err) {
    showError('Could not reach the server. Is it running?');
  } finally {
    setLoading(false);
  }
});

function showResult(data) {
  currentContentId = data.content_id;
  appealTargetId   = data.content_id;  // appeal btn in result card targets latest result

  const v = VERDICTS[data.attribution] || VERDICTS.uncertain;
  const confPct = Math.round(data.confidence * 100);

  verdictBadge.textContent   = v.label;
  verdictBadge.className     = 'verdict-badge ' + v.cls;
  confidenceText.textContent = `Confidence: ${confPct}%`;
  confBarFill.style.width    = confPct + '%';
  confBarFill.className      = 'confidence-bar-fill ' + v.cls;
  labelText.textContent      = data.label;

  llmVal.textContent   = fmt(data.llm_score);
  styloVal.textContent = fmt(data.stylometric_score);
  llmBar.style.width   = (data.llm_score * 100) + '%';
  styloBar.style.width = (data.stylometric_score * 100) + '%';

  contentIdVal.textContent = data.content_id;

  resultSection.classList.remove('hidden');
  resultSection.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// ── New analysis ─────────────────────────────────────────────────────────────

newAnalysisBtn.addEventListener('click', () => {
  resultSection.classList.add('hidden');
  textInput.value    = '';
  creatorInput.value = '';
  textInput.focus();
  currentContentId = null;
  appealTargetId   = null;
});

// ── Appeal ───────────────────────────────────────────────────────────────────
// Appeals can be triggered from two places:
//   1. The result card (after analyzing) — targets the most recent content_id
//   2. The log table appeal button — targets any past submission

function openAppealModal(contentId) {
  appealTargetId = contentId;
  appealText.value = '';
  modalOverlay.classList.remove('hidden');
  appealText.focus();
}

function closeModal() {
  modalOverlay.classList.add('hidden');
  appealText.value = '';
  appealTargetId   = null;
}

// Appeal from result card
appealBtn.addEventListener('click', () => {
  if (!currentContentId) return;
  openAppealModal(currentContentId);
});

modalClose.addEventListener('click', closeModal);
cancelAppeal.addEventListener('click', closeModal);
modalOverlay.addEventListener('click', (e) => {
  if (e.target === modalOverlay) closeModal();
});

submitAppealBtn.addEventListener('click', async () => {
  const reasoning = appealText.value.trim();
  if (!reasoning) { showToast('Please write your reasoning first.'); return; }
  if (!appealTargetId)  { showToast('No submission selected.'); return; }

  submitAppealBtn.disabled    = true;
  submitAppealBtn.textContent = 'Submitting…';

  try {
    const res = await fetch('/appeal', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content_id: appealTargetId, creator_reasoning: reasoning }),
    });
    const data = await res.json();
    if (res.ok) {
      closeModal();
      showToast('Appeal submitted. A human reviewer will examine it.');
      loadLog();
    } else {
      showToast(data.error || 'Appeal failed.');
    }
  } catch {
    showToast('Could not reach the server.');
  } finally {
    submitAppealBtn.disabled    = false;
    submitAppealBtn.textContent = 'Submit Appeal';
  }
});

// ── Analytics ────────────────────────────────────────────────────────────────

async function loadAnalytics() {
  try {
    const res  = await fetch('/analytics');
    const data = await res.json();
    const c    = data.detection_pattern?.counts || {};

    document.getElementById('stat-total').textContent     = data.total_submissions ?? '—';
    document.getElementById('stat-ai').textContent        = c.likely_ai    ?? 0;
    document.getElementById('stat-human').textContent     = c.likely_human ?? 0;
    document.getElementById('stat-uncertain').textContent = c.uncertain    ?? 0;
    document.getElementById('stat-appeal').textContent    = pct(data.appeal_rate);
    document.getElementById('stat-agreement').textContent = pct(data.signal_agreement_rate);
  } catch { /* analytics is non-critical */ }
}

// ── Log ──────────────────────────────────────────────────────────────────────

async function loadLog() {
  try {
    const res  = await fetch('/log');
    const data = await res.json();
    renderLog(data.entries || []);
  } catch { /* fail silently */ }
}

function renderLog(entries) {
  const tbody = document.getElementById('log-body');
  if (!entries.length) {
    tbody.innerHTML = '<tr><td colspan="8" class="table-empty">No submissions yet.</td></tr>';
    return;
  }

  tbody.innerHTML = entries.map(e => {
    const v       = VERDICTS[e.attribution] || VERDICTS.uncertain;
    const isUnderReview = e.status === 'under_review';

    const statusBadge = `<span class="status-badge ${isUnderReview ? 'status-review' : 'status-classified'}">${isUnderReview ? 'Under review' : 'Classified'}</span>`;

    // Show appeal button only if not already under review
    const appealCell = isUnderReview
      ? '<td></td>'
      : `<td><button class="log-appeal-btn" data-id="${escHtml(e.content_id)}">Appeal</button></td>`;

    return `
      <tr>
        <td>${escHtml(e.creator_id || '—')}</td>
        <td class="attr-${v.cls}">${v.label}</td>
        <td>${pct(e.confidence)}</td>
        <td>${fmt(e.llm_score)}</td>
        <td>${fmt(e.stylometric_score)}</td>
        <td>${statusBadge}</td>
        <td>${timeAgo(e.timestamp)}</td>
        ${appealCell}
      </tr>`;
  }).join('');

  // Attach click handlers to all appeal buttons in the table
  tbody.querySelectorAll('.log-appeal-btn').forEach(btn => {
    btn.addEventListener('click', () => openAppealModal(btn.dataset.id));
  });
}

// ── Init ─────────────────────────────────────────────────────────────────────

loadAnalytics();
loadLog();
