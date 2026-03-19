async function initDashboard() {
    try {
        const res = await fetch('/api/checkweigher');
        const text = await res.text();
        const data = JSON.parse(text.replace(/: NaN/g, ': null'));
        renderKPIs(data);
        renderDiagnostics(data);
        renderCharts(data);
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
}

function renderDiagnostics(data) {
    const setDot  = (id, s) => { const e = document.getElementById(id); if (e) e.className = 'dot ' + s; };
    const setPill = (id, label, s) => { const e = document.getElementById(id); if (e) { e.innerText = label; e.className = 'status-pill ' + s; } };
    ['cw01','cw02'].forEach(u => {
        const d = data.diagnostics[u];
        setDot(`dot-${u}-lca`,    d.load_cell_a ? 'active' : 'offline');
        setDot(`dot-${u}-lcb`,    d.load_cell_b ? 'active' : 'offline');
        setDot(`dot-${u}-conv`,   d.conveyor    ? 'active' : 'offline');
        setDot(`dot-${u}-reject`, d.reject_mech ? 'active' : 'offline');
        setDot(`dot-${u}-zero`,   d.auto_zero   ? 'active' : 'warning');
        const critical = d.load_cell_a && d.load_cell_b && d.conveyor && d.reject_mech;
        setPill(`status-${u}`, !critical ? 'OFFLINE' : !d.auto_zero ? 'FAULT' : 'ONLINE', !critical ? 'offline' : !d.auto_zero ? 'warning' : 'active');
    });
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
    const alerts = [];
    if (data.summary.pass_rate_pct < 97) alerts.push(`Pass rate below target: ${data.summary.pass_rate_pct.toFixed(1)}%`);
    if (data.summary.under_rejects > 50) alerts.push(`High under-weight rejects: ${data.summary.under_rejects}`);
    if (alerts.length) {
        document.getElementById('alert-msg').innerText = alerts.join('  |  ');
        document.getElementById('alert-banner').classList.add('visible');
    }
}

initDashboard();
setInterval(initDashboard, 60000);
