// ── State ──────────────────────────────────────────────────────────────────
let currentContentId = null;

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
  // Format a 0-1 float as "0.85"
  return typeof n === 'number' ? n.toFixed(2) : '—';
}

function pct(n) {
  return typeof n === 'number' ? Math.round(n * 100) + '%' : '—';
}

function timeAgo(isoString) {
  const diff = (Date.now() - new Date(isoString).getTime()) / 1000;
  if (diff < 60)  return 'just now';
  if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
  if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
  return Math.floor(diff / 86400) + 'd ago';
}

// ── Attribution display map ──────────────────────────────────────────────────

const VERDICTS = {
  likely_ai:    { label: 'LIKELY AI-GENERATED', cls: 'ai' },
  likely_human: { label: 'LIKELY HUMAN-WRITTEN', cls: 'human' },
  uncertain:    { label: 'UNCERTAIN ORIGIN',    cls: 'uncertain' },
};

// ── Analyze ──────────────────────────────────────────────────────────────────

analyzeBtn.addEventListener('click', async () => {
  const text = textInput.value.trim();
  if (!text) { showError('Please paste some text first.'); return; }
  clearError();
  setLoading(true);

  try {
    const res = await fetch('/submit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text,
        creator_id: creatorInput.value.trim() || 'anonymous',
      }),
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

  const v = VERDICTS[data.attribution] || VERDICTS.uncertain;
  const confPct = Math.round(data.confidence * 100);

  // Verdict badge
  verdictBadge.textContent = v.label;
  verdictBadge.className   = 'verdict-badge ' + v.cls;

  // Confidence text + bar
  confidenceText.textContent = `Confidence: ${confPct}%`;
  confBarFill.style.width    = confPct + '%';
  confBarFill.className      = 'confidence-bar-fill ' + v.cls;

  // Label text
  labelText.textContent = data.label;

  // Scores
  llmVal.textContent   = fmt(data.llm_score);
  styloVal.textContent = fmt(data.stylometric_score);
  llmBar.style.width   = (data.llm_score * 100) + '%';
  styloBar.style.width = (data.stylometric_score * 100) + '%';

  // Content ID
  contentIdVal.textContent = data.content_id;

  // Show section
  resultSection.classList.remove('hidden');
  resultSection.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// ── New analysis ─────────────────────────────────────────────────────────────

newAnalysisBtn.addEventListener('click', () => {
  resultSection.classList.add('hidden');
  textInput.value = '';
  creatorInput.value = '';
  textInput.focus();
  currentContentId = null;
});

// ── Appeal ───────────────────────────────────────────────────────────────────

appealBtn.addEventListener('click', () => {
  if (!currentContentId) return;
  modalOverlay.classList.remove('hidden');
  appealText.focus();
});

function closeModal() {
  modalOverlay.classList.add('hidden');
  appealText.value = '';
}

modalClose.addEventListener('click', closeModal);
cancelAppeal.addEventListener('click', closeModal);
modalOverlay.addEventListener('click', (e) => {
  if (e.target === modalOverlay) closeModal();
});

submitAppealBtn.addEventListener('click', async () => {
  const reasoning = appealText.value.trim();
  if (!reasoning) { showToast('Please write your reasoning first.'); return; }

  submitAppealBtn.disabled = true;
  submitAppealBtn.textContent = 'Submitting…';

  try {
    const res = await fetch('/appeal', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content_id: currentContentId, creator_reasoning: reasoning }),
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
    submitAppealBtn.disabled = false;
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
    document.getElementById('stat-ai').textContent        = c.likely_ai   ?? 0;
    document.getElementById('stat-human').textContent     = c.likely_human ?? 0;
    document.getElementById('stat-uncertain').textContent = c.uncertain   ?? 0;
    document.getElementById('stat-appeal').textContent    = pct(data.appeal_rate);
    document.getElementById('stat-agreement').textContent = pct(data.signal_agreement_rate);
  } catch { /* analytics is non-critical, fail silently */ }
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
    tbody.innerHTML = '<tr><td colspan="7" class="table-empty">No submissions yet.</td></tr>';
    return;
  }

  tbody.innerHTML = entries.map(e => {
    const v     = VERDICTS[e.attribution] || VERDICTS.uncertain;
    const badge = `<span class="status-badge ${e.status === 'under_review' ? 'status-review' : 'status-classified'}">${e.status === 'under_review' ? 'Under review' : 'Classified'}</span>`;
    return `
      <tr>
        <td>${escHtml(e.creator_id || '—')}</td>
        <td class="attr-${v.cls}">${v.label}</td>
        <td>${pct(e.confidence)}</td>
        <td>${fmt(e.llm_score)}</td>
        <td>${fmt(e.stylometric_score)}</td>
        <td>${badge}</td>
        <td>${timeAgo(e.timestamp)}</td>
      </tr>`;
  }).join('');
}

function escHtml(str) {
  return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ── Init ─────────────────────────────────────────────────────────────────────

loadAnalytics();
loadLog();
