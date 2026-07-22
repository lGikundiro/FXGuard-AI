/* ==========================================================
   FXGuard AI — app.js  v3
   Features: navigation, loading states, results-persist,
   chart timeframe, risk modal, RWF converter,
   recent-checks localStorage, stale banner, print export
   ========================================================== */
'use strict';

const configuredApi = String(window.FXGUARD_API_URL ?? '').trim();
const API = configuredApi || window.location.origin;

/* --- State ------------------------------------------------ */
let selectedMainHorizon = 7;
let selectedCurrency    = 'USD';
let latestResult        = null;
let latestRate          = null;   // kept for converter
let historyChart        = null;
let currentDays         = 180;   // active chart range
let chartLibraryRequested = false;
let activeScreen        = 'dashboard';

const FALLBACK_CURRENCIES = {
  USD: { name: 'US Dollar', symbol: '$', decimals: 2 },
  EUR: { name: 'Euro', symbol: '€', decimals: 2 },
  KES: { name: 'Kenyan Shilling', symbol: 'KSh', decimals: 4 },
};
let currencyCatalog = { ...FALLBACK_CURRENCIES };

/* --- Page titles ------------------------------------------ */
const PAGE_TITLES = {
  dashboard:  'Dashboard',
  assessment: 'Run payment check',
  results:    'Results',
  decision:   'Payment tips',
  feedback:   'Share feedback',
};

/* ==========================================================
   NAVIGATION
   ========================================================== */
function showScreen(id) {
  const target = document.getElementById(id);
  if (!target || id === activeScreen) return;

  activeScreen = id;

  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(b => {
    const isActive = b.dataset.screen === id;
    b.classList.toggle('active', isActive);
    b.setAttribute('aria-current', isActive ? 'page' : 'false');
  });

  target.classList.add('active');

  const titleEl = document.getElementById('pageTitle');
  if (titleEl) titleEl.textContent = PAGE_TITLES[id] ?? id;
  window.scrollTo({ top: 0, behavior: 'smooth' });

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

  banner.classList.remove('hidden');
  banner.classList.add('stale');
  text.textContent = `Latest imported ${freshness.pair} BNR rate: ${date} (${days} days ago). Checks use this date until newer rates are imported.`;
  document.querySelector('.main-content')?.classList.add('has-banner');

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
  const pill = document.getElementById('sidebarStatus');
  if (!dot || !text || !pill) return;

  if (!freshness) {
    dot.className = 'status-dot';
    text.textContent = 'Rate date unavailable';
    pill.title = 'The latest BNR rate date could not be checked.';
    return;
  }

  const isCurrent = freshness.status === 'fresh';
  const parsedDate = new Date(`${freshness.latest_rate_date}T00:00:00`);
  const dateLabel = Number.isNaN(parsedDate.getTime())
    ? freshness.latest_rate_date
    : new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short' }).format(parsedDate);
  dot.className = `status-dot ${isCurrent ? 'current' : 'needs-update'}`;
  text.textContent = `${isCurrent ? 'Recent BNR rate' : 'Older BNR rate'} · ${dateLabel}`;
  pill.title = `Latest imported BNR rate: ${freshness.latest_rate_date}`;
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
  setText('assessmentSource', latest.source ?? 'BNR exchange rates');
  updateConverter();
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
  grad.addColorStop(0, 'rgba(245,202,82,0.24)');
  grad.addColorStop(1, 'rgba(255,255,255,0.01)');

  historyChart = new Chart(canvas, {
    type: 'line',
    data: {
      labels: points.map(p => p.date),
      datasets: [{
        label: `${currency}/RWF reference rate`,
        data: values,
        tension: 0.3,
        borderColor: '#f5ca52',
        backgroundColor: grad,
        fill: true,
        pointRadius: points.map((_, i) => i === points.length - 1 ? 4 : 0),
        pointHoverRadius: 5,
        pointBackgroundColor: '#fff2b6',
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
          backgroundColor: '#0d2038',
          titleColor: 'rgba(255,255,255,.68)',
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
            color: 'rgba(255,255,255,.58)',
            font: { size: 11, family: "'Manrope', sans-serif" },
            callback(val) {
              const label = this.getLabelForValue(val);
              return label ? label.slice(days <= 365 ? 5 : 0) : '';
            },
          },
        },
        y: {
          min: rawMin - rawRange * 0.08,
          max: rawMax + rawRange * 0.08,
          grid: { color: 'rgba(255,255,255,0.08)' },
          border: { display: false },
          ticks: {
            maxTicksLimit: 5,
            color: 'rgba(255,255,255,.58)',
            font: { size: 11, family: "'Manrope', sans-serif" },
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

function loadChartLibraryWhenIdle() {
  if (chartLibraryRequested || typeof Chart !== 'undefined') return;
  chartLibraryRequested = true;

  const load = () => {
    const script = document.createElement('script');
    script.src = 'https://cdn.jsdelivr.net/npm/chart.js';
    script.async = true;
    script.onload = () => drawHistory(currentDays).catch(error => {
      console.error('Chart refresh failed:', error);
    });
    script.onerror = () => {
      console.info('Chart library unavailable; using the built-in chart.');
    };
    document.head.appendChild(script);
  };

  if ('requestIdleCallback' in window) {
    window.requestIdleCallback(load, { timeout: 2500 });
  } else {
    window.setTimeout(load, 1200);
  }
}

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
  ctx.fillStyle = '#0d2038'; ctx.fillRect(0,0,W,H);
  ctx.strokeStyle = 'rgba(255,255,255,0.08)'; ctx.lineWidth = 1;
  for (let i=0;i<=4;i++) {
    const y = pad.t+(cH/4)*i;
    ctx.beginPath(); ctx.moveTo(pad.l,y); ctx.lineTo(W-pad.r,y); ctx.stroke();
    ctx.fillStyle='rgba(255,255,255,.58)'; ctx.font='10px Manrope,sans-serif';
    ctx.textAlign='right'; ctx.fillText(fmtRate(vMax-(vR/4)*i), pad.l-4, y+3);
  }
  const grad = ctx.createLinearGradient(0,pad.t,0,H-pad.b);
  grad.addColorStop(0,'rgba(245,202,82,0.24)'); grad.addColorStop(1,'rgba(255,255,255,0)');
  ctx.beginPath();
  points.forEach((p,i) => { const x=xOf(i),y=yOf(p.mid_rate); i===0?ctx.moveTo(x,y):ctx.lineTo(x,y); });
  ctx.lineTo(xOf(points.length-1),H-pad.b); ctx.lineTo(xOf(0),H-pad.b);
  ctx.closePath(); ctx.fillStyle=grad; ctx.fill();
  ctx.beginPath();
  points.forEach((p,i) => { const x=xOf(i),y=yOf(p.mid_rate); i===0?ctx.moveTo(x,y):ctx.lineTo(x,y); });
  ctx.strokeStyle='#f5ca52'; ctx.lineWidth=2; ctx.stroke();
  const lx=xOf(points.length-1), ly=yOf(vals[vals.length-1]);
  ctx.beginPath(); ctx.arc(lx,ly,4,0,Math.PI*2); ctx.fillStyle='#fff2b6'; ctx.fill();
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

function formatInvoiceAmount(check) {
  const currency = String(check.currency ?? 'USD').toUpperCase();
  const amount = new Intl.NumberFormat('en-RW', {
    maximumFractionDigits: 2,
  }).format(Number(check.amount ?? 0));
  return `${currency} ${amount}`;
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
  const clearButton = document.getElementById('clearHistory');
  if (!section || !tbody) return;

  section.classList.remove('hidden');
  if (clearButton) clearButton.disabled = checks.length === 0;

  if (!checks.length) {
    tbody.innerHTML = `
      <tr class="recent-checks-empty">
        <td colspan="7">
          <p class="recent-empty-title">No payment checks yet</p>
          <p class="recent-empty-copy">Run a payment check and your result will appear here.</p>
        </td>
      </tr>`;
    return;
  }

  tbody.innerHTML = checks.map((c, i) => `
    <tr class="recent-check-row" data-reopen="${i}" tabindex="0"
      aria-label="Open ${c.risk} risk payment check from ${formatCheckTime(c)}">
      <td><time class="check-date">${formatCheckTime(c)}</time></td>
      <td class="mono money-col">${formatInvoiceAmount(c)}</td>
      <td>${c.horizon} days</td>
      <td><span class="risk-pill ${c.risk}">${c.risk}</span></td>
      <td class="mono money-col">RWF ${fmt(c.cost)}</td>
      <td class="money-col extra-cost-col">
        <span class="extra-cost-badge" title="Estimated extra cost">
          <span class="extra-cost-arrow" aria-hidden="true">↑</span>
          <span>RWF ${fmt(c.extra)}</span>
        </span>
      </td>
      <td class="td-action">
        <span class="row-link" aria-hidden="true">View →</span>
      </td>
    </tr>`
  ).join('');

  function openCheck(row) {
      const idx   = Number(row.dataset.reopen);
      const check = checks[idx];

      if (check.full) {
        latestResult = check.full;
        renderResult(latestResult);
        showScreen('results');
        toast(`Showing check from ${formatCheckTime(check)}.`);
      } else {
        toast(`This old check has no full result. Please run it again.`, 'error');
      }
  }

  tbody.querySelectorAll('.recent-check-row').forEach(row => {
    row.addEventListener('click', () => openCheck(row));
    row.addEventListener('keydown', event => {
      if (event.key !== 'Enter' && event.key !== ' ') return;
      event.preventDefault();
      openCheck(row);
    });
  });
}

document.getElementById('clearHistory')?.addEventListener('click', () => {
  localStorage.removeItem(HISTORY_KEY);
  renderRecentChecks();
  toast('Recent checks cleared.');
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
    toast('Enter an invoice amount above zero.', 'error');
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
    toast('Cannot connect to the service. Please try again.', 'error');
    setLoading(triggeredBy, false);
    return;
  }

  setLoading(triggeredBy, false);

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    toast(err.detail ?? 'Payment check failed. Please try again.', 'error');
    return;
  }

  latestResult = await res.json();
  saveCheck(latestResult);
  renderResult(latestResult);
  showScreen('results');
}

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

const RESULT_DRIVER_KEYS = new Set([
  'return_7d', 'return_14d', 'volatility_7d',
  'momentum_7d', 'depreciation_days_7d',
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
  Low: 'The rate has not changed much recently.',
  Medium: 'The rate may make this payment more expensive.',
  High: 'The payment could cost much more if the rate changes.',
};

function getDecisionSupportConsiderations(result) {
  if (Array.isArray(result.considerations) && result.considerations.length) {
    return result.considerations;
  }

  const currency = result.currency ?? 'foreign currency';
  const pair = result.currency ? `${result.currency}/RWF` : 'exchange-rate';
  if (result.risk_level === 'High') {
    return [
      `Recent ${pair} changes point to a higher chance of added cost during this check period.`,
      `The estimated extra cost shows the possible effect of a more expensive ${currency} under the planning scenario.`,
      'Payment timing, available cash and supplier terms remain business factors to weigh.',
    ];
  }
  if (result.risk_level === 'Medium') {
    return [
      `Recent ${pair} changes point to a moderate chance of added cost during this check period.`,
      'The estimated extra cost is a planning scenario, not a guaranteed future cost.',
      'Payment timing, available cash and supplier terms remain business factors to weigh.',
    ];
  }
  return [
    `Recent ${pair} rates have been fairly stable compared with the model's past data.`,
    'A Low result does not mean the rate will stay unchanged.',
    'The current cost and estimated extra cost can be weighed alongside cash needs and supplier terms.',
  ];
}

function renderResult(r) {
  hide('emptyResult');    show('resultContent');
  hide('emptyDecision');  show('decisionContent');
  show('exportBar');

  /* Risk card */
  const riskEl = document.getElementById('riskLevel');
  if (riskEl) {
    riskEl.textContent = r.risk_level;
    riskEl.className   = 'result-risk-value';
  }
  const resultHero = document.getElementById('resultHero');
  if (resultHero) resultHero.className = `result-hero level-${r.risk_level}`;

  setText('riskMeaning',     RISK_MEANINGS[r.risk_level] ?? 'Recent rate information is shown below.');
  setText('currentCost',     `RWF ${fmt(r.current_cost_rwf)}`);
  setText('currentRateText', `At today's rate of ${fmtRate(r.current_rate, r.currency)} RWF per ${r.currency}`);
  setText('extraCost',       `RWF ${fmt(r.possible_extra_cost_rwf)}`);

  /* Key drivers */
  const driversEl = document.getElementById('drivers');
  if (driversEl) {
    driversEl.innerHTML = Object.entries(r.key_drivers ?? {})
      .filter(([key]) => RESULT_DRIVER_KEYS.has(key))
      .map(([k, v]) =>
        `<div class="driver-row">
           <span>${DRIVER_LABELS[k] ?? k.replaceAll('_',' ')}</span>
           <strong>${formatDriverValue(k, v, r.currency)}</strong>
         </div>`
      ).join('');
  }

  /* Decision-support considerations */
  const recHtml = getDecisionSupportConsiderations(r)
    .map(x => `<div class="rec-item ${r.risk_level}">${x}</div>`)
    .join('');
  setHTML('resultRecommendations', recHtml);
  setHTML('decisionRecommendations', recHtml);

  /* Scenario table */
  const amount = r.amount ?? r.amount_currency ?? r.amount_usd;
  const symbol = r.currency_symbol ?? currencyCatalog[r.currency]?.symbol ?? r.currency;
  setHTML('scenarioRows', `
    <tr><td>Payment amount</td>     <td>${symbol} ${fmt(amount)} ${r.currency}</td></tr>
    <tr><td>Current rate</td>        <td>${fmtRate(r.current_rate, r.currency)} RWF / ${r.currency}</td></tr>
    <tr><td>Cost at current rate</td><td>RWF ${fmt(r.current_cost_rwf)}</td></tr>
    <tr><td>Possible extra cost</td>
        <td style="color:var(--red-500)">RWF ${fmt(r.possible_extra_cost_rwf)}</td></tr>
    <tr><td>Planning buffer estimate</td>
        <td style="color:var(--amber-700)">RWF ${fmt(r.planning_buffer_estimate_rwf ?? r.suggested_margin_buffer_rwf)}</td></tr>
  `);
  setText('disclaimer',
    `This estimate uses the current BNR rate for ${r.currency}/RWF and a cautious estimate of possible extra cost. ` +
    'Use this estimate for planning only. The future rate may be different.'
  );
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
  if (!latestResult) { toast('Run a payment check first.', 'error'); return; }
  window.print();
});

/* --- Download Excel workbook ----------------------------- */
document.getElementById('downloadExcelBtn').addEventListener('click', async () => {
  if (!latestResult) { toast('Run a payment check first.', 'error'); return; }
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
    toast('Excel file downloaded.', 'success');
  } catch (error) {
    console.error('Excel export failed:', error);
    toast('Could not create the Excel workbook. Please try again.', 'error');
  }
});

/* --- Download HTML report -------------------------------- */
document.getElementById('downloadHtmlBtn').addEventListener('click', () => {
  if (!latestResult) { toast('Run a payment check first.', 'error'); return; }
  const r    = latestResult;
  const date = new Date().toLocaleDateString('en-GB', { day:'2-digit', month:'long', year:'numeric' });

  const riskColor = { Low: '#0ca678', Medium: '#f59f00', High: '#fa5252' }[r.risk_level] ?? '#3b5bdb';
  const riskBg    = { Low: '#e6fcf5', Medium: '#fff9db', High: '#fff5f5'  }[r.risk_level] ?? '#eff4ff';

  const recsHtml = getDecisionSupportConsiderations(r)
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
  <title>FXGuard AI — Payment Check Report</title>
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
    <h1>FXGuard AI — Payment Check Report</h1>
    <p>Created ${date} &nbsp;·&nbsp; ${r.currency} / RWF &nbsp;·&nbsp; ${r.horizon_days}-day check</p>
  </div>
  <div class="body">
    <div class="cards">
      <div class="card risk-card">
        <div class="card-label">Risk level</div>
        <div class="card-value risk-value">${r.risk_level}</div>
        <div class="card-sub">${r.horizon_days}-day check</div>
      </div>
      <div class="card">
        <div class="card-label">Cost at current rate</div>
        <div class="card-value" style="font-family:monospace;font-size:17px">RWF ${fmt(r.current_cost_rwf)}</div>
        <div class="card-sub">At ${fmtRate(r.current_rate, r.currency)} RWF/${r.currency}</div>
      </div>
      <div class="card">
        <div class="card-label">Possible extra cost</div>
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
        <tr><td style="padding:8px 12px;border-bottom:1px solid #e3e7ed;color:#718096">Planning buffer estimate</td>
            <td style="padding:8px 12px;border-bottom:1px solid #e3e7ed;font-family:monospace;color:#b37400">RWF ${fmt(r.planning_buffer_estimate_rwf ?? r.suggested_margin_buffer_rwf)}</td></tr>
        <tr><td style="padding:8px 12px;color:#718096">How sure this check is</td>
            <td style="padding:8px 12px;font-family:monospace">${pct(r.confidence_score ?? r.confidence ?? 0)}</td></tr>
      </table>
    </div>

    <div class="section">
      <div class="section-title">Payment tips</div>
      <ul class="rec-list">${recsHtml}</ul>
    </div>

    <div class="section">
      <div class="section-title">How likely each risk level is</div>
      ${probsHtml}
    </div>

    <div class="section">
      <div class="section-title">What this result is based on</div>
      <table>${driversHtml}</table>
    </div>
  </div>
  <div class="footer">
    ${r.disclaimer ?? 'This check is decision support only. It shows estimates and does not recommend when or how to pay.'}
  </div>
</div>
</body>
</html>`;

  const blob2 = new Blob([html], { type: 'text/html;charset=utf-8;' });
  const url2  = URL.createObjectURL(blob2);
  triggerDownload(url2, `fxguard-report-${r.analysis_date}.html`);
  setTimeout(() => URL.revokeObjectURL(url2), 5000);
  toast('Report downloaded. Open it in any browser.', 'success');
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
  setText('pairEyebrow', `${currency} / RWF · Plan supplier payments`);
  setText('chartTitle', `${currency} / RWF — rate trend`);
  setText('chartDescription', `If this number goes up, you need more RWF to buy 1 ${currency}.`);
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
  const historyRequest = drawHistory(currentDays).catch(error => {
    console.error('Rate history load failed:', error);
  });

  try {
    const [latestResponse, freshnessResponse] = await Promise.all([
      fetch(`${API}/api/latest-rate?currency=${currency}`),
      fetch(`${API}/api/data-freshness?currency=${currency}`),
    ]);
    if (!latestResponse.ok || !freshnessResponse.ok) throw new Error('Currency data request failed');
    const [latest, freshness] = await Promise.all([latestResponse.json(), freshnessResponse.json()]);
    if (currency !== selectedCurrency) return;

    populateRateUI(latest);
    setStatus(freshness);
    showStaleBanner(freshness);

    /* Badge freshness label */
    const ageLabel = {
      fresh: `Updated · ${freshness.days_since_latest_rate} days ago`,
      aging: `Last update · ${freshness.days_since_latest_rate} days ago`,
      stale: `Old rate · ${freshness.days_since_latest_rate} days ago`,
    }[freshness.status] ?? freshness.latest_rate_date;
    setText('badgeDate', ageLabel);
  } catch (err) {
    console.error('Currency load failed:', err);
    setStatus(null);
    setText('badgeDate', 'Rate date unavailable');
    toast(`Could not load ${currency}/RWF rates. Please try again.`, 'error');
  }

  await historyRequest;
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
  updateCurrencyCopy(selectedCurrency);
}

async function init() {
  renderRecentChecks();
  const savedCurrency = localStorage.getItem('fxguard_currency');
  const initialCurrency = currencyCatalog[savedCurrency]
    ? savedCurrency
    : Object.keys(currencyCatalog)[0];

  const currencyDataRequest = selectCurrency(initialCurrency);
  const catalogRequest = (async () => {
    try {
      const currencyResponse = await fetch(`${API}/api/currencies`);
      if (!currencyResponse.ok) throw new Error('Supported currencies request failed');
      const currencyPayload = await currencyResponse.json();
      installCurrencyCatalog(currencyPayload);
    } catch (err) {
      console.info('Using the built-in currency list:', err);
    }
  })();

  await Promise.allSettled([currencyDataRequest, catalogRequest]);
  loadChartLibraryWhenIdle();
}

init();
