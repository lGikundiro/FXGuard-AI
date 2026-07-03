const API = window.location.origin;
    let selectedHorizon = 7;
    let selectedMainHorizon = 7;
    let latestResult = null;
    let historyChart = null;
    let probChart = null;

    const titles = {
      dashboard: [
        'Dashboard',
        'A calm overview of the latest rate, the recent trend, and the fastest path to a payment decision.'
      ],
      assessment: [
        'Payment check',
        'Enter a payment amount and choose how far ahead you want to look.'
      ],
      results: [
        'Decision view',
        'See the outcome, why it happened, and what it means for the payment.'
      ],
      decision: [
        'Action plan',
        'Turn the model result into a concrete next step.'
      ],
      feedback: [
        'Participant feedback',
        'Collecting usability feedback from test participants.'
      ]
    };

    document.querySelectorAll('.nav button').forEach(btn => btn.addEventListener('click', () => showScreen(btn.dataset.screen)));
    document.querySelectorAll('[data-go-screen]').forEach(btn => btn.addEventListener('click', () => showScreen(btn.dataset.goScreen)));
    document.querySelectorAll('[data-horizon]').forEach(btn => btn.addEventListener('click', () => {
      selectedHorizon = Number(btn.dataset.horizon);
      document.querySelectorAll('[data-horizon]').forEach(b => b.classList.remove('selected'));
      btn.classList.add('selected');
    }));
    document.querySelectorAll('[data-horizon-main]').forEach(btn => btn.addEventListener('click', () => {
      selectedMainHorizon = Number(btn.dataset.horizonMain);
      document.querySelectorAll('[data-horizon-main]').forEach(b => b.classList.remove('selected'));
      btn.classList.add('selected');
    }));

    document.getElementById('heroCheckBtn').addEventListener('click', () => showScreen('assessment'));

    function showScreen(id) {
      document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
      const screen = document.getElementById(id);
      if (screen) screen.classList.add('active');
      document.querySelectorAll('.nav button').forEach(b => b.classList.toggle('active', b.dataset.screen === id));
      document.getElementById('pageTitle').textContent = titles[id][0];
      document.getElementById('pageSubtitle').textContent = titles[id][1];
      document.getElementById('pageSubtitleEmphasis').style.display = id === 'dashboard' ? 'block' : 'none';
    }

    function fmt(num) {
      return new Intl.NumberFormat('en-RW', { maximumFractionDigits: 0 }).format(num);
    }
    function fmtRate(num) {
      return new Intl.NumberFormat('en-RW', { maximumFractionDigits: 3 }).format(num);
    }
    function toast(msg) {
      const t = document.getElementById('toast');
      t.textContent = msg;
      t.style.display = 'block';
      setTimeout(() => t.style.display = 'none', 3200);
    }

    async function init() {
      const latest = await fetch(`${API}/api/latest-rate`).then(r => r.json());
      document.getElementById('latestRate').textContent = fmtRate(latest.mid_rate);
      document.getElementById('latestDate').textContent = `Latest update: ${latest.date}`;
      document.getElementById('latestRateStat').textContent = fmtRate(latest.mid_rate);
      document.getElementById('latestDateStat').textContent = `Latest update: ${latest.date}`;
      document.getElementById('dataBadge').textContent = `Recent rate data • ${latest.date}`;

      const freshness = await fetch(`${API}/api/data-freshness`).then(r => r.json());
      const freshnessLabel = freshness.status === 'fresh' ? 'Fresh' : freshness.status === 'aging' ? 'Needs refresh soon' : 'Stale';
      document.getElementById('dataBadge').textContent = `${freshnessLabel} data • ${freshness.latest_rate_date} • ${freshness.days_since_latest_rate} days old`;

      const metadata = await fetch(`${API}/api/model-metadata`).then(r => r.json());
      document.getElementById('model7').textContent = metadata?.models?.['7d']?.best_model ? 'Ready' : 'Loaded';
      document.getElementById('model14').textContent = metadata?.models?.['14d']?.best_model ? 'Ready' : 'Loaded';
      document.getElementById('model7Stat').textContent = metadata?.models?.['7d']?.best_model ? 'Ready' : 'Loaded';
      document.getElementById('model14Stat').textContent = metadata?.models?.['14d']?.best_model ? 'Ready' : 'Loaded';

      await drawHistory();
    }

    async function drawHistory() {
      const data = await fetch(`${API}/api/history?days=180`).then(r => r.json());
      const ctx = document.getElementById('historyChart');
      if (historyChart) historyChart.destroy();
      historyChart = new Chart(ctx, {
        type: 'line',
        data: {
          labels: data.points.map(p => p.date),
          datasets: [{
            label: 'USD - RWF',
            data: data.points.map(p => p.mid_rate),
            tension: .28,
            borderColor: '#2457d6',
            backgroundColor: 'rgba(36,87,214,.10)',
            fill: true,
            pointRadius: 0,
            borderWidth: 2.5
          }]
        },
        options: {
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            x: { ticks: { maxTicksLimit: 8, color: '#728196' }, grid: { display: false } },
            y: { ticks: { color: '#728196' }, grid: { color: 'rgba(20,32,51,0.08)' } }
          }
        }
      });
    }

    async function runAssessment(amount, horizon) {
      const res = await fetch(`${API}/api/predict-risk`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          currency: 'USD',
          amount: Number(amount),
          horizon: Number(horizon),
          margin_percent: Number(document.getElementById('margin')?.value || 0) || null
        })
      });

      if (!res.ok) {
        toast('Failed to analyze risk. Check backend logs.');
        return;
      }

      latestResult = await res.json();
      renderResult(latestResult);
      showScreen('results');
    }

    function renderResult(r) {
      document.getElementById('emptyResult').classList.add('hidden');
      document.getElementById('resultContent').classList.remove('hidden');
      document.getElementById('emptyDecision').classList.add('hidden');
      document.getElementById('decisionContent').classList.remove('hidden');

      const riskEl = document.getElementById('riskLevel');
      riskEl.textContent = r.risk_level;
      riskEl.style.color = r.risk_level === 'High' ? 'var(--red)' : r.risk_level === 'Medium' ? 'var(--amber)' : 'var(--green)';
      document.getElementById('riskMeaning').textContent = `For the next ${r.horizon_days} days, this looks like a ${r.risk_level.toLowerCase()}-pressure payment outlook.`;
      document.getElementById('currentCost').textContent = `RWF ${fmt(r.current_cost_rwf)}`;
      document.getElementById('currentRateText').textContent = `Current rate: ${fmtRate(r.current_rate)} RWF for 1 USD`;
      document.getElementById('extraCost').textContent = `RWF ${fmt(r.possible_extra_cost_rwf)}`;

      const confidenceScore = r.confidence_score ?? r.confidence ?? 0;
      const drivers = r.key_drivers || {};
      const driverLabels = {
        daily_return: 'Latest day-to-day change',
        return_7d: 'Change over the last 7 days',
        return_14d: 'Change over the last 14 days',
        ma_7: '7-day average rate',
        ma_30: '30-day average rate',
        ma_gap: 'Short-term vs long-term difference',
        volatility_7d: 'How much the rate has been moving',
        momentum_7d: 'Recent direction of movement',
        spread_pct: 'Rate spread as a percentage',
        depreciation_days_7d: 'Recent weaker days'
      };
      document.getElementById('drivers').innerHTML = Object.entries(drivers)
        .map(([k, v]) => `<div class="driver"><span>${driverLabels[k] || k.replaceAll('_', ' ')}</span><strong>${v}</strong></div>`)
        .join('');

      const probs = r.class_probabilities || {};
      const probabilitySummary = Object.entries(probs)
        .sort((a, b) => b[1] - a[1])
        .map(([label, probability]) => `${label} ${Math.round(probability * 100)}%`)
        .join(' · ');
      const topLabel = r.top_probability_label || r.risk_level;
      const topProbability = r.predicted_probability ?? confidenceScore;
      document.getElementById('confidenceText').textContent = `Confidence: ${Math.round(confidenceScore * 100)}% • Top class: ${topLabel} at ${Math.round(topProbability * 100)}%${probabilitySummary ? ` • ${probabilitySummary}` : ''}`;

      if (probChart) probChart.destroy();
      probChart = new Chart(document.getElementById('probChart'), {
        type: 'bar',
        data: {
          labels: Object.keys(probs),
          datasets: [{
            data: Object.values(probs).map(p => p * 100),
            backgroundColor: ['#0f8b6c', '#ad6a10', '#c43c3c']
          }]
        },
        options: {
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: { y: { beginAtZero: true, max: 100, ticks: { callback: v => v + '%' } } }
        }
      });

      const recommendationHtml = r.recommendations.map(x => `<div class="recommendation">${x}</div>`).join('');
      document.getElementById('resultRecommendations').innerHTML = recommendationHtml;
      document.getElementById('decisionRecommendations').innerHTML = recommendationHtml;
      document.getElementById('scenarioRows').innerHTML = `
        <tr><td>Payment amount</td><td><strong>${fmt(r.amount_usd)} USD</strong></td></tr>
        <tr><td>Current rate</td><td><strong>${fmtRate(r.current_rate)} RWF per USD</strong></td></tr>
        <tr><td>Cost today</td><td><strong>RWF ${fmt(r.current_cost_rwf)}</strong></td></tr>
        <tr><td>Possible added cost</td><td><strong style="color:var(--red)">RWF ${fmt(r.possible_extra_cost_rwf)}</strong></td></tr>
        <tr><td>Suggested safety cushion</td><td><strong style="color:var(--amber)">RWF ${fmt(r.suggested_margin_buffer_rwf)}</strong></td></tr>`;
      document.getElementById('disclaimer').textContent = 'This estimate is for planning only. It is not a promise of future rates.';
    }

    document.getElementById('quickAnalyze').addEventListener('click', () => runAssessment(document.getElementById('quickAmount').value, selectedHorizon));
    document.getElementById('analyzeBtn').addEventListener('click', () => runAssessment(document.getElementById('amount').value, selectedMainHorizon));

    init().catch(err => {
      console.error(err);
      toast('Could not load data. Is the backend running?');
    });

