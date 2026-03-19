/**
 * Downtime & Reliability Monitoring Page
 * Tracks equipment failures, recovery times, MTBF, and reliability scores.
 */

// ─── CONFIG ────────────────────────────────────────────────────────────────

const ALERT_THRESHOLDS = {
    maxEventsPerDay  : 4,    // trigger alert if a system fails this many times today
    minReliability   : 90,   // % — below this = warning on reliability bar
    critReliability  : 80,   // % — below this = critical
    maxDowntimeMins  : 60,   // total mins before warning
    critDowntimeMins : 180,  // total mins before critical
};

// ─── MOCK DOWNTIME DATA ────────────────────────────────────────────────────
// Shape: { equipment, events: [{ start, end }], recoveryMins[] }
// In production replace with real API data (e.g. /api/cctv/log, etc.)

function generateMockDowntimeData() {
    const todayBase = new Date();
    todayBase.setHours(0, 0, 0, 0);

    function event(startH, startM, durationMins) {
        const start = new Date(todayBase);
        start.setHours(startH, startM);
        const end = new Date(start.getTime() + durationMins * 60000);
        return { start, end, durationMins };
    }

    return [
        {
            equipment: 'CCTV C.16',
            category: 'CCTV',
            events: [event(1,15,12), event(4,30,8), event(7,45,20), event(11,0,15), event(14,20,9), event(18,5,11)],
            recoveryMins: [5, 4, 7, 6, 4, 6],
        },
        {
            equipment: 'CCTV C.08',
            category: 'CCTV',
            events: [event(3,10,10), event(9,45,25), event(16,30,8)],
            recoveryMins: [6, 12, 5],
        },
        {
            equipment: 'Spiral Blast Freezer',
            category: 'Freezer',
            events: [event(2,0,45), event(13,30,30)],
            recoveryMins: [20, 18],
        },
        {
            equipment: 'Boiler 01',
            category: 'Boiler',
            events: [event(6,15,25)],
            recoveryMins: [15],
        },
        {
            equipment: 'Boiler 02',
            category: 'Boiler',
            events: [],
            recoveryMins: [],
        },
        {
            equipment: 'Air Compressor',
            category: 'Utilities',
            events: [event(8,0,15), event(17,45,20)],
            recoveryMins: [10, 12],
        },
        {
            equipment: 'MDB Generator',
            category: 'MDB',
            events: [event(5,30,10)],
            recoveryMins: [8],
        },
        {
            equipment: 'Wastewater Pump',
            category: 'Wastewater',
            events: [event(10,0,35), event(19,15,20)],
            recoveryMins: [18, 12],
        },
        {
            equipment: 'Hobart Dishwasher',
            category: 'Kitchen',
            events: [event(7,0,10), event(12,30,8)],
            recoveryMins: [5, 4],
        },
        {
            equipment: 'X-Ray Inspector',
            category: 'Kitchen',
            events: [event(9,15,5)],
            recoveryMins: [3],
        },
    ];
}

// ─── METRICS CALCULATION ───────────────────────────────────────────────────

const MINUTES_IN_DAY = 24 * 60;

function calcMetrics(equipment) {
    const totalDownMins = equipment.events.reduce((sum, e) => sum + e.durationMins, 0);
    const eventCount    = equipment.events.length;
    const uptimePercent = Math.max(0, ((MINUTES_IN_DAY - totalDownMins) / MINUTES_IN_DAY) * 100);
    const avgDuration   = eventCount > 0 ? totalDownMins / eventCount : 0;
    const avgRecovery   = equipment.recoveryMins.length > 0
        ? equipment.recoveryMins.reduce((a, b) => a + b, 0) / equipment.recoveryMins.length
        : 0;

    // MTBF: (uptime minutes) / number of failures (avoid div by zero)
    const mtbf = eventCount > 0 ? (MINUTES_IN_DAY - totalDownMins) / eventCount : MINUTES_IN_DAY;

    const status = eventCount >= ALERT_THRESHOLDS.maxEventsPerDay || totalDownMins >= ALERT_THRESHOLDS.critDowntimeMins
        ? 'critical'
        : totalDownMins >= ALERT_THRESHOLDS.maxDowntimeMins
        ? 'warning'
        : 'ok';

    return { totalDownMins, eventCount, uptimePercent, avgDuration, avgRecovery, mtbf, status };
}

function fmtDuration(mins) {
    if (mins <= 0) return '0 min';
    const h = Math.floor(mins / 60);
    const m = Math.round(mins % 60);
    return h > 0 ? `${h}h ${m}m` : `${m} min`;
}

// ─── KPI POPULATION ────────────────────────────────────────────────────────

function setText(id, val) {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
}

function populateKPIs(all) {
    const totalDownMins  = all.reduce((s, eq) => s + calcMetrics(eq).totalDownMins, 0);
    const totalEvents    = all.reduce((s, eq) => s + calcMetrics(eq).eventCount, 0);
    const avgMtbf        = all.filter(eq => calcMetrics(eq).eventCount > 0)
                              .map(eq => calcMetrics(eq).mtbf);
    const mtbfAvg        = avgMtbf.length > 0
        ? avgMtbf.reduce((a, b) => a + b, 0) / avgMtbf.length
        : MINUTES_IN_DAY;

    const worst = all.reduce((prev, curr) => {
        return calcMetrics(curr).totalDownMins > calcMetrics(prev).totalDownMins ? curr : prev;
    }, all[0]);

    const combinedUptime = ((MINUTES_IN_DAY * all.length - totalDownMins) /
                            (MINUTES_IN_DAY * all.length) * 100);

    setText('kpi-total-downtime', fmtDuration(totalDownMins));
    setText('kpi-event-count',    totalEvents);
    setText('kpi-worst-system',   worst.equipment);
    setText('kpi-worst-sub',      `${fmtDuration(calcMetrics(worst).totalDownMins)} total downtime`);
    setText('kpi-mtbf',           fmtDuration(mtbfAvg));
    setText('kpi-uptime',         combinedUptime.toFixed(1) + '%');
}

// ─── ALERT SYSTEM ──────────────────────────────────────────────────────────

const alertMessages = [];

function checkAlerts(all) {
    all.forEach(eq => {
        const m = calcMetrics(eq);
        if (m.eventCount >= ALERT_THRESHOLDS.maxEventsPerDay) {
            alertMessages.push({
                msg: `${eq.equipment} offline ${m.eventCount} times today — ${fmtDuration(m.totalDownMins)} total downtime`,
                critical: m.eventCount >= ALERT_THRESHOLDS.maxEventsPerDay + 2,
            });
        }
        if (m.uptimePercent < ALERT_THRESHOLDS.critReliability) {
            alertMessages.push({
                msg: `${eq.equipment} reliability critical — ${m.uptimePercent.toFixed(1)}% uptime`,
                critical: true,
            });
        }
    });

    const banner = document.getElementById('alert-banner');
    const list   = document.getElementById('alert-list');
    if (alertMessages.length === 0) { banner.classList.add('hidden'); return; }

    banner.classList.remove('hidden');
    list.innerHTML = alertMessages.map(a =>
        `<div class="alert-item ${a.critical ? 'critical' : ''}">⚠️ ${a.msg}</div>`
    ).join('');
}

// ─── DOWNTIME TABLE ────────────────────────────────────────────────────────

function renderTable(all) {
    const tbody = document.getElementById('downtime-tbody');
    tbody.innerHTML = all.map(eq => {
        const m = calcMetrics(eq);
        const pillClass = m.status === 'critical' ? 'critical' : m.status === 'warning' ? 'warning' : 'ok';
        const pillLabel = m.status === 'critical' ? 'Critical' : m.status === 'warning' ? 'Warning' : 'Normal';

        return `
        <tr>
            <td><strong>${eq.equipment}</strong><br><small style="color:var(--text-muted)">${eq.category}</small></td>
            <td>${m.eventCount}</td>
            <td>${fmtDuration(m.totalDownMins)}</td>
            <td>${m.eventCount > 0 ? fmtDuration(m.avgDuration) : '—'}</td>
            <td>${m.eventCount > 0 ? fmtDuration(m.avgRecovery) : '—'}</td>
            <td>${m.uptimePercent.toFixed(1)}%</td>
            <td><span class="status-pill ${pillClass}">${pillLabel}</span></td>
        </tr>`;
    }).join('');
}

// ─── RELIABILITY BARS ──────────────────────────────────────────────────────

function renderReliabilityBars(all) {
    const container = document.getElementById('reliability-list');
    container.innerHTML = all.map(eq => {
        const m = calcMetrics(eq);
        const pct = m.uptimePercent.toFixed(1);
        const color = m.uptimePercent >= ALERT_THRESHOLDS.minReliability
            ? '#10b981'
            : m.uptimePercent >= ALERT_THRESHOLDS.critReliability
            ? '#f59e0b'
            : '#ef4444';
        return `
        <div class="reliability-item">
            <span class="rel-name" title="${eq.equipment}">${eq.equipment}</span>
            <div class="rel-bar-wrap">
                <div class="rel-bar-fill" style="width:${pct}%; background:${color};"></div>
            </div>
            <span class="rel-score" style="color:${color};">${pct}%</span>
        </div>`;
    }).join('');
}

// ─── TIMELINE CHART ────────────────────────────────────────────────────────

function renderTimelineChart(all) {
    const ctx = document.getElementById('timelineChart').getContext('2d');

    // Build hourly running/downtime counts across all equipment
    const hours = Array.from({ length: 24 }, (_, i) => i);
    const hourLabels = hours.map(h => h.toString().padStart(2, '0') + ':00');

    const runningCounts  = new Array(24).fill(0);
    const downtimeCounts = new Array(24).fill(0);

    all.forEach(eq => {
        eq.events.forEach(ev => {
            const startH = ev.start.getHours();
            const endH   = Math.min(23, ev.end.getHours());
            for (let h = startH; h <= endH; h++) {
                downtimeCounts[h]++;
            }
        });
        // Running = total equipment minus those in downtime each hour
        hours.forEach(h => {
            runningCounts[h] = all.length - downtimeCounts[h];
        });
    });

    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: hourLabels,
            datasets: [
                {
                    label: 'Systems Running',
                    data: runningCounts,
                    backgroundColor: 'rgba(16, 185, 129, 0.7)',
                    borderColor: '#10b981',
                    borderWidth: 1,
                    borderRadius: 3,
                },
                {
                    label: 'Systems in Downtime',
                    data: downtimeCounts,
                    backgroundColor: 'rgba(239, 68, 68, 0.65)',
                    borderColor: '#ef4444',
                    borderWidth: 1,
                    borderRadius: 3,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { position: 'top', labels: { usePointStyle: true } },
                tooltip: {
                    callbacks: {
                        label: ctx => `${ctx.dataset.label}: ${ctx.parsed.y}`,
                    },
                },
            },
            scales: {
                x: {
                    stacked: true,
                    grid: { display: false },
                    ticks: { maxRotation: 45, font: { size: 10 } },
                },
                y: {
                    stacked: true,
                    grid: { color: '#f1f5f9' },
                    ticks: { stepSize: 1, font: { size: 11 } },
                    title: { display: true, text: 'Equipment Count' },
                },
            },
        },
    });
}

// ─── RECOVERY CHART ────────────────────────────────────────────────────────

function renderRecoveryChart(all) {
    const ctx = document.getElementById('recoveryChart').getContext('2d');

    const filtered = all.filter(eq => eq.recoveryMins.length > 0);
    const labels   = filtered.map(eq => eq.equipment.replace('CCTV ', 'C.'));
    const avgRec   = filtered.map(eq => {
        const r = eq.recoveryMins;
        return Math.round(r.reduce((a, b) => a + b, 0) / r.length);
    });
    const colors   = avgRec.map(v => v <= 10 ? '#10b981' : v <= 20 ? '#f59e0b' : '#ef4444');

    new Chart(ctx, {
        type: 'bar',
        data: {
            labels,
            datasets: [{
                label: 'Avg Recovery Time (min)',
                data: avgRec,
                backgroundColor: colors,
                borderRadius: 4,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            indexAxis: 'y',
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: { label: ctx => `${ctx.parsed.x} min avg recovery` },
                },
            },
            scales: {
                x: {
                    grid: { color: '#f1f5f9' },
                    ticks: { font: { size: 10 } },
                    title: { display: true, text: 'Minutes' },
                },
                y: { grid: { display: false }, ticks: { font: { size: 10 } } },
            },
        },
    });
}

// ─── CLOCK ─────────────────────────────────────────────────────────────────

function startClock() {
    function tick() {
        const el = document.getElementById('clock');
        if (el) el.textContent = new Date().toTimeString().slice(0, 8);
    }
    tick();
    setInterval(tick, 1000);
}

// ─── MAIN INIT ─────────────────────────────────────────────────────────────

async function init() {
    startClock();

    // Try to fetch real CCTV log and enrich mock data
    let all = generateMockDowntimeData();

    try {
        const res  = await fetch('/api/cctv/log');
        const text = await res.text();
        const data = JSON.parse(text.replace(/: NaN/g, ': null'));

        // If real CCTV log has event data, could map it here.
        // For now mock data is used — real integration left as extension point.
        void data;
    } catch {
        // silently fall back to mock
    }

    populateKPIs(all);
    checkAlerts(all);
    renderTable(all);
    renderReliabilityBars(all);
    renderTimelineChart(all);
    renderRecoveryChart(all);

    const ts = document.getElementById('last-updated');
    if (ts) ts.textContent = 'Updated ' + new Date().toLocaleTimeString();
}

document.addEventListener('DOMContentLoaded', init);

// Refresh every 2 minutes
setInterval(() => {
    alertMessages.length = 0;
    document.getElementById('downtime-tbody').innerHTML = '';
    document.getElementById('reliability-list').innerHTML = '';
    init();
}, 2 * 60 * 1000);
