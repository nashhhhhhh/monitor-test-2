async function initDashboard() {
    try {
        const res = await fetch('/api/steambox');
        const text = await res.text();
        const data = JSON.parse(text.replace(/: NaN/g, ': null'));
        renderKPIs(data);
        renderDiagnostics(data);
        renderCharts(data);
        checkAlerts(data);
    } catch (e) { console.error('Steambox Error:', e); }
}

function renderKPIs(data) {
    const latest = data.readings[data.readings.length - 1];
    document.getElementById('val-chamber-temp').innerHTML = `${latest.avg_chamber_temp.toFixed(1)}<span class="kpi-unit"> °C</span>`;
    document.getElementById('val-pressure').innerHTML     = `${latest.pressure_bar.toFixed(2)}<span class="kpi-unit"> bar</span>`;
    document.getElementById('val-units').innerText        = data.summary.units_today;
    document.getElementById('val-cook-time').innerHTML    = `${data.summary.avg_cook_min.toFixed(1)}<span class="kpi-unit"> min</span>`;
    document.getElementById('val-door-opens').innerText   = data.summary.door_opens_today;
}

function renderDiagnostics(data) {
    const setDot  = (id, s) => { const e = document.getElementById(id); if (e) e.className = 'dot ' + s; };
    const setPill = (id, label, s) => { const e = document.getElementById(id); if (e) { e.innerText = label; e.className = 'status-pill ' + s; } };
    ['sb01','sb02','sb03'].forEach(u => {
        const d = data.diagnostics[u];
        setDot(`dot-${u}-heat`,  d.heating_element ? 'active' : 'offline');
        setDot(`dot-${u}-steam`, d.steam_generator ? 'active' : 'offline');
        setDot(`dot-${u}-valve`, d.pressure_valve  ? 'active' : 'warning');
        setDot(`dot-${u}-door`,  d.door_seal       ? 'active' : 'warning');
        const ok = d.heating_element && d.steam_generator;
        const warn = !d.pressure_valve || !d.door_seal;
        setPill(`status-${u}`, !ok ? 'OFFLINE' : warn ? 'FAULT' : 'ONLINE', !ok ? 'offline' : warn ? 'warning' : 'active');
    });
}

function renderCharts(data) {
    const labels = data.readings.map(r => r.time);
    new Chart(document.getElementById('tempProfileChart'), {
        type: 'line',
        data: { labels, datasets: [
            { label: 'SB-01 (°C)', data: data.readings.map(r => r.sb01_temp), borderColor: '#3b82f6', backgroundColor: 'rgba(59,130,246,0.06)', fill: true, tension: 0.4 },
            { label: 'SB-02 (°C)', data: data.readings.map(r => r.sb02_temp), borderColor: '#10b981', backgroundColor: 'rgba(16,185,129,0.06)', fill: true, tension: 0.4 },
            { label: 'SB-03 (°C)', data: data.readings.map(r => r.sb03_temp), borderColor: '#8b5cf6', backgroundColor: 'rgba(139,92,246,0.06)', fill: true, tension: 0.4 },
            { label: 'Min Target (95°C)', data: data.readings.map(() => 95), borderColor: '#ef4444', borderDash: [6,4], borderWidth: 1.5, pointRadius: 0, fill: false }
        ] },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 10 } } } }, scales: { y: { title: { display: true, text: 'Temp (°C)' }, min: 80 } } }
    });
    new Chart(document.getElementById('throughputChart'), {
        type: 'bar',
        data: { labels: data.hourly_throughput.map(h => h.hour), datasets: [{ label: 'Units', data: data.hourly_throughput.map(h => h.units), backgroundColor: '#10b981', borderRadius: 4 }] },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { title: { display: true, text: 'Trays' }, beginAtZero: true } } }
    });
    new Chart(document.getElementById('pressureChart'), {
        type: 'line',
        data: { labels, datasets: [
            { label: 'Steam Pressure (bar)', data: data.readings.map(r => r.pressure_bar), borderColor: '#f59e0b', backgroundColor: 'rgba(245,158,11,0.08)', fill: true, tension: 0.4 },
            { label: 'Max Safe (3.5)', data: data.readings.map(() => 3.5), borderColor: '#ef4444', borderDash: [5,5], borderWidth: 1.5, pointRadius: 0, fill: false },
            { label: 'Min Oper. (2.0)', data: data.readings.map(() => 2.0), borderColor: '#94a3b8', borderDash: [5,5], borderWidth: 1.5, pointRadius: 0, fill: false }
        ] },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 10 } } } }, scales: { y: { title: { display: true, text: 'Pressure (bar)' }, min: 0, max: 5 } } }
    });
}

function checkAlerts(data) {
    const latest = data.readings[data.readings.length - 1];
    const alerts = [];
    if (latest.avg_chamber_temp < 95) alerts.push(`Chamber temp below target: ${latest.avg_chamber_temp.toFixed(1)}°C`);
    if (latest.pressure_bar > 3.5)   alerts.push(`Pressure above safe limit: ${latest.pressure_bar.toFixed(2)} bar`);
    if (latest.pressure_bar < 2.0)   alerts.push(`Pressure below operating range: ${latest.pressure_bar.toFixed(2)} bar`);
    if (alerts.length) {
        document.getElementById('alert-msg').innerText = alerts.join('  |  ');
        document.getElementById('alert-banner').classList.add('visible');
    }
}

initDashboard();
setInterval(initDashboard, 60000);
