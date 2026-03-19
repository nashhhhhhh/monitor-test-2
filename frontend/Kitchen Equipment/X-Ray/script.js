async function initDashboard() {
    try {
        const res = await fetch('/api/xray');
        const text = await res.text();
        const data = JSON.parse(text.replace(/: NaN/g, ': null'));
        renderKPIs(data);
        renderDiagnostics(data);
        renderCharts(data);
        renderRejectLog(data);
        checkAlerts(data);
    } catch (e) { console.error('X-Ray Error:', e); }
}

function renderKPIs(data) {
    document.getElementById('val-inspected').innerText   = data.summary.inspected_today.toLocaleString();
    document.getElementById('val-rejects').innerText     = data.summary.rejects_today.toLocaleString();
    document.getElementById('val-reject-rate').innerHTML = `${data.summary.reject_rate_pct.toFixed(2)}<span class="kpi-unit"> %</span>`;
    document.getElementById('val-uptime').innerHTML      = `${data.summary.uptime_pct.toFixed(1)}<span class="kpi-unit"> %</span>`;
    document.getElementById('val-sensitivity').innerHTML = `${data.machine.sensitivity_mm}<span class="kpi-unit"> mm</span>`;
    const tubePct = Math.min((data.machine.tube_hours / data.machine.tube_max_hours) * 100, 100);
    document.getElementById('val-tube-hours').innerHTML   = `${data.machine.tube_hours.toLocaleString()} <span class="kpi-unit">hrs</span>`;
    document.getElementById('bar-tube-hours').style.width = tubePct + '%';
    document.getElementById('bar-tube-hours').style.background = tubePct > 85 ? '#ef4444' : tubePct > 70 ? '#f59e0b' : '#3b82f6';
    document.getElementById('tube-hours-label').innerText = `Replacement at ${data.machine.tube_max_hours.toLocaleString()} hrs`;
    document.getElementById('val-cal-days').innerHTML = `${data.machine.days_since_calibration} <span class="kpi-unit">days</span>`;
}

function renderDiagnostics(data) {
    const setDot  = (id, s) => { const e = document.getElementById(id); if (e) e.className = 'dot ' + s; };
    const setPill = (id, label, s) => { const e = document.getElementById(id); if (e) { e.innerText = label; e.className = 'status-pill ' + s; } };
    const d = data.diagnostics;
    setDot('dot-xr01-tube',   d.xray_tube      ? 'active' : 'offline');
    setDot('dot-xr01-belt',   d.conveyor_belt  ? 'active' : 'offline');
    setDot('dot-xr01-algo',   d.detection_algo ? 'active' : 'warning');
    setDot('dot-xr01-reject', d.reject_mech    ? 'active' : 'offline');
    setDot('dot-xr01-shield', d.shielding_ok   ? 'active' : 'offline');
    const critical = d.xray_tube && d.conveyor_belt && d.shielding_ok && d.reject_mech;
    setPill('status-xr01', !critical ? 'OFFLINE' : !d.detection_algo ? 'DEGRADED' : 'ONLINE', !critical ? 'offline' : !d.detection_algo ? 'warning' : 'active');
}

const _charts = {};

function renderCharts(data) {
    const labels = data.readings.map(r => r.time);
    if (_charts.rejectRate) _charts.rejectRate.destroy();
    _charts.rejectRate = new Chart(document.getElementById('rejectRateChart'), {
        type: 'line',
        data: { labels, datasets: [
            { label: 'Rejection Rate (%)', data: data.readings.map(r => r.reject_rate_pct), borderColor: '#ef4444', backgroundColor: 'rgba(239,68,68,0.07)', fill: true, tension: 0.4 },
            { label: 'Alert Threshold (2%)', data: data.readings.map(() => 2.0), borderColor: '#f59e0b', borderDash: [6,4], borderWidth: 1.5, pointRadius: 0, fill: false }
        ] },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 10 } } } }, scales: { y: { title: { display: true, text: 'Rejection Rate (%)' }, beginAtZero: true } } }
    });
    if (_charts.throughput) _charts.throughput.destroy();
    _charts.throughput = new Chart(document.getElementById('throughputChart'), {
        type: 'bar',
        data: { labels: data.hourly_throughput.map(h => h.hour), datasets: [
            { label: 'Inspected', data: data.hourly_throughput.map(h => h.inspected), backgroundColor: '#10b981', borderRadius: 4, stack: 'a' },
            { label: 'Rejected',  data: data.hourly_throughput.map(h => h.rejected),  backgroundColor: '#ef4444', borderRadius: 4, stack: 'a' }
        ] },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 10 } } } }, scales: { y: { title: { display: true, text: 'Items' }, beginAtZero: true } } }
    });
}

function renderRejectLog(data) {
    const tbody = document.getElementById('reject-log-body');
    if (!data.reject_log || data.reject_log.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;color:var(--text-muted)">No rejects today</td></tr>';
        return;
    }
    tbody.innerHTML = data.reject_log.map(e => `<tr><td>${e.time}</td><td>${e.product}</td><td>${e.detection_type}</td><td><span class="badge reject">REJECTED</span></td></tr>`).join('');
}

function checkAlerts(data) {
    const alerts = [];
    if (data.summary.reject_rate_pct > 2) alerts.push(`Rejection rate elevated: ${data.summary.reject_rate_pct.toFixed(2)}%`);
    if (data.machine.days_since_calibration > 30) alerts.push(`Calibration overdue: ${data.machine.days_since_calibration} days`);
    const tubePct = (data.machine.tube_hours / data.machine.tube_max_hours) * 100;
    if (tubePct > 85) alerts.push(`X-Ray tube near end of life: ${tubePct.toFixed(0)}%`);
    if (alerts.length) {
        document.getElementById('alert-msg').innerText = alerts.join('  |  ');
        document.getElementById('alert-banner').classList.add('visible');
    }
}

initDashboard();
setInterval(initDashboard, 60000);
