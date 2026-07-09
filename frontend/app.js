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
    function fmtSignedRate(num) {
      const sign = num > 0 ? '+' : '';
      return `${sign}${fmtRate(num)}`;
    }
    function fmtPercent(num) {
      const sign = num > 0 ? '+' : '';
      return `${sign}${num.toFixed(2)}%`;
    }
    function toast(msg) {
      const t = document.getElementById('toast');
      t.textContent = msg;
      t.style.display = 'block';
      setTimeout(() => t.style.display = 'none', 3200);
    }

    function updateTrendSummary(points) {
      const latestEl = document.getElementById('trendLatest');
      const changeEl = document.getElementById('trendChange');
      const directionEl = document.getElementById('trendDirection');
      if (!points.length) {
        latestEl.textContent = '--';
        changeEl.textContent = '--';
        directionEl.textContent = 'No data';
        return;
      }

      const first = points[0];
      const last = points[points.length - 1];
      const change = last.mid_rate - first.mid_rate;
      const percentChange = first.mid_rate ? (change / first.mid_rate) * 100 : 0;
      const direction = Math.abs(percentChange) < 0.05 ? 'Mostly flat' : percentChange > 0 ? 'Rising' : 'Falling';

      latestEl.textContent = `${fmtRate(last.mid_rate)} RWF`;
      changeEl.textContent = `${fmtSignedRate(change)} RWF (${fmtPercent(percentChange)})`;
      directionEl.textContent = direction;
      directionEl.style.color = percentChange > 0.05 ? 'var(--amber)' : percentChange < -0.05 ? 'var(--green)' : 'var(--muted)';
    }

    function getCanvasContext(canvas) {
      const rect = canvas.getBoundingClientRect();
      const width = Math.max(Math.round(rect.width), 320);
      const height = Math.max(Math.round(rect.height), Number(canvas.getAttribute('height')) || 160);
      const scale = window.devicePixelRatio || 1;

      canvas.width = Math.round(width * scale);
      canvas.height = Math.round(height * scale);
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;

      const ctx = canvas.getContext('2d');
      ctx.setTransform(scale, 0, 0, scale, 0, 0);
      ctx.clearRect(0, 0, width, height);
      return { ctx, width, height };
    }

    function drawCanvasLineChart(canvas, points) {
      if (!points.length) return;

      const { ctx, width, height } = getCanvasContext(canvas);
      const values = points.map(p => p.mid_rate);
      const rawMin = Math.min(...values);
      const rawMax = Math.max(...values);
      const rawRange = rawMax - rawMin || 1;
      const min = rawMin - rawRange * 0.12;
      const max = rawMax + rawRange * 0.12;
      const range = max - min || 1;
      const pad = { top: 16, right: 18, bottom: 30, left: 58 };
      const chartWidth = width - pad.left - pad.right;
      const chartHeight = height - pad.top - pad.bottom;

      ctx.fillStyle = '#ffffff';
      ctx.fillRect(0, 0, width, height);
      ctx.strokeStyle = 'rgba(20,32,51,0.08)';
      ctx.lineWidth = 1;
      ctx.fillStyle = '#728196';
      ctx.font = '12px Manrope, Segoe UI, sans-serif';

      for (let i = 0; i <= 3; i += 1) {
        const y = pad.top + (chartHeight / 3) * i;
        const value = max - (range / 3) * i;
        ctx.beginPath();
        ctx.moveTo(pad.left, y);
        ctx.lineTo(width - pad.right, y);
        ctx.stroke();
        ctx.fillText(fmtRate(value), 8, y + 4);
      }

      const first = points[0];
      const last = points[points.length - 1];
      ctx.fillText(first.date.slice(5), pad.left, height - 12);
      ctx.textAlign = 'right';
      ctx.fillText(last.date.slice(5), width - pad.right, height - 12);
      ctx.textAlign = 'left';

      const path = new Path2D();
      points.forEach((point, index) => {
        const x = pad.left + (chartWidth * index) / Math.max(points.length - 1, 1);
        const y = pad.top + chartHeight - ((point.mid_rate - min) / range) * chartHeight;
        if (index === 0) path.moveTo(x, y);
        else path.lineTo(x, y);
      });

      const gradient = ctx.createLinearGradient(0, pad.top, 0, height - pad.bottom);
      gradient.addColorStop(0, 'rgba(36,87,214,0.18)');
      gradient.addColorStop(1, 'rgba(36,87,214,0)');
      const area = new Path2D(path);
      area.lineTo(width - pad.right, height - pad.bottom);
      area.lineTo(pad.left, height - pad.bottom);
      area.closePath();
      ctx.fillStyle = gradient;
      ctx.fill(area);

      ctx.strokeStyle = '#2457d6';
      ctx.lineWidth = 2.5;
      ctx.stroke(path);

      const lastPoint = points[points.length - 1];
      const lastX = pad.left + chartWidth;
      const lastY = pad.top + chartHeight - ((lastPoint.mid_rate - min) / range) * chartHeight;
      ctx.fillStyle = '#2457d6';
      ctx.beginPath();
      ctx.arc(lastX, lastY, 4, 0, Math.PI * 2);
      ctx.fill();
    }

    function drawCanvasBarChart(canvas, probabilities) {
      const entries = Object.entries(probabilities);
      if (!entries.length) return;

      const { ctx, width, height } = getCanvasContext(canvas);
      const pad = { top: 18, right: 18, bottom: 36, left: 42 };
      const chartWidth = width - pad.left - pad.right;
      const chartHeight = height - pad.top - pad.bottom;
      const colors = ['#0f8b6c', '#ad6a10', '#c43c3c'];
      const slot = chartWidth / entries.length;

      ctx.fillStyle = '#ffffff';
      ctx.fillRect(0, 0, width, height);
      ctx.strokeStyle = 'rgba(20,32,51,0.08)';
      ctx.fillStyle = '#728196';
      ctx.font = '12px Manrope, Segoe UI, sans-serif';

      for (let i = 0; i <= 4; i += 1) {
        const y = pad.top + (chartHeight / 4) * i;
        ctx.beginPath();
        ctx.moveTo(pad.left, y);
        ctx.lineTo(width - pad.right, y);
        ctx.stroke();
        ctx.fillText(`${100 - i * 25}%`, 8, y + 4);
      }

      entries.forEach(([label, probability], index) => {
        const value = probability * 100;
        const barHeight = (value / 100) * chartHeight;
        const x = pad.left + slot * index + slot * 0.25;
        const y = pad.top + chartHeight - barHeight;
        const barWidth = slot * 0.5;

        ctx.fillStyle = colors[index % colors.length];
        ctx.fillRect(x, y, barWidth, barHeight);
        ctx.fillStyle = '#142033';
        ctx.textAlign = 'center';
        ctx.fillText(label, x + barWidth / 2, height - 12);
        ctx.fillText(`${Math.round(value)}%`, x + barWidth / 2, y - 6);
      });
      ctx.textAlign = 'left';
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
      const points = data.points || [];
      updateTrendSummary(points);
      const canvas = document.getElementById('historyChart');
      if (typeof Chart === 'undefined') {
        drawCanvasLineChart(canvas, points);
        return;
      }
      if (historyChart) historyChart.destroy();
      const values = points.map(p => p.mid_rate);
      const rawMin = Math.min(...values);
      const rawMax = Math.max(...values);
      const rawRange = rawMax - rawMin || 1;
      const lineCtx = canvas.getContext('2d');
      const gradient = lineCtx.createLinearGradient(0, 0, 0, 260);
      gradient.addColorStop(0, 'rgba(36,87,214,0.20)');
      gradient.addColorStop(1, 'rgba(36,87,214,0)');
      historyChart = new Chart(canvas, {
        type: 'line',
        data: {
          labels: points.map(p => p.date),
          datasets: [{
            label: 'USD - RWF',
            data: values,
            tension: .32,
            borderColor: '#2457d6',
            backgroundColor: gradient,
            fill: true,
            pointRadius: points.map((_, index) => index === points.length - 1 ? 3 : 0),
            pointHoverRadius: 4,
            pointBackgroundColor: '#2457d6',
            borderWidth: 2.5
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          interaction: { mode: 'index', intersect: false },
          plugins: {
            legend: { display: false },
            tooltip: {
              displayColors: false,
              callbacks: {
                title: items => items[0]?.label || '',
                label: item => `Rate: ${fmtRate(item.parsed.y)} RWF`
              }
            }
          },
          scales: {
            x: {
              ticks: {
                maxTicksLimit: 5,
                color: '#728196',
                callback: function(value) {
                  const label = this.getLabelForValue(value);
                  return label ? label.slice(5) : '';
                }
              },
              grid: { display: false },
              border: { display: false }
            },
            y: {
              min: rawMin - rawRange * 0.12,
              max: rawMax + rawRange * 0.12,
              ticks: {
                maxTicksLimit: 4,
                color: '#728196',
                callback: value => fmtRate(value)
              },
              grid: { color: 'rgba(20,32,51,0.08)' },
              border: { display: false }
            }
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
      if (typeof Chart === 'undefined') {
        drawCanvasBarChart(document.getElementById('probChart'), probs);
      } else {
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
      }

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

