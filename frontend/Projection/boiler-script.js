/**
 * boiler-script.js — Boiler & Air Compressor Projection
 * Depends on prediction-core.js
 */

const FUTURE_HOURS = 6;

async function init() {
    startClock();

    const [boilerData, compData] = await Promise.all([
        tryFetchAPI('/api/boiler'),
        tryFetchAPI('/api/aircompressor'),
    ]);
    // Enrich mock if real data present (field names may vary)
    if (boilerData?.efficiency?.length) MOCK.boiler_eff = boilerData.efficiency.map(r => r.value ?? r).filter(v => v > 0);
    if (compData?.energy?.length)       MOCK.compressor  = compData.energy.map(r => r.value ?? r).filter(v => v > 0);

    // ── Boiler ─────────────────────────────────────────────────────────────
    const boilerPred = generatePredictions(MOCK.boiler_eff, FUTURE_HOURS);
    const gasPred    = generatePredictions(MOCK.boiler_gas, FUTURE_HOURS);

    const eff1h  = Math.min(100, Math.max(0, boilerPred[0]));
    const gas24h = Math.max(0, gasPred[0]) * 24;
    const trend  = trendDirection(MOCK.boiler_eff, true);

    const boilerRisk = eff1h < THRESHOLDS.boiler.minEff      ? 'danger'
                     : eff1h < THRESHOLDS.boiler.minEff + 10  ? 'warn' : 'ok';

    setText('kpi-boiler-eff',   fmt(eff1h) + ' %');
    setText('kpi-boiler-gas',   fmt0(gas24h) + ' kg');
    setText('kpi-boiler-trend', trend.label);

    const brEl   = document.getElementById('kpi-boiler-risk');
    const brCard = document.getElementById('kpi-boiler-risk-card');
    if (brEl) {
        brEl.textContent = boilerRisk === 'danger' ? 'REVIEW NEEDED' : boilerRisk === 'warn' ? 'MONITOR' : 'STABLE';
        brCard.classList.remove('highlight-red', 'highlight-amber', 'highlight-green');
        brCard.classList.add(boilerRisk === 'danger' ? 'highlight-red' : boilerRisk === 'warn' ? 'highlight-amber' : 'highlight-green');
    }

    // ── Compressor ─────────────────────────────────────────────────────────
    const compPred = generatePredictions(MOCK.compressor, FUTURE_HOURS);

    const comp1h  = Math.max(0, compPred[0]);
    const comp24h = comp1h * 24;
    const compTrend = trendDirection(MOCK.compressor, false);
    const compRisk  = comp1h > THRESHOLDS.compressor.maxEnergy        ? 'danger'
                    : comp1h > THRESHOLDS.compressor.maxEnergy * 0.8  ? 'warn' : 'ok';

    setText('kpi-comp-1h',       fmt(comp1h));
    setText('kpi-comp-24h',      fmt0(comp24h));
    setText('kpi-comp-pressure', compTrend.label);

    const crEl   = document.getElementById('kpi-comp-risk');
    const crCard = document.getElementById('kpi-comp-risk-card');
    if (crEl) {
        crEl.textContent = compRisk === 'danger' ? 'HIGH' : compRisk === 'warn' ? 'ELEVATED' : 'NORMAL';
        crCard.classList.remove('highlight-red', 'highlight-amber', 'highlight-green');
        crCard.classList.add(compRisk === 'danger' ? 'highlight-red' : compRisk === 'warn' ? 'highlight-amber' : 'highlight-green');
    }

    // ── Alerts ─────────────────────────────────────────────────────────────
    const alerts = [];
    if (boilerRisk !== 'ok') alerts.push({ msg: `Boiler efficiency declining — predicted ${fmt(eff1h)}% (threshold: ${THRESHOLDS.boiler.minEff}%)`, critical: boilerRisk === 'danger' });
    if (compRisk !== 'ok')   alerts.push({ msg: `Compressor energy elevated — predicted ${fmt(comp1h)} kWh/hr`, critical: compRisk === 'danger' });

    const banner = document.getElementById('alert-banner');
    const list   = document.getElementById('alert-list');
    if (alerts.length > 0) {
        banner.classList.remove('hidden');
        list.innerHTML = alerts.map(a => `<div class="alert-item ${a.critical ? 'critical' : ''}">⚠️ ${a.msg}</div>`).join('');
    } else {
        banner.classList.add('hidden');
    }

    // ── Charts ─────────────────────────────────────────────────────────────
    renderForecastLineChart('boilerChart', MOCK.boiler_eff, boilerPred, { label: 'Efficiency', unit: '%',   color: '#f97316', FUTURE: FUTURE_HOURS });
    renderForecastLineChart('compChart',   MOCK.compressor, compPred,   { label: 'Energy',     unit: 'kWh', color: '#10b981', FUTURE: FUTURE_HOURS });

    // ── Recommendations ────────────────────────────────────────────────────
    const recs = [];
    if (boilerRisk === 'danger') recs.push('Schedule boiler inspection — efficiency below safe threshold');
    if (boilerRisk === 'warn')   recs.push('Monitor boiler heat exchange surfaces — possible fouling detected in trend');
    if (boilerRisk === 'ok')     recs.push('Boiler operating efficiently — maintain current operating parameters');
    if (compRisk === 'danger')   recs.push('Check air dryer and filter condition — high energy may indicate blockage');
    if (compRisk === 'ok')       recs.push('Compressor load stable — no corrective action required');
    if (gas24h > 12000)          recs.push(`High daily gas forecast (${fmt0(gas24h)} kg) — verify burner efficiency`);

    document.getElementById('rec-items').innerHTML = recs.map(t => `<div class="rec-item">${t}</div>`).join('');
    setText('last-updated', 'Updated ' + new Date().toLocaleTimeString());
}

document.addEventListener('DOMContentLoaded', init);
setInterval(init, 5 * 60 * 1000);
