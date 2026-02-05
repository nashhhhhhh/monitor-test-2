async function initDashboard() {
    try {
        // Assuming API returns MDB and Generator specific fields
        const response = await fetch('/api/power-systems');
        const data = await response.json();

        // 1. Update Generator Status
        const genRunning = data.generator.engine_speed > 0;
        const genStatusEl = document.getElementById('status-gen-master');
        genStatusEl.innerText = genRunning ? "RUNNING (LOAD)" : "STANDBY (READY)";
        genStatusEl.className = genRunning ? "status-pill active" : "status-pill warning";
        
        document.getElementById('dot-gen-engine').className = genRunning ? 'dot active' : 'dot offline';

        // 2. Power Calculations
        const totalKW = data.mdb1.total_kw + data.mdb2.total_kw;
        document.getElementById('val-total-kw').innerText = totalKW.toFixed(1);
        document.getElementById('val-avg-pf').innerText = data.facility.avg_power_factor.toFixed(2);

        // 3. Fuel & Maintenance
        const fuelPct = data.generator.fuel_level_pct;
        document.getElementById('val-fuel-pct').innerText = fuelPct + "%";
        document.getElementById('val-fuel-liters').innerText = data.generator.fuel_liters + " L remaining";
        
        // Progress Bars
        const utilityBar = document.getElementById('bar-utility');
        const genBar = document.getElementById('bar-gen');
        
        if (genRunning) {
            utilityBar.style.width = "0%";
            genBar.style.width = data.generator.load_factor + "%";
            document.getElementById('val-util-load').innerText = "0%";
            document.getElementById('val-gen-load').innerText = data.generator.load_factor + "%";
        } else {
            utilityBar.style.width = "100%";
            genBar.style.width = "0%";
            document.getElementById('val-util-load').innerText = "ACTIVE";
            document.getElementById('val-gen-load').innerText = "0%";
        }

        renderPowerCharts(data);
    } catch (e) {
        console.error("MDB Dashboard Error:", e);
    }
}

function renderPowerCharts(data) {
    // Load Profile Chart
    const ctxLoad = document.getElementById('loadChart').getContext('2d');
    new Chart(ctxLoad, {
        type: 'line',
        data: {
            labels: data.history.timestamps,
            datasets: [{
                label: 'Facility Demand (kW)',
                data: data.history.total_kw,
                borderColor: '#eab308',
                backgroundColor: 'rgba(234, 179, 8, 0.1)',
                fill: true,
                tension: 0.4
            }]
        },
        options: { responsive: true, maintainAspectRatio: false }
    });

    // Voltage Stability Chart
    const ctxVolt = document.getElementById('voltageChart').getContext('2d');
    new Chart(ctxVolt, {
        type: 'line',
        data: {
            labels: data.history.timestamps,
            datasets: [
                { label: 'L1', data: data.history.v_l1, borderColor: '#ef4444', tension: 0.2 },
                { label: 'L2', data: data.history.v_l2, borderColor: '#3b82f6', tension: 0.2 },
                { label: 'L3', data: data.history.v_l3, borderColor: '#eab308', tension: 0.2 }
            ]
        },
        options: { 
            responsive: true, 
            maintainAspectRatio: false,
            scales: { y: { min: 210, max: 250 } } // Standard 230V range
        }
    });
}

document.addEventListener('DOMContentLoaded', initDashboard);