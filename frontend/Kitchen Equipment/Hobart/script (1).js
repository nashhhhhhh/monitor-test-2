async function initDashboard() {
    try {
        const res = await fetch('/api/hobart');
        const text = await res.text();
        const data = JSON.parse(text.replace(/: NaN/g, ': null'));
        renderKPIs(data);
        renderDiagnostics(data);
        renderCharts(data);
        checkAlerts(data);
    } catch (e) {
        console.error('Hobart Dashboard Error:', e);
    }
}

function renderKPIs(data) {
    const latest = data.readings[data.readings.length - 1];
    document.getElementById('val-wash-temp').innerHTML  = `${latest.wash_temp.toFixed(1)}<span class="kpi-unit"> °C</span>`;
    document.getElementById('val-rinse-temp').innerHTML = `${latest.rinse_temp.toFixed(1)}<span class="kpi-unit"> °C</span>`;
    document.getElementById('val-sanitizer').innerHTML  = `${latest.sanitizer_ppm}<span class="kpi-unit"> ppm</span>`;
    document.getElementById('val-cycles').innerText     = data.summary.cycles_today;
    document.getElementById('val-water').innerHTML      = `${data.summary.water_usage_L}<span class="kpi-unit"> L</span>`;
    document.getElementById('val-tank-level').innerText = `${data.summary.tank_level_pct} %`;
    document.getElementById('val-detergent').innerText  = `${data.summary.detergent_ml} mL`;
    document.getElementById('val-cycle-time').innerHTML = `${data.summary.avg_cycle_min.toFixed(1)} <span class="kpi-unit">min</span>`;
    document.getElementById('bar-tank').style.width     = data.summary.tank_level_pct + '%';
    document.getElementById('bar-detergent').style.width = Math.min((data.summary.detergent_ml / 1000) * 100, 100) + '%';
    const tankBar = document.getElementById('bar-tank');
    tankBar.style.background = data.summary.tank_level_pct < 20 ? '#ef4444' : data.summary.tank_level_pct < 40 ? '#f59e0b' : '#8b5cf6';
}

function renderDiagnostics(data) {
    const setDot = (id, state) => { const el = document.getElementById(id); if (el) el.className = 'dot ' + state; };
    const setPill = (id, label, state) => { const el = document.getElementById(id); if (el) { el.innerText = label; el.className = 'status-pill ' + state; } };
    const d = data.diagnostics;
    setDot('dot-h01-wash',  d.unit_01.wash_arm   ? 'active' : 'offline');
    setDot('dot-h01-rinse', d.unit_01.rinse_pump ? 'active' : 'offline');
    setDot('dot-h01-dose',  d.unit_01.dose_pump  ? 'active' : 'warning');
    setDot('dot-h01-door',  d.unit_01.door_seal  ? 'active' : 'warning');
    const u01ok = d.unit_01.wash_arm && d.unit_01.rinse_pump;
    setPill('status-h01', u01ok ? (d.unit_01.dose_pump && d.unit_01.door_seal ? 'ONLINE' : 'FAULT') : 'OFFLINE', u01ok ? (d.unit_01.dose_pump && d.unit_01.door_seal ? 'active' : 'warning') : 'offline');
    setDot('dot-h02-wash',  d.unit_02.wash_arm   ? 'active' : 'offline');
    setDot('dot-h02-rinse', d.unit_02.rinse_pump ? 'active' : 'offline');
    setDot('dot-h02-dose',  d.unit_02.dose_pump  ? 'active' : 'warning');
    setDot('dot-h02-door',  d.unit_02.door_seal  ? 'active' : 'warning');
    const u02ok = d.unit_02.wash_arm && d.unit_02.rinse_pump;
    setPill('status-h02', u02ok ? (d.unit_02.dose_pump && d.unit_02.door_seal ? 'ONLINE' : 'FAULT') : 'OFFLINE', u02ok ? (d.unit_02.dose_pump && d.unit_02.door_seal ? 'active' : 'warning') : 'offline');
}

function renderCharts(data) {
    const labels = data.readings.map(r => r.time);
    new Chart(document.getElementById('tempTrendChart'), {
        type: 'line',
        data: {
            labels,
            datasets: [
                { label: 'Wash Temp (°C)', data: data.readings.map(r => r.wash_temp), borderColor: '#3b82f6', backgroundColor: 'rgba(59,130,246,0.07)', fill: true, tension: 0.4 },
                { label: 'Rinse Temp (°C)', data: data.readings.map(r => r.rinse_temp), borderColor: '#10b981', backgroundColor: 'rgba(16,185,129,0.07)', fill: true, tension: 0.4 },
                { label: 'Wash Target (60°C)', data: data.readings.map(() => 60), borderColor: '#3b82f6', borderDash: [5,5], borderWidth: 1, pointRadius: 0, fill: false },
                { label: 'Rinse Target (82°C)', data: data.readings.map(() => 82), borderColor: '#10b981', borderDash: [5,5], borderWidth: 1, pointRadius: 0, fill: false }
            ]
        },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 10 } } } }, scales: { y: { title: { display: true, text: 'Temperature (°C)' }, min: 40 } } }
    });
    new Chart(document.getElementById('cycleChart'), {
        type: 'bar',
        data: { labels: data.hourly_cycles.map(h => h.hour), datasets: [{ label: 'Cycles', data: data.hourly_cycles.map(h => h.cycles), backgroundColor: '#8b5cf6', borderRadius: 4 }] },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { title: { display: true, text: 'Cycle Count' }, beginAtZero: true } } }
    });
}

function checkAlerts(data) {
    const latest = data.readings[data.readings.length - 1];
    const alerts = [];
    if (latest.wash_temp < 60)            alerts.push(`Wash temp low: ${latest.wash_temp.toFixed(1)}°C`);
    if (latest.rinse_temp < 82)           alerts.push(`Rinse temp low: ${latest.rinse_temp.toFixed(1)}°C`);
    if (latest.sanitizer_ppm < 200)       alerts.push(`Sanitizer low: ${latest.sanitizer_ppm} ppm`);
    if (data.summary.tank_level_pct < 20) alerts.push(`Tank level critical: ${data.summary.tank_level_pct}%`);
    if (alerts.length) {
        document.getElementById('alert-msg').innerText = alerts.join('  |  ');
        document.getElementById('alert-banner').classList.add('visible');
    }
}

initDashboard();
setInterval(initDashboard, 60000);
