/**
 * water-script.js - Water & Wastewater Projection
 * Depends on prediction-core.js
 */

const FUTURE_HOURS = 6;
const TANK_CAPACITY_M3 = 5000;

async function init() {
    const [wwData, wtpData] = await Promise.all([
        tryFetchAPI('/api/wwtp/history'),
        tryFetchAPI('/api/wtp'),
    ]);

    if (wwData?.history?.length) MOCK.wastewater = wwData.history.map((row) => row.value ?? row.temperature ?? 0).filter(Boolean);
    if (wtpData?.flow?.length) MOCK.wtp_flow = wtpData.flow.map((row) => row.value ?? 0).filter(Boolean);
    if (wtpData?.quality?.ro_chlorine?.length) {
        MOCK.wtp_chlorine = wtpData.quality.ro_chlorine.map((row) => row.mg ?? 0).filter(Boolean);
    }

    const wwPred = generatePredictions(MOCK.wastewater, FUTURE_HOURS);
    const wtpPred = generatePredictions(MOCK.wtp_flow, FUTURE_HOURS);
    const clPred = generatePredictions(MOCK.wtp_chlorine, FUTURE_HOURS);

    const ww1h = Math.max(0, wwPred[0]);
    const ww24h = ww1h * 24;
    const wtp24h = Math.max(0, wtpPred[0]) * 24;
    const cl1h = Math.max(0, clPred[0]);

    const netFlow = ww1h - Math.max(0, movingAverage(MOCK.wtp_flow, 3));
    const tankLvlPct = Math.min(100, 60 + (netFlow / TANK_CAPACITY_M3) * 100 * 3);
    const hoursTo90 = netFlow > 0 ? ((TANK_CAPACITY_M3 * 0.9 - TANK_CAPACITY_M3 * 0.6) / netFlow).toFixed(1) : null;

    setText('kpi-ww-1h', fmt(ww1h));
    setText('kpi-ww-24h', fmt0(ww24h));
    setText('kpi-wtp-24h', fmt0(wtp24h));
    setText('kpi-chlorine', fmt(cl1h, 2));

    const trendEl = document.getElementById('kpi-tank-trend');
    const trendSub = document.getElementById('kpi-tank-sub');
    const trendCard = document.getElementById('kpi-tank-card');
    if (trendEl) {
        trendEl.textContent = `${tankLvlPct.toFixed(1)}%`;
        trendCard.classList.remove('highlight-amber', 'highlight-red', 'highlight-green');
        if (tankLvlPct >= 90) {
            trendCard.classList.add('highlight-red');
            trendSub.textContent = 'CRITICAL - near capacity';
        } else if (tankLvlPct >= 75) {
            trendCard.classList.add('highlight-amber');
            trendSub.textContent = hoursTo90 ? `May reach 90% in ~${hoursTo90} hr` : 'Elevated - monitor closely';
        } else {
            trendCard.classList.add('highlight-green');
            trendSub.textContent = 'Within normal operating range';
        }
    }

    const alerts = [];
    if (tankLvlPct >= 90) alerts.push({ msg: 'Tank approaching capacity - immediate action required', critical: true });
    else if (tankLvlPct >= 75 && hoursTo90) alerts.push({ msg: `Tank may reach 90% capacity in ~${hoursTo90} hours`, critical: false });
    if (ww1h > THRESHOLDS.wastewater.maxFlow * 0.9) alerts.push({ msg: `Wastewater inflow predicted at ${fmt(ww1h)} m3/hr - nearing max capacity`, critical: true });
    if (cl1h < 0.5) alerts.push({ msg: `RO chlorine residual declining - predicted ${fmt(cl1h, 2)} mg/L`, critical: cl1h < 0.3 });

    const banner = document.getElementById('alert-banner');
    const list = document.getElementById('alert-list');
    if (alerts.length > 0) {
        banner.classList.remove('hidden');
        list.innerHTML = alerts.map((alert) => `<div class="alert-item ${alert.critical ? 'critical' : ''}">Alert: ${alert.msg}</div>`).join('');
    } else {
        banner.classList.add('hidden');
    }

    renderForecastLineChart('wwChart', MOCK.wastewater, wwPred, { label: 'WW Flow', unit: 'm3/hr', color: '#3b82f6', FUTURE: FUTURE_HOURS });
    renderForecastLineChart('wtpChart', MOCK.wtp_flow, wtpPred, { label: 'WTP Flow', unit: 'm3/hr', color: '#0ea5e9', FUTURE: FUTURE_HOURS });

  }

document.addEventListener('DOMContentLoaded', init);
setInterval(init, 5 * 60 * 1000);
