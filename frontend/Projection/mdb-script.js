/**
 * mdb-script.js — MDB Power Projection
 * Depends on prediction-core.js
 */

const FUTURE_HOURS = 6;

async function init() {
    startClock();

    const data = await tryFetchAPI('/api/mdb/history');
    if (data?.history?.length) {
        const vals = data.history.map(r => r.energy ?? r.value ?? 0).filter(Boolean);
        if (vals.length > 3) MOCK.mdb = vals;
    }

    const hist = MOCK.mdb;
    const pred = generatePredictions(hist, FUTURE_HOURS);

    const load1h  = Math.max(0, pred[0]);
    const load24h = load1h * 24;

    // Peak hour from historical pattern
    const peakIdx = hist.indexOf(Math.max(...hist));
    const peakH   = (new Date().getHours() - (hist.length - 1 - peakIdx) + 24) % 24;

    const risk = load1h > THRESHOLDS.mdb.maxLoad * THRESHOLDS.mdb.critPct ? 'danger'
               : load1h > THRESHOLDS.mdb.maxLoad * THRESHOLDS.mdb.warnPct ? 'warn' : 'ok';
    const conf = rSquared(hist);

    setText('kpi-load-1h',   fmtK(load1h) + ' kWh');
    setText('kpi-load-24h',  fmtK(load24h) + ' kWh');
    setText('kpi-peak-time', peakH.toString().padStart(2,'0') + ':00');
    setText('kpi-confidence', conf + '%');

    const riskEl   = document.getElementById('kpi-overload-risk');
    const riskSub  = document.getElementById('kpi-risk-sub');
    const riskCard = document.getElementById('kpi-risk-card');
    if (riskEl) {
        const pct = ((load1h / THRESHOLDS.mdb.maxLoad) * 100).toFixed(1);
        riskEl.textContent = risk === 'danger' ? 'HIGH' : risk === 'warn' ? 'MODERATE' : 'LOW';
        riskSub.textContent = `${pct}% of max threshold`;
        riskCard.classList.remove('highlight-red', 'highlight-amber', 'highlight-green');
        riskCard.classList.add(risk === 'danger' ? 'highlight-red' : risk === 'warn' ? 'highlight-amber' : 'highlight-green');
    }

    // Alerts
    const alerts = [];
    if (risk === 'danger') alerts.push({ msg: `MDB peak load expected around ${peakH.toString().padStart(2,'0')}:00 — ${fmtK(load1h)} kWh/hr approaching threshold`, critical: true });
    else if (risk === 'warn') alerts.push({ msg: `MDB load elevated — predicted ${fmtK(load1h)} kWh/hr`, critical: false });

    const banner = document.getElementById('alert-banner');
    const list   = document.getElementById('alert-list');
    if (alerts.length > 0) {
        banner.classList.remove('hidden');
        list.innerHTML = alerts.map(a => `<div class="alert-item ${a.critical ? 'critical' : ''}">⚠️ ${a.msg}</div>`).join('');
    } else {
        banner.classList.add('hidden');
    }

    // Chart
    renderForecastLineChart('loadChart', hist.map(v => v / 1000), pred.map(v => v / 1000), {
        label : 'MDB Load',
        unit  : 'MWh',
        color : '#8b5cf6',
        FUTURE: FUTURE_HOURS,
    });

    // Recommendations
    const recs = [];
    if (risk === 'ok')     recs.push('Power consumption within normal range — no action required');
    if (risk === 'warn')   recs.push(`Prepare for elevated load around ${peakH.toString().padStart(2,'0')}:00 — consider staggering non-critical equipment`);
    if (risk === 'danger') recs.push('Consider load shedding of non-critical systems before peak period');
    if (risk === 'danger') recs.push('Verify generator standby readiness ahead of predicted peak');
    recs.push(`Generator switch-over recommended if grid load exceeds ${fmtK(THRESHOLDS.mdb.maxLoad * 0.95)} kWh`);

    document.getElementById('rec-items').innerHTML = recs.map(t => `<div class="rec-item">${t}</div>`).join('');
    setText('last-updated', 'Updated ' + new Date().toLocaleTimeString());
}

document.addEventListener('DOMContentLoaded', init);
setInterval(init, 5 * 60 * 1000);
