/**
 * freezer-script.js — Spiral Blast Freezer Projection
 * Shows per-unit (Spiral 01/02/03) temperature status with -18°C threshold alerts.
 * Depends on prediction-core.js
 */

// ─── CONFIG ────────────────────────────────────────────────────────────────

const TEMP_THRESHOLD  = -18;   // °C — must be AT or BELOW this to be NORMAL
const TEMP_CRITICAL   = -10;   // °C — above this = CRITICAL (not freezing at all)
const FUTURE_HOURS    = 6;

// Per-unit colours for the combined chart
const UNIT_COLORS = {
    '01': '#06b6d4',   // cyan
    '02': '#8b5cf6',   // purple
    '03': '#f97316',   // orange
};

// ─── MOCK FALLBACK DATA ────────────────────────────────────────────────────
// Simulates realistic operating temperatures for each spiral unit

function makeFreezerMock(baseTef, noise = 1.5) {
    return {
        tef01_series : Array.from({ length: 24 }, (_, i) => baseTef + Math.sin(i / 4) * noise + (Math.random() - 0.5) * noise),
        tef02_series : Array.from({ length: 24 }, (_, i) => (baseTef - 1.5) + Math.sin(i / 4) * noise + (Math.random() - 0.5) * noise),
        energy_series: Array.from({ length: 24 }, () => Math.max(60, 110 + (Math.random() - 0.5) * 25)),
        runtime      : 18.5,
        pt01         : 2.1,
    };
}

const MOCK_UNITS = {
    '01': makeFreezerMock(-32),
    '02': makeFreezerMock(-28),
    '03': makeFreezerMock(-15),  // intentionally warm to demo alert
};

// ─── DATA NORMALIZATION ────────────────────────────────────────────────────

function normalizeRows(rows) {
    if (!Array.isArray(rows) || rows.length === 0) return null;
    return rows.map(r => ({
        tef01        : Number(r.tef01)        || 0,
        tef02        : Number(r.tef02)        || 0,
        pt01         : Number(r.pt01)         || 0,
        runtime      : Number(r.runtime)      || 0,
        freezing_time: Number(r.freezing_time)|| 0,
    }));
}

/** Extract tef01 time-series from normalized rows */
function tempSeries(rows) {
    return rows.map(r => r.tef01).filter(v => v !== 0);
}

// ─── STATUS LOGIC ─────────────────────────────────────────────────────────

/**
 * Determine unit status from the current temperature and whether it's running.
 * Returns { cls, label, tempCls }
 */
function tempStatus(tef01, tef02, runtime) {
    const worstTemp = Math.max(tef01, tef02);   // higher temp = worse for a freezer

    if (runtime <= 0) {
        return { cls: 'stopped', label: 'STOPPED', tempCls: 'temp-stopped' };
    }
    if (worstTemp > TEMP_CRITICAL) {
        return { cls: 'danger',  label: 'CRITICAL', tempCls: 'temp-critical' };
    }
    if (worstTemp > TEMP_THRESHOLD) {
        return { cls: 'warn',    label: 'WARNING',  tempCls: 'temp-warning'  };
    }
    return     { cls: 'ok',      label: 'NORMAL',   tempCls: 'temp-ok'       };
}

// ─── RENDER UNIT CARD ─────────────────────────────────────────────────────

function renderUnitCard(id, latest, tef01Series, energySeries) {
    const status = tempStatus(latest.tef01, latest.tef02, latest.runtime);

    // Status pill
    const pill = document.getElementById(`unit-status-${id}`);
    if (pill) {
        pill.textContent = status.label;
        pill.className   = `sys-status-pill ${status.cls}`;
    }

    // Card border colour
    const card = document.getElementById(`unit-card-${id}`);
    if (card) {
        card.className = `freezer-unit-card border-${status.cls}`;
    }

    // Temperature values — colour them by status
    const tef01El = document.getElementById(`unit-tef01-${id}`);
    const tef02El = document.getElementById(`unit-tef02-${id}`);
    if (tef01El) {
        tef01El.textContent = `${latest.tef01.toFixed(1)}°C`;
        tef01El.className   = `unit-temp-value ${status.tempCls}`;
    }
    if (tef02El) {
        tef02El.textContent = `${latest.tef02.toFixed(1)}°C`;
        tef02El.className   = `unit-temp-value ${status.tempCls}`;
    }

    // Other metrics
    setText(`unit-pt01-${id}`,    `${latest.pt01.toFixed(2)} kg/cm²`);
    setText(`unit-runtime-${id}`, `${latest.runtime.toFixed(1)} hrs`);

    // Predicted energy next 1 hr
    const predEnergy = Math.max(0, linearExtrapolate(energySeries, 1));
    setText(`unit-pred-energy-${id}`, `${predEnergy.toFixed(1)} kWh`);

    // Temp trend
    const trend = trendDirection(tef01Series, false); // lower = better for freezer
    const trendEl = document.getElementById(`unit-temp-trend-${id}`);
    if (trendEl) {
        trendEl.textContent = trend.label;
        trendEl.style.color = trend.cls === 'ok' ? '#10b981' : '#f59e0b';
    }

    // Mini sparkline for temperature
    const preds  = generatePredictions(tef01Series, 3);
    const color  = UNIT_COLORS[id];
    const canvas = document.getElementById(`chart-unit-${id}`);
    if (canvas) {
        const existing = Chart.getChart(canvas);
        if (existing) existing.destroy();

        const PAST   = tef01Series.slice(-10);
        const histD  = [...PAST,          ...Array(3).fill(null)];
        const predD  = [...Array(9).fill(null), PAST[PAST.length - 1], ...preds];

        new Chart(canvas.getContext('2d'), {
            type: 'line',
            data: {
                labels  : Array.from({ length: PAST.length + 3 }, (_, i) => i),
                datasets: [
                    { data: histD, borderColor: color, borderWidth: 2, pointRadius: 0, tension: 0.4, fill: false, spanGaps: false },
                    { data: predD, borderColor: color, borderDash: [5, 3], borderWidth: 2, pointRadius: 0, tension: 0.4, fill: false, spanGaps: false },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false }, tooltip: { enabled: false } },
                scales: { x: { display: false }, y: { display: false } },
            },
        });
    }
}

// ─── COMBINED TEMPERATURE CHART ────────────────────────────────────────────

function renderCombinedChart(units) {
    const canvas = document.getElementById('combinedTempChart');
    if (!canvas) return;
    const existing = Chart.getChart(canvas);
    if (existing) existing.destroy();

    const maxLen     = Math.max(...Object.values(units).map(u => u.tef01Series.length));
    const predCount  = FUTURE_HOURS;
    const labels     = buildTimeLabels(maxLen, predCount);

    const datasets = [];

    Object.entries(units).forEach(([id, u]) => {
        const hist  = u.tef01Series;
        const preds = generatePredictions(hist, predCount);
        const color = UNIT_COLORS[id];
        const name  = `Spiral ${id}`;

        const histData = [...hist, ...Array(predCount).fill(null)];
        const predData = [...Array(hist.length - 1).fill(null), hist[hist.length - 1], ...preds];

        datasets.push({
            label          : `${name} (Historical)`,
            data           : histData,
            borderColor    : color,
            backgroundColor: color + '18',
            borderWidth    : 2,
            pointRadius    : 1.5,
            tension        : 0.4,
            fill           : false,
            spanGaps       : false,
        });
        datasets.push({
            label          : `${name} (Predicted)`,
            data           : predData,
            borderColor    : color,
            borderDash     : [7, 4],
            borderWidth    : 2,
            pointRadius    : 0,
            tension        : 0.4,
            fill           : false,
            spanGaps       : false,
        });
    });

    // Threshold annotation line dataset
    datasets.push({
        label      : '−18°C Threshold',
        data       : Array(labels.length).fill(TEMP_THRESHOLD),
        borderColor: '#ef4444',
        borderDash : [4, 4],
        borderWidth: 1.5,
        pointRadius: 0,
        fill       : false,
    });

    new Chart(canvas.getContext('2d'), {
        type: 'line',
        data: { labels, datasets },
        options: {
            responsive        : true,
            maintainAspectRatio: false,
            interaction       : { mode: 'index', intersect: false },
            plugins: {
                legend: { position: 'top', labels: { usePointStyle: true, font: { size: 11 } } },
                tooltip: {
                    callbacks: {
                        label: c => `${c.dataset.label}: ${c.parsed.y !== null ? c.parsed.y.toFixed(1) + '°C' : 'N/A'}`,
                    },
                },
            },
            scales: {
                x: { grid: { display: false }, ticks: { maxRotation: 45, font: { size: 10 } } },
                y: { grid: { color: '#f1f5f9' }, ticks: { font: { size: 11 } }, title: { display: true, text: '°C' } },
            },
        },
    });
}

// ─── ALERTS ────────────────────────────────────────────────────────────────

function renderAlerts(alertList) {
    const banner = document.getElementById('alert-banner');
    const list   = document.getElementById('alert-list');
    if (alertList.length === 0) { banner.classList.add('hidden'); return; }
    banner.classList.remove('hidden');
    list.innerHTML = alertList.map(a =>
        `<div class="alert-item ${a.critical ? 'critical' : ''}">⚠️ ${a.msg}</div>`
    ).join('');
}

// ─── RECOMMENDATIONS ───────────────────────────────────────────────────────

function buildRecommendations(unitStatuses) {
    const recs = [];
    unitStatuses.forEach(({ id, status, tef01 }) => {
        if (status.cls === 'danger')  recs.push(`Spiral ${id}: temperature at ${tef01.toFixed(1)}°C — inspect evaporator coils and refrigerant charge immediately`);
        else if (status.cls === 'warn') recs.push(`Spiral ${id}: temperature at ${tef01.toFixed(1)}°C — pre-cool belt and monitor compressor load`);
        else if (status.cls === 'stopped') recs.push(`Spiral ${id}: unit stopped — check power and drive status before next batch`);
    });
    if (recs.length === 0) recs.push('All units operating within normal temperature range — no corrective action required');

    // Best unit recommendation
    const running = unitStatuses.filter(u => u.status.cls === 'ok');
    if (running.length > 0) {
        const best = running.reduce((a, b) => a.tef01 < b.tef01 ? a : b);
        recs.push(`Route next priority batch to Spiral ${best.id} — currently coldest at ${best.tef01.toFixed(1)}°C`);
    }

    document.getElementById('rec-items').innerHTML = recs.map(t => `<div class="rec-item">${t}</div>`).join('');
}

// ─── MAIN INIT ─────────────────────────────────────────────────────────────

async function init() {
    startClock();

    // Fetch real API data
    let apiData = null;
    try {
        const res  = await fetch('/api/spiral_blast_freezer', { cache: 'no-store' });
        const text = await res.text();
        apiData    = JSON.parse(text.replace(/\bNaN\b/g, 'null').replace(/\bInfinity\b/g, 'null').replace(/\b-Infinity\b/g, 'null'));
    } catch { /* fall back to mock */ }

    // Build per-unit data objects
    const UNIT_IDS = ['01', '02', '03'];
    const SPIRAL_KEYS = ['spiral_01', 'spiral_02', 'spiral_03'];

    const units   = {};
    const latests = {};

    UNIT_IDS.forEach((id, i) => {
        const rows = normalizeRows(apiData?.status_data?.[SPIRAL_KEYS[i]]?.data);
        const mock = MOCK_UNITS[id];

        const tef01Hist   = rows ? tempSeries(rows)  : mock.tef01_series;
        const energyHist  = mock.energy_series;  // energy always from mock until real energy API available
        const latestRow   = rows ? rows[rows.length - 1] : { tef01: mock.tef01_series.at(-1), tef02: mock.tef02_series.at(-1), pt01: mock.pt01, runtime: mock.runtime };

        units[id]   = { tef01Series: tef01Hist, energyHist };
        latests[id] = latestRow;
    });

    // Render unit cards
    const unitStatuses = [];
    const alerts = [];
    let activeCount = 0;
    let totalEnergy24 = 0;
    let allTefs = [];

    UNIT_IDS.forEach(id => {
        const latest = latests[id];
        const status = tempStatus(latest.tef01, latest.tef02, latest.runtime);

        renderUnitCard(id, latest, units[id].tef01Series, units[id].energyHist);
        unitStatuses.push({ id, status, tef01: latest.tef01 });

        if (status.cls !== 'stopped') activeCount++;

        const predEnergy1h = Math.max(0, linearExtrapolate(units[id].energyHist, 1));
        totalEnergy24 += predEnergy1h * 24;

        allTefs.push(latest.tef01, latest.tef02);

        // Build alerts
        if (status.cls === 'danger') {
            alerts.push({ msg: `Spiral ${id}: temperature ${latest.tef01.toFixed(1)}°C — CRITICAL, above −10°C threshold`, critical: true });
        } else if (status.cls === 'warn') {
            alerts.push({ msg: `Spiral ${id}: temperature ${latest.tef01.toFixed(1)}°C — above −18°C operating threshold`, critical: false });
        }
    });

    // Top KPIs
    const validTefs = allTefs.filter(t => t !== 0);
    const coldest = validTefs.length ? Math.min(...validTefs) : null;
    const warmest = validTefs.length ? Math.max(...validTefs) : null;

    setText('kpi-active',    `${activeCount} / 3`);
    setText('kpi-energy-24h', fmt0(totalEnergy24));
    setText('kpi-confidence', rSquared(units['01'].tef01Series) + '%');

    const coldEl = document.getElementById('kpi-coldest');
    if (coldEl && coldest !== null) coldEl.textContent = `${coldest.toFixed(1)}°C`;

    const warmEl   = document.getElementById('kpi-warmest');
    const warmCard = document.getElementById('kpi-warm-card');
    if (warmEl && warmest !== null) {
        warmEl.textContent = `${warmest.toFixed(1)}°C`;
        warmCard.className = 'kpi-card ' + (warmest > TEMP_THRESHOLD ? 'highlight-red' : 'highlight-green');
    }

    // Alerts + chart + recommendations
    renderAlerts(alerts);
    renderCombinedChart(units);
    buildRecommendations(unitStatuses);

    setText('last-updated', 'Updated ' + new Date().toLocaleTimeString());
}

document.addEventListener('DOMContentLoaded', init);
setInterval(init, 5 * 60 * 1000);
