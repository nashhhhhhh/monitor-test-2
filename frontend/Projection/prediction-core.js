/**
 * prediction-core.js
 * Shared prediction math, mock data, chart helpers and utilities.
 * Included by all Projection subpages via <script src="/Projection/prediction-core.js">
 */

// ─── THRESHOLDS ────────────────────────────────────────────────────────────

const THRESHOLDS = {
    wastewater : { maxFlow: 500,    capacityWarnPct: 0.7, capacityCritPct: 0.9 },
    mdb        : { maxLoad: 300000, warnPct: 0.7, critPct: 0.9 },
    boiler     : { minEff: 70 },
    compressor : { maxEnergy: 200 },
    freezer    : { maxEnergy: 150 },
    cctv       : { maxEventsPerDay: 4 },
};

// ─── MOCK DATA ─────────────────────────────────────────────────────────────

function _mockSeries(base, noise, length = 24) {
    return Array.from({ length }, (_, i) =>
        Math.max(0, base + Math.sin(i / 3) * (noise * 0.4) + (Math.random() - 0.5) * noise * 0.6)
    );
}

const MOCK = {
    wastewater  : _mockSeries(280,  60,  24),
    mdb         : _mockSeries(180000, 30000, 24),
    boiler_eff  : _mockSeries(82,   8,   24),
    boiler_gas  : _mockSeries(450,  60,  24),
    compressor  : _mockSeries(95,   20,  24),
    freezer_kwh : _mockSeries(110,  25,  24),
    freezer_temp: _mockSeries(-22,  3,   24),
    wtp_flow    : _mockSeries(320,  40,  24),
    wtp_chlorine: _mockSeries(0.8,  0.2, 24),
    cctv_events : [2, 1, 3, 0, 2, 4, 1, 2, 3, 1, 5, 2],
};

// ─── MATH ──────────────────────────────────────────────────────────────────

function movingAverage(values, window = 5) {
    if (!values || values.length === 0) return 0;
    const s = values.slice(-Math.min(window, values.length));
    return s.reduce((a, b) => a + b, 0) / s.length;
}

function linearExtrapolate(values, steps = 1) {
    const n = Math.min(values.length, 10);
    if (n < 2) return values[values.length - 1] || 0;
    const slice = values.slice(-n);
    const meanX = (n - 1) / 2;
    const meanY = slice.reduce((a, b) => a + b, 0) / n;
    let num = 0, den = 0;
    slice.forEach((y, i) => { num += (i - meanX) * (y - meanY); den += (i - meanX) ** 2; });
    const slope = den !== 0 ? num / den : 0;
    return (meanY - slope * meanX) + slope * (n - 1 + steps);
}

function generatePredictions(hist, count = 6) {
    const ext = [...hist];
    const out = [];
    for (let i = 0; i < count; i++) {
        const next = Math.max(0, linearExtrapolate(ext, 1));
        out.push(next);
        ext.push(next);
    }
    return out;
}

function rSquared(values) {
    const n = Math.min(values.length, 10);
    if (n < 3) return 85;
    const slice = values.slice(-n);
    const meanY = slice.reduce((a, b) => a + b, 0) / n;
    const ssTot = slice.reduce((s, y) => s + (y - meanY) ** 2, 0);
    if (ssTot === 0) return 99;
    const meanX = (n - 1) / 2;
    let num = 0, den = 0;
    slice.forEach((y, i) => { num += (i - meanX) * (y - meanY); den += (i - meanX) ** 2; });
    const slope = den !== 0 ? num / den : 0;
    const intercept = meanY - slope * meanX;
    const ssRes = slice.reduce((s, y, i) => s + (y - (intercept + slope * i)) ** 2, 0);
    return Math.max(0, Math.min(100, Math.round((1 - ssRes / ssTot) * 100)));
}

function trendDirection(values, higherIsBetter = true) {
    if (!values || values.length < 3) return { label: '→ Stable', cls: 'ok' };
    const slope = linearExtrapolate(values, 1) - values[values.length - 1];
    const up = slope > 0.5, dn = slope < -0.5;
    if (higherIsBetter) {
        if (up) return { label: '▲ Improving', cls: 'ok' };
        if (dn) return { label: '▼ Declining', cls: 'danger' };
    } else {
        if (dn) return { label: '▼ Improving', cls: 'ok' };
        if (up) return { label: '▲ Rising',    cls: 'warn' };
    }
    return { label: '→ Stable', cls: 'ok' };
}

function statusFromRisk(risk) {
    if (risk === 'danger') return { label: 'CRITICAL', cls: 'danger' };
    if (risk === 'warn')   return { label: 'WARNING',  cls: 'warn'   };
    return                        { label: 'NORMAL',   cls: 'ok'     };
}

// ─── TIME LABELS ───────────────────────────────────────────────────────────

function buildTimeLabels(histCount, futureCount) {
    const now = new Date();
    const labels = [];
    for (let i = histCount; i > 0; i--) {
        const d = new Date(now - i * 3600000);
        labels.push(d.getHours().toString().padStart(2, '0') + ':00');
    }
    for (let i = 1; i <= futureCount; i++) {
        const d = new Date(now.getTime() + i * 3600000);
        labels.push(d.getHours().toString().padStart(2, '0') + ':00 ⟶');
    }
    return labels;
}

// ─── CHART FACTORY ─────────────────────────────────────────────────────────

/**
 * Render a historical-vs-predicted line chart on a given canvas id.
 * @param {string} canvasId
 * @param {number[]} historical
 * @param {number[]} predictions
 * @param {{ label: string, unit: string, color?: string, height?: number }} opts
 */
function renderForecastLineChart(canvasId, historical, predictions, opts = {}) {
    const {
        label   = 'Value',
        unit    = '',
        color   = '#3b82f6',
        FUTURE  = predictions.length,
    } = opts;

    const canvas = document.getElementById(canvasId);
    if (!canvas) return null;

    // Destroy existing instance
    const existing = Chart.getChart(canvas);
    if (existing) existing.destroy();

    const labels   = buildTimeLabels(historical.length, FUTURE);
    const histData = [...historical, ...Array(FUTURE).fill(null)];
    const predData = [...Array(historical.length - 1).fill(null), historical[historical.length - 1], ...predictions];

    return new Chart(canvas.getContext('2d'), {
        type: 'line',
        data: {
            labels,
            datasets: [
                {
                    label: `${label} (Historical)`,
                    data: histData,
                    borderColor: color,
                    backgroundColor: color + '14',
                    borderWidth: 2.5,
                    pointRadius: 2,
                    tension: 0.4,
                    fill: true,
                    spanGaps: false,
                },
                {
                    label: `${label} (Predicted)`,
                    data: predData,
                    borderColor: '#f59e0b',
                    backgroundColor: 'rgba(245,158,11,0.06)',
                    borderWidth: 2.5,
                    borderDash: [8, 4],
                    pointRadius: 3,
                    pointBackgroundColor: '#f59e0b',
                    tension: 0.4,
                    fill: false,
                    spanGaps: false,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { position: 'top', labels: { usePointStyle: true, font: { size: 12 } } },
                tooltip: {
                    callbacks: {
                        label: c => `${c.dataset.label}: ${c.parsed.y !== null ? c.parsed.y.toFixed(1) + ' ' + unit : 'N/A'}`,
                    },
                },
            },
            scales: {
                x: { grid: { display: false }, ticks: { maxRotation: 45, font: { size: 10 } } },
                y: { grid: { color: '#f1f5f9' }, ticks: { font: { size: 11 } } },
            },
        },
    });
}

// ─── HELPERS ───────────────────────────────────────────────────────────────

function setText(id, val) {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
}

function setHtml(id, html) {
    const el = document.getElementById(id);
    if (el) el.innerHTML = html;
}

function fmt(v, d = 1)  { return (v == null || isNaN(v)) ? '--' : Number(v).toFixed(d); }
function fmt0(v)         { return fmt(v, 0); }
function fmtK(v)         { return v >= 1000 ? (v / 1000).toFixed(1) + 'k' : fmt0(v); }

async function tryFetchAPI(url) {
    try {
        const res  = await fetch(url);
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const text = await res.text();
        return JSON.parse(text.replace(/: NaN/g, ': null'));
    } catch {
        return null;
    }
}

function startClock(id = 'clock') {
    const tick = () => {
        const el = document.getElementById(id);
        if (el) el.textContent = new Date().toTimeString().slice(0, 8);
    };
    tick();
    setInterval(tick, 1000);
}
