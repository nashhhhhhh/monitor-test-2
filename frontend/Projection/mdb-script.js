/**
 * mdb-script.js - MDB Power Projection
 * Depends on prediction-core.js
 */

const FUTURE_HOURS = 6;

async function init() {
    const data = await tryFetchAPI('/api/mdb/history');
    if (data?.history?.length) {
        const values = data.history.map((row) => row.energy ?? row.value ?? 0).filter(Boolean);
        if (values.length > 3) MOCK.mdb = values;
    }

    const history = MOCK.mdb;
    const predictions = generatePredictions(history, FUTURE_HOURS);
    const load1h = Math.max(0, predictions[0]);
    const load24h = load1h * 24;
    const peakIndex = history.indexOf(Math.max(...history));
    const peakHour = (new Date().getHours() - (history.length - 1 - peakIndex) + 24) % 24;
    const risk = load1h > THRESHOLDS.mdb.maxLoad * THRESHOLDS.mdb.critPct
        ? 'danger'
        : load1h > THRESHOLDS.mdb.maxLoad * THRESHOLDS.mdb.warnPct
            ? 'warn'
            : 'ok';
    const confidence = rSquared(history);

    setText('kpi-load-1h', `${fmtK(load1h)} kWh`);
    setText('kpi-load-24h', `${fmtK(load24h)} kWh`);
    setText('kpi-peak-time', `${peakHour.toString().padStart(2, '0')}:00`);
    setText('kpi-confidence', `${confidence}%`);

    const riskEl = document.getElementById('kpi-overload-risk');
    const riskSub = document.getElementById('kpi-risk-sub');
    const riskCard = document.getElementById('kpi-risk-card');
    if (riskEl) {
        const pct = ((load1h / THRESHOLDS.mdb.maxLoad) * 100).toFixed(1);
        riskEl.textContent = risk === 'danger' ? 'HIGH' : risk === 'warn' ? 'MODERATE' : 'LOW';
        riskSub.textContent = `${pct}% of max threshold`;
        riskCard.classList.remove('highlight-red', 'highlight-amber', 'highlight-green');
        riskCard.classList.add(risk === 'danger' ? 'highlight-red' : risk === 'warn' ? 'highlight-amber' : 'highlight-green');
    }

    const alerts = [];
    if (risk === 'danger') {
        alerts.push({ msg: `MDB peak load expected around ${peakHour.toString().padStart(2, '0')}:00 - ${fmtK(load1h)} kWh/hr approaching threshold`, critical: true });
    } else if (risk === 'warn') {
        alerts.push({ msg: `MDB load elevated - predicted ${fmtK(load1h)} kWh/hr`, critical: false });
    }

    const banner = document.getElementById('alert-banner');
    const list = document.getElementById('alert-list');
    if (alerts.length > 0) {
        banner.classList.remove('hidden');
        list.innerHTML = alerts.map((alert) => `<div class="alert-item ${alert.critical ? 'critical' : ''}">Alert: ${alert.msg}</div>`).join('');
    } else {
        banner.classList.add('hidden');
    }

    renderForecastLineChart('loadChart', history.map((value) => value / 1000), predictions.map((value) => value / 1000), {
        label: 'MDB Load',
        unit: 'MWh',
        color: '#8b5cf6',
        FUTURE: FUTURE_HOURS,
    });

}

document.addEventListener('DOMContentLoaded', init);
setInterval(init, 5 * 60 * 1000);
