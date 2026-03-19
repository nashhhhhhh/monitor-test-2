/**
 * Projection Overview – script.js
 * Computes per-system forecasts, renders summary cards and alerts.
 * Relies on prediction-core.js being loaded first.
 */

// ─── CONSTANTS ─────────────────────────────────────────────────────────────

const FREEZER_TEMP_WARN = -18;   // °C — above this = WARNING
const FREEZER_TEMP_CRIT = -10;   // °C — above this = CRITICAL

// ─── FREEZER LIVE CACHE ─────────────────────────────────────────────────────
// Populated in init() from the real API; read by the freezer compute() below.

let FREEZER_CACHE = null;

// Mock fallback per-unit temps (used when API unavailable)
const FREEZER_MOCK_UNITS = {
    spiral_01: { tef01: -32.1, tef02: -30.4, runtime: 18.5 },
    spiral_02: { tef01: -28.6, tef02: -27.1, runtime: 20.0 },
    spiral_03: { tef01: -15.2, tef02: -14.8, runtime: 16.0 },  // warm — demo alert
};

function normalizeFreezerRow(row) {
    return {
        tef01  : Number(row?.tef01)   || 0,
        tef02  : Number(row?.tef02)   || 0,
        runtime: Number(row?.runtime) || 0,
    };
}

/** Fetch real freezer API and populate FREEZER_CACHE */
async function loadFreezerCache() {
    try {
        const res  = await fetch('/api/spiral_blast_freezer', { cache: 'no-store' });
        const text = await res.text();
        const data = JSON.parse(
            text.replace(/\bNaN\b/g, 'null')
                .replace(/\bInfinity\b/g, 'null')
                .replace(/\b-Infinity\b/g, 'null')
        );
        const sd = data?.status_data || {};
        FREEZER_CACHE = {
            spiral_01: normalizeFreezerRow((sd.spiral_01?.data || []).at(-1)),
            spiral_02: normalizeFreezerRow((sd.spiral_02?.data || []).at(-1)),
            spiral_03: normalizeFreezerRow((sd.spiral_03?.data || []).at(-1)),
        };
    } catch {
        FREEZER_CACHE = null;  // will fall back to mock
    }
}

// ─── SYSTEM DEFINITIONS ────────────────────────────────────────────────────

const SYSTEMS = [
    {
        id          : 'freezer',
        name        : 'Spiral Blast Freezer',
        icon        : '❄️',
        subpage     : '/Projection/freezer.html',
        color       : '#06b6d4',
        compute() {
            const units  = FREEZER_CACHE || FREEZER_MOCK_UNITS;
            const entries = Object.entries(units);

            let worstRisk  = 'ok';
            let alertUnits = [];
            let activeCount = 0;

            entries.forEach(([key, u]) => {
                const id   = key.replace('spiral_0', '');
                const temp = Math.max(u.tef01, u.tef02);   // higher = worse
                if (u.runtime > 0) activeCount++;
                if (temp > FREEZER_TEMP_CRIT) {
                    worstRisk = 'danger';
                    alertUnits.push(`Spiral ${id}: ${u.tef01.toFixed(1)}°C (CRITICAL)`);
                } else if (temp > FREEZER_TEMP_WARN) {
                    if (worstRisk !== 'danger') worstRisk = 'warn';
                    alertUnits.push(`Spiral ${id}: ${u.tef01.toFixed(1)}°C (above −18°C)`);
                }
            });

            // Predicted energy (combined mock estimate — real energy API extension point)
            const energy1h  = Math.max(0, linearExtrapolate(MOCK.freezer_kwh, 1));
            const energy24  = energy1h * 24;

            // Card metric
            let metric;
            if (alertUnits.length === 0) {
                metric = `${activeCount}/3 Active — All normal`;
            } else {
                metric = alertUnits.length === 1
                    ? `⚠ ${alertUnits[0]}`
                    : `⚠ ${alertUnits.length} units above −18°C`;
            }

            const alertMsg = alertUnits.length > 0
                ? `Freezer temperature alert — ${alertUnits.join(' | ')}`
                : null;

            return {
                metric,
                risk      : worstRisk,
                alert     : alertMsg,
                energyKwh : energy24,
            };
        },
    },
    {
        id        : 'wastewater',
        name      : 'Wastewater Plant',
        icon      : '💧',
        subpage   : '/Projection/water.html',
        color     : '#3b82f6',
        compute() {
            const flow1h  = Math.max(0, linearExtrapolate(MOCK.wastewater, 1));
            const flow24  = flow1h * 24;
            const risk    = flow1h > THRESHOLDS.wastewater.maxFlow * THRESHOLDS.wastewater.capacityCritPct ? 'danger'
                          : flow1h > THRESHOLDS.wastewater.maxFlow * THRESHOLDS.wastewater.capacityWarnPct ? 'warn' : 'ok';
            return {
                metric  : `${fmt0(flow24)} m³ (24 h forecast)`,
                risk,
                alert   : risk !== 'ok' ? `Wastewater flow predicted at ${fmt(flow1h)} m³/hr — nearing capacity` : null,
                waterM3 : flow24,
            };
        },
    },
    {
        id        : 'wtp',
        name      : 'Water Treatment Plant',
        icon      : '🚰',
        subpage   : '/Projection/water.html',
        color     : '#0ea5e9',
        compute() {
            const flow1h = Math.max(0, linearExtrapolate(MOCK.wtp_flow, 1));
            const flow24 = flow1h * 24;
            const cl     = movingAverage(MOCK.wtp_chlorine, 5);
            const risk   = cl < 0.5 ? 'danger' : cl < 0.7 ? 'warn' : 'ok';
            return {
                metric  : `${fmt0(flow24)} m³ (24 h forecast)`,
                risk,
                alert   : risk !== 'ok' ? `WTP chlorine trend low — predicted ${fmt(cl)} mg/L` : null,
                waterM3 : flow24,
            };
        },
    },
    {
        id        : 'mdb',
        name      : 'MDB / Power Distribution',
        icon      : '⚡',
        subpage   : '/Projection/mdb.html',
        color     : '#8b5cf6',
        compute() {
            const load1h  = Math.max(0, linearExtrapolate(MOCK.mdb, 1));
            const load24  = load1h * 24;
            const peakIdx = MOCK.mdb.indexOf(Math.max(...MOCK.mdb));
            const peakH   = (new Date().getHours() - (MOCK.mdb.length - 1 - peakIdx) + 24) % 24;
            const risk    = load1h > THRESHOLDS.mdb.maxLoad * THRESHOLDS.mdb.critPct ? 'danger'
                          : load1h > THRESHOLDS.mdb.maxLoad * THRESHOLDS.mdb.warnPct ? 'warn' : 'ok';
            return {
                metric    : `${fmtK(load24)} kWh (24 h forecast)`,
                risk,
                alert     : risk !== 'ok' ? `MDB peak load expected around ${peakH.toString().padStart(2,'0')}:00 — ${fmtK(load1h)} kWh/hr` : null,
                energyKwh : load24,
            };
        },
    },
    {
        id        : 'boiler',
        name      : 'Boiler System',
        icon      : '🔥',
        subpage   : '/Projection/boiler.html',
        color     : '#f97316',
        compute() {
            const eff1h  = Math.min(100, Math.max(0, linearExtrapolate(MOCK.boiler_eff, 1)));
            const gas24  = movingAverage(MOCK.boiler_gas, 5) * 24;
            const risk   = eff1h < THRESHOLDS.boiler.minEff      ? 'danger'
                         : eff1h < THRESHOLDS.boiler.minEff + 10  ? 'warn' : 'ok';
            return {
                metric    : `${fmt(eff1h)}% efficiency (predicted)`,
                risk,
                alert     : risk !== 'ok' ? `Boiler efficiency declining — predicted ${fmt(eff1h)}%` : null,
                energyKwh : gas24 * 12.5,
            };
        },
    },
    {
        id        : 'compressor',
        name      : 'Air Compressor',
        icon      : '🌀',
        subpage   : '/Projection/boiler.html',
        color     : '#10b981',
        compute() {
            const energy1h = Math.max(0, linearExtrapolate(MOCK.compressor, 1));
            const energy24 = energy1h * 24;
            const risk     = energy1h > THRESHOLDS.compressor.maxEnergy       ? 'danger'
                           : energy1h > THRESHOLDS.compressor.maxEnergy * 0.8 ? 'warn' : 'ok';
            return {
                metric    : `${fmt0(energy24)} kWh (24 h forecast)`,
                risk,
                alert     : risk !== 'ok' ? `Compressor energy elevated — predicted ${fmt(energy1h)} kWh/hr` : null,
                energyKwh : energy24,
            };
        },
    },
    {
        id          : 'cctv',
        name        : 'CCTV Monitoring',
        icon        : '📷',
        subpage     : '/Projection/cctv.html',
        color       : '#64748b',
        noProjection: true,
        compute()   { return { metric: 'Event-based — see Downtime tab', risk: 'none', alert: null }; },
    },
    {
        id          : 'kitchen',
        name        : 'Kitchen Equipment',
        icon        : '🍽️',
        subpage     : '/Projection/cctv.html',
        color       : '#64748b',
        noProjection: true,
        compute()   { return { metric: 'Event-based — see Downtime tab', risk: 'none', alert: null }; },
    },
];

// ─── RENDER SYSTEM CARDS ────────────────────────────────────────────────────

function renderSystemCards(results) {
    const grid = document.getElementById('system-cards');
    grid.innerHTML = results.map(({ sys, result }) => {
        const { risk, metric } = result;
        const s = sys.noProjection ? { label: 'N/A', cls: 'na' } : statusFromRisk(risk);

        const confSrc = sys.id === 'freezer' ? MOCK.freezer_kwh
                      : sys.id === 'mdb'     ? MOCK.mdb
                      : sys.id === 'boiler'  ? MOCK.boiler_eff
                      : MOCK.wastewater;

        return `
        <div class="sys-card ${s.cls}" onclick="location.href='${sys.subpage}'">
            <div class="sys-card-top">
                <div class="sys-icon" style="background:${sys.color}22; color:${sys.color};">${sys.icon}</div>
                <span class="sys-status-pill ${s.cls}">${s.label}</span>
            </div>
            <div class="sys-name">${sys.name}</div>
            <div class="sys-metric">${metric}</div>
            ${sys.noProjection
                ? `<div class="sys-na-note">Projection not applicable for this system.</div>`
                : `<div class="sys-confidence">Confidence: ${rSquared(confSrc)}%</div>`
            }
            <div class="sys-card-footer">View Detailed Forecast →</div>
        </div>`;
    }).join('');
}

// ─── ALERTS ────────────────────────────────────────────────────────────────

function renderAlerts(alerts) {
    const banner = document.getElementById('alert-banner');
    const list   = document.getElementById('alert-list');
    const count  = document.getElementById('kpi-alert-count');
    const sub    = document.getElementById('kpi-alert-sub');
    const card   = document.getElementById('kpi-alert-card');

    count.textContent = alerts.length;

    if (alerts.length === 0) {
        banner.classList.add('hidden');
        sub.textContent = 'All forecasts within range';
        card.classList.remove('highlight-red');
        card.classList.add('highlight-green');
        return;
    }

    card.classList.remove('highlight-green');
    card.classList.add('highlight-red');
    sub.textContent = alerts.length === 1 ? '1 system needs attention' : `${alerts.length} systems need attention`;
    banner.classList.remove('hidden');
    list.innerHTML = alerts.map(a =>
        `<div class="alert-item ${a.critical ? 'critical' : ''}">⚠️ ${a.msg}</div>`
    ).join('');
}

// ─── GLOBAL KPIs ───────────────────────────────────────────────────────────

function updateGlobalKPIs(results) {
    let totalEnergy  = 0;
    let totalWater   = 0;
    let enabledCount = 0;

    results.forEach(({ sys, result }) => {
        if (!sys.noProjection) enabledCount++;
        if (result.energyKwh) totalEnergy += result.energyKwh;
        if (result.waterM3)   totalWater  += result.waterM3;
    });

    setText('kpi-energy-total', fmtK(totalEnergy) + ' kWh');
    setText('kpi-water-total',  fmt0(totalWater) + ' m³');
    setText('kpi-sys-enabled',  `${enabledCount} / ${SYSTEMS.length}`);
}

// ─── MAIN INIT ─────────────────────────────────────────────────────────────

async function init() {
    startClock();

    // Fetch all data sources in parallel
    const [wwData, mdbData] = await Promise.all([
        tryFetchAPI('/api/wwtp/history'),
        tryFetchAPI('/api/mdb/history'),
        loadFreezerCache(),          // populates FREEZER_CACHE
    ]);

    if (wwData?.history?.length)  MOCK.wastewater = wwData.history.map(r => r.value ?? r.temperature ?? 0).filter(Boolean);
    if (mdbData?.history?.length) MOCK.mdb        = mdbData.history.map(r => r.energy ?? r.value ?? 0).filter(Boolean);

    // Compute all systems (freezer.compute() now reads FREEZER_CACHE)
    const results = SYSTEMS.map(sys => ({ sys, result: sys.compute() }));

    const alerts = results
        .filter(({ result }) => result.alert)
        .map(({ sys, result }) => ({ msg: result.alert, critical: result.risk === 'danger' }));

    updateGlobalKPIs(results);
    renderAlerts(alerts);
    renderSystemCards(results);

    setText('last-updated', 'Updated ' + new Date().toLocaleTimeString());
}

document.addEventListener('DOMContentLoaded', init);
setInterval(() => init(), 5 * 60 * 1000);
