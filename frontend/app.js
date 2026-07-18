/* ==========================================================
   FXGuard AI — app.js  v3
   Features: navigation, loading states, results-persist,
   chart timeframe, risk modal, RWF converter,
   recent-checks localStorage, stale banner, print export
   ========================================================== */
'use strict';

const API = window.location.origin;

/* --- State ------------------------------------------------ */
let selectedHorizon     = 7;
let selectedMainHorizon = 7;
let selectedCurrency    = 'USD';
let latestResult        = null;
let latestRate          = null;   // kept for converter
let historyChart        = null;
let probChart           = null;
let currentDays         = 180;   // active chart range
let modelMetadata       = {};

const FALLBACK_CURRENCIES = {
  USD: { name: 'US Dollar', symbol: '$', decimals: 2 },
  EUR: { name: 'Euro', symbol: '€', decimals: 2 },
  KES: { name: 'Kenyan Shilling', symbol: 'KSh', decimals: 4 },
};
let currencyCatalog = { ...FALLBACK_CURRENCIES };

/* --- Page titles ------------------------------------------ */
const PAGE_TITLES = {
  dashboard:  'Dashboard',
  assessment: 'Payment check',
  results:    'Results',
  decision:   'Recommendations',
  feedback:   'User feedback',
};

/* ==========================================================
   NAVIGATION
   ========================================================== */
function showScreen(id) {
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(b => {
    const isActive = b.dataset.screen === id;
    b.classList.toggle('active', isActive);
    b.setAttribute('aria-current', isActive ? 'page' : 'false');
  });

  const target = document.getElementById(id);
  if (target) target.classList.add('active');

  const titleEl = document.getElementById('pageTitle');
  if (titleEl) titleEl.textContent = PAGE_TITLES[id] ?? id;

  // Re-render result if returning to results/decision and we have data
  if ((id === 'results' || id === 'decision') && latestResult) {
    renderResult(latestResult);
  }
}

document.querySelectorAll('.nav-item[data-screen]').forEach(btn =>
  btn.addEventListener('click', () => showScreen(btn.dataset.screen))
);
document.querySelectorAll('[data-go-screen]').forEach(el =>
  el.addEventListener('click', () => showScreen(el.dataset.goScreen))
);

/* ==========================================================
   HORIZON TOGGLES
   ========================================================== */
document.querySelectorAll('[data-horizon]').forEach(btn =>
  btn.addEventListener('click', () => {
    selectedHorizon = Number(btn.dataset.horizon);
    document.querySelectorAll('[data-horizon]').forEach(b =>
      b.classList.toggle('active', b === btn)
    );
  })
);
document.querySelectorAll('[data-horizon-main]').forEach(btn =>
  btn.addEventListener('click', () => {
    selectedMainHorizon = Number(btn.dataset.horizonMain);
    document.querySelectorAll('[data-horizon-main]').forEach(b =>
      b.classList.toggle('active', b === btn)
    );
  })
);

/* ==========================================================
   FORMATTERS
   ========================================================== */
function fmt(num) {
  return new Intl.NumberFormat('en-RW', { maximumFractionDigits: 0 }).format(num);
}
function fmtRate(num, currency = selectedCurrency) {
  const decimals = currencyCatalog[currency]?.decimals ?? 3;
  return new Intl.NumberFormat('en-RW', {
    minimumFractionDigits: Math.min(decimals, 2),
    maximumFractionDigits: decimals,
  }).format(num);
}
function fmtSigned(num) {
  return `${num > 0 ? '+' : ''}${fmtRate(num)}`;
}
function fmtPct(num) {
  return `${num > 0 ? '+' : ''}${num.toFixed(2)}%`;
}
function pct(val) {
  return `${Math.round((val ?? 0) * 100)}%`;
}

/* ==========================================================
   TOAST
   ========================================================== */
let toastTimer = null;
function toast(msg, type = '') {
  const el = document.getElementById('toast');
  if (!el) return;
  el.textContent = msg;
  el.className = `toast${type ? ' ' + type : ''}`;
  el.style.display = 'block';
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.style.display = 'none'; }, 3800);
}

/* ==========================================================
   UTILITIES
   ========================================================== */
function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val ?? '';
}
function setHTML(id, html) {
  const el = document.getElementById(id);
  if (el) el.innerHTML = html;
}
function show(id) { document.getElementById(id)?.classList.remove('hidden'); }
function hide(id) { document.getElementById(id)?.classList.add('hidden'); }

/* ==========================================================
   FEATURE 1 — STALE DATA BANNER
   ========================================================== */
function showStaleBanner(freshness) {
  const banner = document.getElementById('staleBanner');
  const text   = document.getElementById('staleBannerText');
  if (!banner || !text) return;

  if (freshness.status === 'fresh') {
    banner.classList.add('hidden');
    banner.classList.remove('stale');
    document.querySelector('.main-content')?.classList.remove('has-banner');
    return;
  }

  const days = freshness.days_since_latest_rate;
  const date = freshness.latest_rate_date;

  if (freshness.status === 'aging') {
    banner.classList.remove('hidden', 'stale');
    text.textContent = `Using ${freshness.pair} BNR rate data from ${date} (${days} days ago). The result uses the most recent information available.`;
    document.querySelector('.main-content')?.classList.add('has-banner');
  } else {
    banner.classList.remove('hidden');
    banner.classList.add('stale');
    text.textContent = `${freshness.pair} rate data is from ${date} (${days} days ago). Results reflect conditions as of that date.`;
    document.querySelector('.main-content')?.classList.add('has-banner');
  }

  document.getElementById('staleBannerClose')?.addEventListener('click', () => {
    banner.classList.add('hidden');
    document.querySelector('.main-content')?.classList.remove('has-banner');
  }, { once: true });
}

/* ==========================================================
   FEATURE 2 — SIDEBAR STATUS PILL
   ========================================================== */
function setStatus(freshness) {
  const dot  = document.querySelector('.status-dot');
  const text = document.getElementById('sidebarStatusText');
  if (!dot || !text) return;
  const map = {
    fresh: { cls: 'fresh', label: 'Data up to date' },
    aging: { cls: 'aging', label: 'Data aging' },
    stale: { cls: 'stale', label: 'Data stale' },
  };
  const s = map[freshness?.status] ?? { cls: '', label: 'Unknown' };
  dot.className    = `status-dot ${s.cls}`;
  text.textContent = s.label;
}

/* ==========================================================
   FEATURE 3 — RATE BADGE + KPI CARDS
   ========================================================== */
function populateRateUI(latest) {
  latestRate = latest.mid_rate;
  const currency = latest.currency ?? selectedCurrency;
  const rate = fmtRate(latest.mid_rate, currency);
  setText('badgeRate',   rate);
  setText('badgeDate',   latest.date);
  setText('badgeLabel',  `BNR average rate · ${currency}/RWF`);
  setText('kpiRateLabel', `Current ${currency}/RWF rate`);
  setText('kpiRate',     `${rate} RWF`);
  setText('kpiRateDate', `As of ${latest.date}`);
  setText('assessmentSource', latest.source ?? 'BNR exchange rates');
  updateConverter();
}

function populateModelUI(metadata, currency = selectedCurrency) {
  const models = metadata?.models?.[currency] ?? {};
  const m7  = models?.['7d']?.best_model  ? 'Available' : 'Unavailable';
  const m14 = models?.['14d']?.best_model ? 'Available' : 'Unavailable';
  setText('kpiModel7',  m7);
  setText('kpiModel14', m14);
}

/* ==========================================================
   FEATURE 4 — LIVE RWF CONVERTER
   ========================================================== */
function updateConverter() {
  const foreignEl = document.getElementById('convForeign');
  const rwfEl  = document.getElementById('convRWF');
  const noteEl = document.getElementById('convRateNote');
  if (!foreignEl || !rwfEl || !latestRate) return;

  setText('convCurrencyPrefix', selectedCurrency);
  foreignEl.setAttribute('aria-label', `Amount in ${selectedCurrency}`);
  if (noteEl) noteEl.textContent = `at ${fmtRate(latestRate)} RWF/${selectedCurrency}`;
  const value = parseFloat(foreignEl.value);
  rwfEl.value = isNaN(value) ? '' : Math.round(value * latestRate);
}

document.getElementById('convForeign')?.addEventListener('input', updateConverter);
document.getElementById('convRWF')?.addEventListener('input', event => {
  const foreignEl = document.getElementById('convForeign');
  const value = parseFloat(event.target.value);
  if (foreignEl) foreignEl.value = isNaN(value) || !latestRate ? '' : (value / latestRate).toFixed(2);
});

/* ==========================================================
   FEATURE 5 — CHART WITH TIMEFRAME SELECTOR
   ========================================================== */
async function drawHistory(days = 180) {
  currentDays = days;
  const currency = selectedCurrency;

  // Update active button
  document.querySelectorAll('.chart-range-btn').forEach(btn => {
    btn.classList.toggle('active', Number(btn.dataset.days) === days);
  });

  const response = await fetch(`${API}/api/history?days=${days}&currency=${currency}`);
  if (!response.ok) throw new Error(`Could not load ${currency}/RWF history`);
  const data = await response.json();
  if (currency !== selectedCurrency) return;
  const points = data.points ?? [];
  updateChartStats(points);

  const canvas = document.getElementById('historyChart');
  if (!canvas) return;

  if (typeof Chart === 'undefined') {
    drawFallbackLine(canvas, points);
    return;
  }
  if (historyChart) { historyChart.destroy(); historyChart = null; }

  const values   = points.map(p => p.mid_rate);
  const rawMin   = Math.min(...values);
  const rawMax   = Math.max(...values);
  const rawRange = rawMax - rawMin || 1;
  const ctx      = canvas.getContext('2d');
  const grad     = ctx.createLinearGradient(0, 0, 0, 300);
  grad.addColorStop(0, 'rgba(59,91,219,0.18)');
  grad.addColorStop(1, 'rgba(59,91,219,0.01)');

  historyChart = new Chart(canvas, {
    type: 'line',
    data: {
      labels: points.map(p => p.date),
      datasets: [{
        label: `${currency}/RWF reference rate`,
        data: values,
        tension: 0.3,
        borderColor: '#3b5bdb',
        backgroundColor: grad,
        fill: true,
        pointRadius: points.map((_, i) => i === points.length - 1 ? 4 : 0),
        pointHoverRadius: 5,
        pointBackgroundColor: '#3b5bdb',
        borderWidth: 2,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          displayColors: false,
          backgroundColor: '#1a1f2e',
          titleColor: '#a0aec0',
          bodyColor: '#fff',
          padding: 10,
          cornerRadius: 8,
          callbacks: {
            title: items => items[0]?.label ?? '',
            label: item  => `${fmtRate(item.parsed.y)} RWF`,
          },
        },
      },
      scales: {
        x: {
          grid: { display: false },
          border: { display: false },
          ticks: {
            maxTicksLimit: 7,
            color: '#718096',
            font: { size: 11, family: "'Inter', sans-serif" },
            callback(val) {
              const label = this.getLabelForValue(val);
              return label ? label.slice(days <= 365 ? 5 : 0) : '';
            },
          },
        },
        y: {
          min: rawMin - rawRange * 0.08,
          max: rawMax + rawRange * 0.08,
          grid: { color: 'rgba(0,0,0,0.05)' },
          border: { display: false },
          ticks: {
            maxTicksLimit: 5,
            color: '#718096',
            font: { size: 11, family: "'IBM Plex Mono', monospace" },
            callback: v => fmtRate(v),
          },
        },
      },
    },
  });
}

function updateChartStats(points) {
  if (!points.length) return;
  const first  = points[0];
  const last   = points[points.length - 1];
  const delta  = last.mid_rate - first.mid_rate;
  const pctVal = first.mid_rate ? (delta / first.mid_rate) * 100 : 0;
  const isFlat = Math.abs(pctVal) < 0.05;
  const trend  = isFlat ? 'Flat' : pctVal > 0 ? 'Rising' : 'Falling';

  setText('statLatest', `${fmtRate(last.mid_rate)} RWF`);
  setText('statChange',  `${fmtSigned(delta)} (${fmtPct(pctVal)})`);

  const trendEl = document.getElementById('statTrend');
  if (trendEl) {
    trendEl.textContent = trend;
    trendEl.style.color = isFlat ? '' : pctVal > 0 ? 'var(--amber-500)' : 'var(--teal-500)';
  }
}

/* Chart range buttons */
document.querySelectorAll('.chart-range-btn').forEach(btn =>
  btn.addEventListener('click', () => drawHistory(Number(btn.dataset.days)))
);

/* Fallback canvas renderer */
function drawFallbackLine(canvas, points) {
  if (!points.length) return;
  const dpr  = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  const W    = Math.max(rect.width  || 600, 300);
  const H    = Math.max(rect.height || 220, 140);
  canvas.width  = W * dpr; canvas.height = H * dpr;
  canvas.style.width = `${W}px`; canvas.style.height = `${H}px`;
  const ctx  = canvas.getContext('2d');
  ctx.scale(dpr, dpr);
  const vals = points.map(p => p.mid_rate);
  const vMin = Math.min(...vals), vMax = Math.max(...vals);
  const vR   = vMax - vMin || 1;
  const pad  = { t:12, r:12, b:28, l:56 };
  const cW   = W - pad.l - pad.r, cH = H - pad.t - pad.b;
  const xOf  = i => pad.l + (cW * i) / Math.max(points.length - 1, 1);
  const yOf  = v => pad.t + cH - ((v - vMin) / vR) * cH;
  ctx.fillStyle = '#fff'; ctx.fillRect(0,0,W,H);
  ctx.strokeStyle = 'rgba(0,0,0,0.06)'; ctx.lineWidth = 1;
  for (let i=0;i<=4;i++) {
    const y = pad.t+(cH/4)*i;
    ctx.beginPath(); ctx.moveTo(pad.l,y); ctx.lineTo(W-pad.r,y); ctx.stroke();
    ctx.fillStyle='#718096'; ctx.font='10px IBM Plex Mono,monospace';
    ctx.textAlign='right'; ctx.fillText(fmtRate(vMax-(vR/4)*i), pad.l-4, y+3);
  }
  const grad = ctx.createLinearGradient(0,pad.t,0,H-pad.b);
  grad.addColorStop(0,'rgba(59,91,219,0.18)'); grad.addColorStop(1,'rgba(59,91,219,0)');
  ctx.beginPath();
  points.forEach((p,i) => { const x=xOf(i),y=yOf(p.mid_rate); i===0?ctx.moveTo(x,y):ctx.lineTo(x,y); });
  ctx.lineTo(xOf(points.length-1),H-pad.b); ctx.lineTo(xOf(0),H-pad.b);
  ctx.closePath(); ctx.fillStyle=grad; ctx.fill();
  ctx.beginPath();
  points.forEach((p,i) => { const x=xOf(i),y=yOf(p.mid_rate); i===0?ctx.moveTo(x,y):ctx.lineTo(x,y); });
  ctx.strokeStyle='#3b5bdb'; ctx.lineWidth=2; ctx.stroke();
  const lx=xOf(points.length-1), ly=yOf(vals[vals.length-1]);
  ctx.beginPath(); ctx.arc(lx,ly,4,0,Math.PI*2); ctx.fillStyle='#3b5bdb'; ctx.fill();
}

/* ==========================================================
   FEATURE 6 — RECENT CHECKS (localStorage)
   ========================================================== */
const HISTORY_KEY = 'fxguard_checks';
const MAX_HISTORY = 10;

function checkSignature(check) {
  return [
    String(check.currency ?? 'USD').toUpperCase(),
    Number(check.amount ?? 0),
    Number(check.horizon ?? 0),
  ].join('|');
}

function formatCheckTime(check) {
  const checkedAt = check.checkedAt ? new Date(check.checkedAt) : null;
  if (checkedAt && !Number.isNaN(checkedAt.getTime())) {
    return new Intl.DateTimeFormat('en-GB', {
      day: '2-digit', month: 'short', year: 'numeric',
      hour: '2-digit', minute: '2-digit', hour12: false,
    }).format(checkedAt);
  }
  return check.date ?? '—';
}

function saveCheck(r) {
  const entry = {
    checkedAt: new Date().toISOString(),
    date:    new Date().toLocaleDateString('en-GB', { day:'2-digit', month:'short', year:'numeric' }),
    amount:  r.amount ?? r.amount_currency ?? r.amount_usd,
    currency: r.currency ?? 'USD',
    horizon: r.horizon_days,
    risk:    r.risk_level,
    cost:    r.current_cost_rwf,
    extra:   r.possible_extra_cost_rwf,
    rate:    r.current_rate,
    full:    r,
  };
  const signature = checkSignature(entry);
  const checks = getChecks().filter(check => checkSignature(check) !== signature);
  checks.unshift(entry);
  localStorage.setItem(HISTORY_KEY, JSON.stringify(checks.slice(0, MAX_HISTORY)));
  renderRecentChecks();
}

function getChecks() {
  try {
    const stored = JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]');
    const seen = new Set();
    const unique = stored.filter(check => {
      const signature = checkSignature(check);
      if (seen.has(signature)) return false;
      seen.add(signature);
      return true;
    });
    if (unique.length !== stored.length) {
      localStorage.setItem(HISTORY_KEY, JSON.stringify(unique.slice(0, MAX_HISTORY)));
    }
    return unique.slice(0, MAX_HISTORY);
  }
  catch { return []; }
}

function renderRecentChecks() {
  const checks  = getChecks();
  const section = document.getElementById('recentChecks');
  const tbody   = document.getElementById('recentChecksBody');
  if (!section || !tbody) return;

  if (!checks.length) { section.classList.add('hidden'); return; }
  section.classList.remove('hidden');

  tbody.innerHTML = checks.map((c, i) => `
    <tr>
      <td>${formatCheckTime(c)}</td>
      <td class="mono">${currencyCatalog[c.currency ?? 'USD']?.symbol ?? c.currency ?? ''} ${new Intl.NumberFormat('en').format(c.amount)}</td>
      <td>${c.horizon} days</td>
      <td><span class="risk-pill ${c.risk}">${c.risk}</span></td>
      <td class="mono">RWF ${fmt(c.cost)}</td>
      <td class="mono" style="color:var(--red-500)">+RWF ${fmt(c.extra)}</td>
      <td class="td-action">
        <button class="btn-ghost" style="font-size:11px;padding:4px 8px" data-reopen="${i}"
          title="View full result for this check">
          View
        </button>
      </td>
    </tr>`
  ).join('');

  // Wire each View button to load the stored full result and navigate to Results screen
  tbody.querySelectorAll('[data-reopen]').forEach(btn =>
    btn.addEventListener('click', () => {
      const idx   = Number(btn.dataset.reopen);
      const check = checks[idx];

      if (check.full) {
        // Restore as the active result and navigate to Results screen
        latestResult = check.full;
        renderResult(latestResult);
        showScreen('results');
        toast(`Showing check from ${formatCheckTime(check)}.`);
      } else {
        // Old entry without full data — show what we have and prompt re-run
        toast(`No full data for this entry — please re-run the assessment.`, 'error');
      }
    })
  );
}

document.getElementById('clearHistory')?.addEventListener('click', () => {
  localStorage.removeItem(HISTORY_KEY);
  renderRecentChecks();
  toast('History cleared.');
});

/* ==========================================================
   FEATURE 7 — RISK ASSESSMENT with loading state
   ========================================================== */
function setLoading(btnId, on) {
  const btn = document.getElementById(btnId);
  if (!btn) return;
  btn.classList.toggle('loading', on);
  btn.disabled = on;
}

async function runAssessment(amount, horizon, triggeredBy, currency = selectedCurrency) {
  if (!amount || amount <= 0) {
    toast('Enter a valid invoice amount.', 'error');
    return;
  }
  setLoading(triggeredBy, true);

  const body = JSON.stringify({
    currency,
    amount:         Number(amount),
    horizon:        Number(horizon),
  });

  let res;
  try {
    res = await fetch(`${API}/api/predict-risk`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body,
    });
  } catch {
    toast('Network error — is the backend running?', 'error');
    setLoading(triggeredBy, false);
    return;
  }

  setLoading(triggeredBy, false);

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    toast(err.detail ?? 'Risk assessment failed.', 'error');
    return;
  }

  latestResult = await res.json();
  saveCheck(latestResult);
  renderResult(latestResult);
  showScreen('results');
}

document.getElementById('quickAnalyze')?.addEventListener('click', () =>
  runAssessment(
    document.getElementById('quickAmount')?.value,
    selectedHorizon,
    'quickAnalyze'
  )
);
document.getElementById('analyzeBtn')?.addEventListener('click', () =>
  runAssessment(
    document.getElementById('amount')?.value,
    selectedMainHorizon,
    'analyzeBtn',
    document.getElementById('currency')?.value ?? selectedCurrency
  )
);

/* ==========================================================
   RENDER RESULT
   ========================================================== */
const DRIVER_LABELS = {
  daily_return:         'Change since the previous day',
  return_7d:            'Change over the last 7 days',
  return_14d:           'Change over the last 14 days',
  ma_7:                 'Typical rate over the last 7 days',
  ma_30:                'Typical rate over the last 30 days',
  ma_gap:               'Difference between recent and longer-term rates',
  volatility_7d:        'How much the rate moved up and down this week',
  momentum_7d:          'Direction the rate moved this week',
  spread_pct:           'Gap between BNR buying and selling rates',
  depreciation_days_7d: 'Days the foreign currency became more expensive this week',
};

const DRIVER_PERCENTAGES = new Set([
  'daily_return', 'return_7d', 'return_14d', 'ma_gap',
  'volatility_7d', 'momentum_7d', 'spread_pct',
]);

function formatDriverValue(key, value, currency) {
  const number = Number(value);
  if (!Number.isFinite(number)) return String(value ?? '—');
  if (DRIVER_PERCENTAGES.has(key)) {
    const percentage = number * 100;
    return `${percentage > 0 ? '+' : ''}${percentage.toFixed(2)}%`;
  }
  if (key === 'ma_7' || key === 'ma_30') return `${fmtRate(number, currency)} RWF`;
  if (key === 'depreciation_days_7d') return `${Math.round(number)} of 7 days`;
  return fmtRate(number, currency);
}

const RISK_MEANINGS = {
  Low: 'The rate has been relatively stable recently.',
  Medium: 'The rate could make this payment moderately more expensive.',
  High: 'The rate could make this payment noticeably more expensive.',
};

function renderResult(r) {
  hide('emptyResult');    show('resultContent');
  hide('emptyDecision');  show('decisionContent');

  /* Risk card */
  const riskEl = document.getElementById('riskLevel');
  if (riskEl) {
    riskEl.textContent = r.risk_level;
    riskEl.className   = `summary-value risk-${r.risk_level}`;
  }
  const summaryRisk = document.querySelector('.summary-risk');
  if (summaryRisk) summaryRisk.className = `summary-card summary-risk level-${r.risk_level}`;

  setText('riskMeaning',     RISK_MEANINGS[r.risk_level] ?? 'Review the recent rate information carefully.');
  setText('currentCost',     `RWF ${fmt(r.current_cost_rwf)}`);
  setText('currentRateText', `At today's rate of ${fmtRate(r.current_rate, r.currency)} RWF per ${r.currency}`);
  setText('extraCost',       `RWF ${fmt(r.possible_extra_cost_rwf)}`);

  const confidence = r.confidence_score ?? r.confidence ?? 0;
  const topLabel   = r.top_probability_label ?? r.risk_level;
  const topProb    = r.predicted_probability ?? confidence;
  setText('confidenceText',
    `Strength of this result: ${pct(confidence)}. The information points most strongly to ${topLabel} risk (${pct(topProb)}).`
  );

  /* Key drivers */
  const driversEl = document.getElementById('drivers');
  if (driversEl) {
    driversEl.innerHTML = Object.entries(r.key_drivers ?? {})
      .map(([k, v]) =>
        `<div class="driver-row">
           <span>${DRIVER_LABELS[k] ?? k.replaceAll('_',' ')}</span>
           <strong>${formatDriverValue(k, v, r.currency)}</strong>
         </div>`
      ).join('');
  }

  /* Recommendations */
  const recHtml = (r.recommendations ?? [])
    .map(x => `<div class="rec-item ${r.risk_level}">${x}</div>`)
    .join('');
  setHTML('resultRecommendations', recHtml);
  setHTML('decisionRecommendations', recHtml);

  /* Probability chart */
  renderProbChart(r.class_probabilities ?? {});

  /* Scenario table */
  const amount = r.amount ?? r.amount_currency ?? r.amount_usd;
  const symbol = r.currency_symbol ?? currencyCatalog[r.currency]?.symbol ?? r.currency;
  setHTML('scenarioRows', `
    <tr><td>Payment amount</td>     <td>${symbol} ${fmt(amount)} ${r.currency}</td></tr>
    <tr><td>Current rate</td>        <td>${fmtRate(r.current_rate, r.currency)} RWF / ${r.currency}</td></tr>
    <tr><td>Cost at current rate</td><td>RWF ${fmt(r.current_cost_rwf)}</td></tr>
    <tr><td>Possible added cost</td>
        <td style="color:var(--red-500)">RWF ${fmt(r.possible_extra_cost_rwf)}</td></tr>
    <tr><td>Suggested safety buffer</td>
        <td style="color:var(--amber-700)">RWF ${fmt(r.suggested_margin_buffer_rwf)}</td></tr>
  `);
  setText('disclaimer',
    `This estimate uses the current BNR rate for ${r.currency}/RWF and a cautious estimate of possible extra cost. ` +
    'It is for planning only — not a guaranteed future rate.'
  );
}

function renderProbChart(probs) {
  const canvas = document.getElementById('probChart');
  if (!canvas) return;
  if (probChart) { probChart.destroy(); probChart = null; }
  if (typeof Chart === 'undefined') return;

  const labels = Object.keys(probs);
  const values = Object.values(probs).map(p => +(p * 100).toFixed(1));
  const colors = {
    Low:    { bg:'rgba(12,166,120,0.85)',  border:'#0ca678' },
    Medium: { bg:'rgba(245,159,0,0.85)',   border:'#f59f00' },
    High:   { bg:'rgba(250,82,82,0.85)',   border:'#fa5252' },
  };

  probChart = new Chart(canvas, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        data: values,
        backgroundColor: labels.map(l => (colors[l] ?? colors.Low).bg),
        borderColor:     labels.map(l => (colors[l] ?? colors.Low).border),
        borderWidth: 1,
        borderRadius: 6,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          displayColors: false,
          backgroundColor: '#1a1f2e',
          titleColor: '#a0aec0',
          bodyColor: '#fff',
          padding: 10, cornerRadius: 8,
          callbacks: { label: item => `${item.parsed.y}%` },
        },
      },
      scales: {
        x: { grid:{display:false}, border:{display:false}, ticks:{color:'#718096', font:{size:12}} },
        y: {
          beginAtZero: true, max: 100,
          grid:{color:'rgba(0,0,0,0.05)'}, border:{display:false},
          ticks: { maxTicksLimit:5, color:'#718096', font:{size:11}, callback: v=>`${v}%` },
        },
      },
    },
  });
}

/* ==========================================================
   FEATURE 8 — RISK DEFINITIONS MODAL
   ========================================================== */
function openModal()  { document.getElementById('riskModal')?.classList.remove('hidden'); }
function closeModal() { document.getElementById('riskModal')?.classList.add('hidden'); }

document.getElementById('riskInfoBtn')?.addEventListener('click', openModal);
document.getElementById('riskModalClose')?.addEventListener('click', closeModal);
document.getElementById('riskModal')?.addEventListener('click', e => {
  if (e.target === e.currentTarget) closeModal();   // click outside modal
});
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') closeModal();
});

/* ==========================================================
   FEATURE 9 — EXPORT: PRINT, EXCEL DOWNLOAD, HTML DOWNLOAD
   ========================================================== */

/* --- Print / Save as PDF --------------------------------- */
document.getElementById('printBtn').addEventListener('click', () => {
  if (!latestResult) { toast('Run an assessment first.', 'error'); return; }
  window.print();
});

/* --- Download Excel workbook ----------------------------- */
document.getElementById('downloadExcelBtn').addEventListener('click', async () => {
  if (!latestResult) { toast('Run an assessment first.', 'error'); return; }
  const r = latestResult;
  try {
    const response = await fetch(`${API}/api/export-excel`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        currency: r.currency,
        amount: r.amount ?? r.amount_currency ?? r.amount_usd,
        horizon: r.horizon_days,
      }),
    });
    if (!response.ok) throw new Error(await response.text());
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    triggerDownload(url, `fxguard-result-${r.analysis_date}.xlsx`);
    setTimeout(() => URL.revokeObjectURL(url), 5000);
    toast('Excel workbook downloaded.', 'success');
  } catch (error) {
    console.error('Excel export failed:', error);
    toast('Could not create the Excel workbook. Please try again.', 'error');
  }
});

/* --- Download HTML report -------------------------------- */
document.getElementById('downloadHtmlBtn').addEventListener('click', () => {
  if (!latestResult) { toast('Run an assessment first.', 'error'); return; }
  const r    = latestResult;
  const date = new Date().toLocaleDateString('en-GB', { day:'2-digit', month:'long', year:'numeric' });

  const riskColor = { Low: '#0ca678', Medium: '#f59f00', High: '#fa5252' }[r.risk_level] ?? '#3b5bdb';
  const riskBg    = { Low: '#e6fcf5', Medium: '#fff9db', High: '#fff5f5'  }[r.risk_level] ?? '#eff4ff';

  const recsHtml = (r.recommendations ?? [])
    .map(rec => `<li style="margin-bottom:6px">${rec}</li>`).join('');

  const driversHtml = Object.entries(r.key_drivers ?? {})
    .map(([k, v]) => `
      <tr>
        <td style="padding:8px 12px;border-bottom:1px solid #e3e7ed;color:#718096">
          ${DRIVER_LABELS[k] ?? k.replaceAll('_', ' ')}
        </td>
        <td style="padding:8px 12px;border-bottom:1px solid #e3e7ed;font-family:monospace;text-align:right">
          ${formatDriverValue(k, v, r.currency)}
        </td>
      </tr>`).join('');

  const probsHtml = Object.entries(r.class_probabilities ?? {})
    .map(([k, v]) => {
      const pctVal = (v * 100).toFixed(1);
      const c = { Low:'#0ca678', Medium:'#f59f00', High:'#fa5252' }[k] ?? '#3b5bdb';
      return `
        <div style="margin-bottom:10px">
          <div style="display:flex;justify-content:space-between;margin-bottom:4px">
            <span style="font-weight:600;color:#1a1f2e">${k}</span>
            <span style="font-family:monospace;color:#4a5568">${pctVal}%</span>
          </div>
          <div style="height:8px;background:#e9ecef;border-radius:4px;overflow:hidden">
            <div style="height:100%;width:${pctVal}%;background:${c};border-radius:4px"></div>
          </div>
        </div>`;
    }).join('');

  const html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>FXGuard AI — Risk Assessment Report</title>
  <style>
    *{box-sizing:border-box;margin:0;padding:0}
    body{font-family:'Segoe UI',Inter,system-ui,sans-serif;font-size:14px;color:#1a1f2e;background:#f4f6f9;padding:32px}
    .page{max-width:800px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 16px rgba(0,0,0,.08)}
    .header{background:#1a1f2e;padding:28px 32px;color:#fff}
    .header h1{font-size:22px;font-weight:700;letter-spacing:-.02em}
    .header p{color:#a0aec0;margin-top:4px;font-size:13px}
    .body{padding:32px}
    .section{margin-bottom:28px}
    .section-title{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:#718096;margin-bottom:12px}
    .cards{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:28px}
    .card{border:1px solid #e3e7ed;border-radius:10px;padding:16px}
    .card-label{font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:#718096;margin-bottom:6px}
    .card-value{font-size:20px;font-weight:700;letter-spacing:-.02em}
    .card-sub{font-size:11.5px;color:#718096;margin-top:4px}
    .risk-card{background:${riskBg};border-color:${riskColor}40}
    .risk-value{color:${riskColor}}
    table{width:100%;border-collapse:collapse}
    .rec-list{padding-left:16px}
    .rec-list li{margin-bottom:6px;color:#4a5568;line-height:1.55}
    .footer{background:#f8f9fa;border-top:1px solid #e3e7ed;padding:16px 32px;font-size:11.5px;color:#718096;line-height:1.6}
    @media print{body{background:#fff;padding:0}.page{box-shadow:none;border-radius:0}}
  </style>
</head>
<body>
<div class="page">
  <div class="header">
    <h1>FXGuard AI — Risk Assessment Report</h1>
    <p>Generated ${date} &nbsp;·&nbsp; ${r.currency} / RWF &nbsp;·&nbsp; ${r.horizon_days}-day outlook</p>
  </div>
  <div class="body">
    <div class="cards">
      <div class="card risk-card">
        <div class="card-label">Risk level</div>
        <div class="card-value risk-value">${r.risk_level}</div>
        <div class="card-sub">${r.horizon_days}-day outlook</div>
      </div>
      <div class="card">
        <div class="card-label">Cost at current rate</div>
        <div class="card-value" style="font-family:monospace;font-size:17px">RWF ${fmt(r.current_cost_rwf)}</div>
        <div class="card-sub">At ${fmtRate(r.current_rate, r.currency)} RWF/${r.currency}</div>
      </div>
      <div class="card">
        <div class="card-label">Possible added cost</div>
        <div class="card-value" style="font-family:monospace;font-size:17px;color:#fa5252">RWF ${fmt(r.possible_extra_cost_rwf)}</div>
        <div class="card-sub">A cautious estimate if the rate changes</div>
      </div>
    </div>

    <div class="section">
      <div class="section-title">Payment details</div>
      <table>
        <tr><td style="padding:8px 12px;border-bottom:1px solid #e3e7ed;color:#718096;width:200px">Amount</td>
            <td style="padding:8px 12px;border-bottom:1px solid #e3e7ed;font-family:monospace">${r.currency_symbol ?? r.currency} ${fmt(r.amount ?? r.amount_currency ?? r.amount_usd)} ${r.currency}</td></tr>
        <tr><td style="padding:8px 12px;border-bottom:1px solid #e3e7ed;color:#718096">Current rate</td>
            <td style="padding:8px 12px;border-bottom:1px solid #e3e7ed;font-family:monospace">${fmtRate(r.current_rate, r.currency)} RWF / ${r.currency}</td></tr>
        <tr><td style="padding:8px 12px;border-bottom:1px solid #e3e7ed;color:#718096">Safety buffer</td>
            <td style="padding:8px 12px;border-bottom:1px solid #e3e7ed;font-family:monospace;color:#b37400">RWF ${fmt(r.suggested_margin_buffer_rwf)}</td></tr>
        <tr><td style="padding:8px 12px;color:#718096">Strength of this result</td>
            <td style="padding:8px 12px;font-family:monospace">${pct(r.confidence_score ?? r.confidence ?? 0)}</td></tr>
      </table>
    </div>

    <div class="section">
      <div class="section-title">Recommendations</div>
      <ul class="rec-list">${recsHtml}</ul>
    </div>

    <div class="section">
      <div class="section-title">How strongly each risk level is supported</div>
      ${probsHtml}
    </div>

    <div class="section">
      <div class="section-title">What this result is based on</div>
      <table>${driversHtml}</table>
    </div>
  </div>
  <div class="footer">
    ${r.disclaimer ?? 'FXGuard AI provides decision support only. It is not guaranteed financial, forex trading, or professional investment advice.'}
  </div>
</div>
</body>
</html>`;

  const blob2 = new Blob([html], { type: 'text/html;charset=utf-8;' });
  const url2  = URL.createObjectURL(blob2);
  triggerDownload(url2, `fxguard-report-${r.analysis_date}.html`);
  setTimeout(() => URL.revokeObjectURL(url2), 5000);
  toast('Report downloaded — open in any browser.', 'success');
});

/* --- Helper: trigger a browser file download ------------- */
function triggerDownload(dataUrl, filename) {
  const a = document.createElement('a');
  a.href     = dataUrl;
  a.download = filename;
  a.style.display = 'none';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

/* ==========================================================
   INIT
   ========================================================== */
function updateCurrencyCopy(currency) {
  const info = currencyCatalog[currency];
  if (!info) return;
  setText('pairEyebrow', `${currency} / RWF · Decision support`);
  setText('chartTitle', `${currency} / RWF — rate trend`);
  setText('chartDescription', `BNR reference rates. Higher values mean each ${currency} costs more RWF.`);
  setText('quickAmountLabel', `Invoice amount (${currency})`);
  setText('quickAmountPrefix', info.symbol);
  setText('amountLabel', `Invoice amount (${currency})`);
  setText('amountPrefix', info.symbol);
  setText('assessmentPair', `${currency} / RWF`);
  setText('convCurrencyPrefix', currency);
  const chart = document.getElementById('historyChart');
  if (chart) chart.setAttribute('aria-label', `${currency}/RWF reference-rate chart`);
  const activeSelect = document.getElementById('activeCurrency');
  const assessmentSelect = document.getElementById('currency');
  if (activeSelect) activeSelect.value = currency;
  if (assessmentSelect) assessmentSelect.value = currency;
}

async function selectCurrency(currency) {
  if (!currencyCatalog[currency]) return;
  selectedCurrency = currency;
  localStorage.setItem('fxguard_currency', currency);
  latestRate = null;
  updateCurrencyCopy(currency);
  setText('badgeRate', '—');
  setText('badgeDate', 'Loading…');
  setText('assessmentSource', 'Loading…');
  setText('kpiModel7', 'Loading…');
  setText('kpiModel14', 'Loading…');

  try {
    const [latestResponse, freshnessResponse] = await Promise.all([
      fetch(`${API}/api/latest-rate?currency=${currency}`),
      fetch(`${API}/api/data-freshness?currency=${currency}`),
    ]);
    if (!latestResponse.ok || !freshnessResponse.ok) throw new Error('Currency data request failed');
    const [latest, freshness] = await Promise.all([latestResponse.json(), freshnessResponse.json()]);
    if (currency !== selectedCurrency) return;

    populateRateUI(latest);
    populateModelUI(modelMetadata, currency);
    setStatus(freshness);
    showStaleBanner(freshness);

    /* Badge freshness label */
    const ageLabel = {
      fresh: `Fresh · ${freshness.days_since_latest_rate}d old`,
      aging: `Aging · ${freshness.days_since_latest_rate}d old`,
      stale: `Stale · ${freshness.days_since_latest_rate}d old`,
    }[freshness.status] ?? freshness.latest_rate_date;
    setText('badgeDate', ageLabel);

    await drawHistory(currentDays);
  } catch (err) {
    console.error('Currency load failed:', err);
    toast(`Could not load ${currency}/RWF data.`, 'error');
  }
}

document.getElementById('activeCurrency')?.addEventListener('change', event => {
  selectCurrency(event.target.value);
});
document.getElementById('currency')?.addEventListener('change', event => {
  selectCurrency(event.target.value);
});

function installCurrencyCatalog(payload) {
  const supported = Array.isArray(payload?.currencies) ? payload.currencies : [];
  if (supported.length) {
    currencyCatalog = Object.fromEntries(supported.map(item => [
      item.code,
      {
        name: item.name,
        symbol: item.symbol,
        decimals: item.display_decimals,
        pair: item.pair,
      },
    ]));
  }

  for (const selectId of ['activeCurrency', 'currency']) {
    const select = document.getElementById(selectId);
    if (!select) continue;
    const options = Object.entries(currencyCatalog).map(([code, info]) => {
      const option = document.createElement('option');
      option.value = code;
      option.textContent = `${code} — ${info.name}`;
      return option;
    });
    select.replaceChildren(...options);
  }

  const codes = Object.keys(currencyCatalog);
  setText('kpiCoverageValue', `${codes.length} ${codes.length === 1 ? 'currency' : 'currencies'}`);
  setText('kpiCoverageSub', `${codes.join(', ')} against RWF`);
}

async function init() {
  try {
    const [currencyResponse, metadataResponse] = await Promise.all([
      fetch(`${API}/api/currencies`),
      fetch(`${API}/api/model-metadata`),
    ]);
    if (!currencyResponse.ok) throw new Error('Supported currencies request failed');
    if (!metadataResponse.ok) throw new Error('Model metadata request failed');
    const [currencyPayload, metadataPayload] = await Promise.all([
      currencyResponse.json(),
      metadataResponse.json(),
    ]);
    installCurrencyCatalog(currencyPayload);
    modelMetadata = metadataPayload;
    renderRecentChecks();
    const savedCurrency = localStorage.getItem('fxguard_currency');
    const initialCurrency = currencyCatalog[savedCurrency]
      ? savedCurrency
      : Object.keys(currencyCatalog)[0];
    await selectCurrency(initialCurrency);
  } catch (err) {
    console.error('Init failed:', err);
    toast('Could not load data — is the backend running?', 'error');
  }
}

init();
