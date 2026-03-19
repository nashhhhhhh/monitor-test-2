async function initDashboard() {
    try {
        const res = await fetch('/api/checkweigher');
        const text = await res.text();
        const data = JSON.parse(text.replace(/: NaN/g, ': null'));
        renderKPIs(data);
        renderDiagnostics(data);
        renderCharts(data);
        renderWeightTrend(data);
        renderWeightLog(data);
        checkAlerts(data);
    } catch (e) { console.error('Checkweigher Error:', e); }
}

function renderKPIs(data) {
    document.getElementById('val-total').innerText        = data.summary.total_today.toLocaleString();
    document.getElementById('val-under').innerText        = data.summary.under_rejects.toLocaleString();
    document.getElementById('val-over').innerText         = data.summary.over_rejects.toLocaleString();
    document.getElementById('val-avg-weight').innerHTML   = `${data.summary.avg_weight_g.toFixed(1)}<span class="kpi-unit"> g</span>`;
    document.getElementById('val-pass-rate').innerHTML    = `${data.summary.pass_rate_pct.toFixed(1)}<span class="kpi-unit"> %</span>`;
    document.getElementById('kpi-target-label').innerText = `Target: ${data.spec.target_g}g ±${data.spec.tolerance_g}g`;

    const rejectRate = 100 - data.summary.pass_rate_pct;
    const giveaway   = data.summary.avg_weight_g - data.spec.target_g;

    document.getElementById('val-target').innerHTML      = `${data.spec.target_g.toFixed(0)}<span class="kpi-unit"> g</span>`;
    document.getElementById('kpi-spec-label').innerText  = `Spec: ${data.spec.lower_g}g – ${data.spec.upper_g}g`;
    document.getElementById('val-reject-rate').innerHTML = `${rejectRate.toFixed(1)}<span class="kpi-unit"> %</span>`;
    document.getElementById('val-giveaway').innerHTML    = `${giveaway >= 0 ? '+' : ''}${giveaway.toFixed(1)}<span class="kpi-unit"> g</span>`;
    document.getElementById('val-stddev').innerHTML      = `${data.summary.std_dev_g ?? '--'}<span class="kpi-unit"> g</span>`;
    document.getElementById('val-throughput').innerHTML  = `${data.summary.throughput_per_min ?? '--'}<span class="kpi-unit">/min</span>`;

    document.getElementById('kpi-reject-card').className  = `kpi-card ${rejectRate > 5 ? 'highlight-red' : rejectRate > 3 ? 'highlight-warn' : 'highlight-green'}`;
    document.getElementById('kpi-giveaway-card').className = `kpi-card ${giveaway < 0 ? 'highlight-red' : giveaway > 3 ? 'highlight-warn' : 'highlight-green'}`;
}

function renderDiagnostics(data) {
    const units = [
        { id: 'cw01', label: 'Checkweigher CW-01', d: data.diagnostics.cw01 },
        { id: 'cw02', label: 'Checkweigher CW-02', d: data.diagnostics.cw02 }
    ];
    const pillClass = { running: 'active', idle: 'warning', fault: 'offline' };
    const pillLabel = { running: 'Running', idle: 'Idle', fault: 'Fault' };
    const calWarn   = d => d.last_cal_days > 10 ? 'color:#b45309' : 'color:#16a34a';

    document.getElementById('unit-status-list').innerHTML = units.map(({ label, d }) => `
        <div class="diag-group" style="margin-bottom:20px;">
            <h4 style="display:flex;justify-content:space-between;align-items:center;font-size:0.9rem;margin:0 0 12px 0;">
                ${label}
                <span class="status-pill ${pillClass[d.status]}">${pillLabel[d.status]}</span>
            </h4>
            <div class="diag-item"><span>Current Product</span>      <strong>${data.summary.shift_product}</strong></div>
            <div class="diag-item"><span>Conveyor Speed</span>       <strong>${d.speed_mpm} m/min</strong></div>
            <div class="diag-item"><span>Items Checked</span>        <strong>${d.items_checked.toLocaleString()}</strong></div>
            <div class="diag-item"><span>Last Calibration</span>     <strong style="${calWarn(d)}">${d.last_cal_days} day${d.last_cal_days !== 1 ? 's' : ''} ago</strong></div>
        </div>
    `).join('');
}

function renderCharts(data) {
    new Chart(document.getElementById('weightDistChart'), {
        type: 'bar',
        data: { labels: data.distribution.map(b => b.label), datasets: [{ label: 'Item Count', data: data.distribution.map(b => b.count), backgroundColor: data.distribution.map(b => b.zone === 'under' ? 'rgba(239,68,68,0.75)' : b.zone === 'over' ? 'rgba(245,158,11,0.75)' : 'rgba(16,185,129,0.75)'), borderRadius: 3 }] },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { title: { display: true, text: 'Weight (g)' }, ticks: { maxRotation: 45, font: { size: 9 } } }, y: { title: { display: true, text: 'Count' }, beginAtZero: true } } }
    });
    const labels = data.readings.map(r => r.time);
    new Chart(document.getElementById('passRateTrendChart'), {
        type: 'line',
        data: { labels, datasets: [
            { label: 'Pass Rate (%)', data: data.readings.map(r => r.pass_rate_pct), borderColor: '#8b5cf6', backgroundColor: 'rgba(139,92,246,0.08)', fill: true, tension: 0.4 },
            { label: 'Min Target (97%)', data: data.readings.map(() => 97), borderColor: '#ef4444', borderDash: [5,5], borderWidth: 1.5, pointRadius: 0, fill: false }
        ] },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 10 } } } }, scales: { y: { title: { display: true, text: 'Pass Rate (%)' }, min: 90, max: 100 } } }
    });
}

function renderWeightTrend(data) {
    const labels    = data.readings.map(r => r.time);
    const weights   = data.readings.map(r => r.avg_weight_g ?? null);
    const movingAvg = weights.map((_, i) => {
        const slice = weights.slice(Math.max(0, i - 2), i + 1).filter(v => v !== null);
        return slice.length ? +(slice.reduce((a, b) => a + b, 0) / slice.length).toFixed(1) : null;
    });
    new Chart(document.getElementById('weightTrendChart'), {
        type: 'line',
        data: { labels, datasets: [
            { label: 'Avg Weight (g)',         data: weights,   borderColor: '#3b82f6', backgroundColor: 'rgba(59,130,246,0.08)', fill: true,  tension: 0.4, pointRadius: 4 },
            { label: '3-pt Moving Avg',        data: movingAvg, borderColor: '#8b5cf6', borderDash: [4,4], borderWidth: 1.5, pointRadius: 0, fill: false, tension: 0.4 },
            { label: `Target (${data.spec.target_g}g)`, data: labels.map(() => data.spec.target_g), borderColor: '#16a34a', borderDash: [6,3], borderWidth: 2,   pointRadius: 0, fill: false },
            { label: `Upper (${data.spec.upper_g}g)`,   data: labels.map(() => data.spec.upper_g),  borderColor: '#f59e0b', borderDash: [3,3], borderWidth: 1.5, pointRadius: 0, fill: false },
            { label: `Lower (${data.spec.lower_g}g)`,   data: labels.map(() => data.spec.lower_g),  borderColor: '#ef4444', borderDash: [3,3], borderWidth: 1.5, pointRadius: 0, fill: false }
        ] },
        options: {
            responsive: true, maintainAspectRatio: false,
            plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 10 } } } },
            scales: { y: { title: { display: true, text: 'Weight (g)' }, min: data.spec.target_g - 12, max: data.spec.target_g + 12 } }
        }
    });
}

function renderWeightLog(data) {
    const tbody = document.getElementById('weight-log-body');
    tbody.innerHTML = data.recent_log.map(entry => {
        const variance = (entry.weight_g - data.spec.target_g).toFixed(1);
        const sign = variance >= 0 ? '+' : '';
        let status, badgeClass;
        if (entry.weight_g < data.spec.lower_g)      { status = 'UNDER'; badgeClass = 'reject'; }
        else if (entry.weight_g > data.spec.upper_g) { status = 'OVER';  badgeClass = 'warn'; }
        else                                          { status = 'PASS';  badgeClass = 'pass'; }
        return `<tr><td>${entry.time}</td><td>${entry.product}</td><td>${entry.weight_g.toFixed(1)}</td><td style="color:${Math.abs(variance) > data.spec.tolerance_g ? '#ef4444' : '#10b981'}">${sign}${variance}g</td><td><span class="badge ${badgeClass}">${status}</span></td></tr>`;
    }).join('');
}

function checkAlerts(data) {
    const container  = document.getElementById('alert-container');
    const rejectRate = 100 - data.summary.pass_rate_pct;
    const giveaway   = data.summary.avg_weight_g - data.spec.target_g;
    const items = [];

    if (rejectRate > 5)
        items.push({ cls: 'red',    icon: '🔴', msg: `Reject rate critical: ${rejectRate.toFixed(1)}% exceeds 5% threshold — inspect reject mechanism` });
    if (data.summary.avg_weight_g < data.spec.target_g)
        items.push({ cls: 'red',    icon: '🔴', msg: `Average weight below target: ${data.summary.avg_weight_g}g vs ${data.spec.target_g}g — underweight risk` });
    if (giveaway > 3)
        items.push({ cls: 'yellow', icon: '⚠',  msg: `Overfill detected: avg is +${giveaway.toFixed(1)}g above target — review filler calibration` });
    if (data.summary.pass_rate_pct < 97 && rejectRate <= 5)
        items.push({ cls: 'yellow', icon: '⚠',  msg: `Pass rate below 97%: currently ${data.summary.pass_rate_pct.toFixed(1)}%` });
    if (data.summary.under_rejects > 50)
        items.push({ cls: 'yellow', icon: '⚠',  msg: `High under-weight count: ${data.summary.under_rejects} rejects this shift` });
    if (items.length === 0)
        items.push({ cls: 'green',  icon: '✓',  msg: `All metrics within normal range — pass rate ${data.summary.pass_rate_pct.toFixed(1)}%, reject rate ${rejectRate.toFixed(1)}%` });

    container.innerHTML = items.map(i =>
        `<div class="alert-item ${i.cls}"><span>${i.icon}</span><span>${i.msg}</span></div>`
    ).join('');
}

initDashboard();
setInterval(initDashboard, 60000);
