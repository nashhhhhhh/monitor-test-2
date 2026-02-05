async function initDashboard() {
    try {
        const response = await fetch('/api/boiler');
        const data = await response.json();

        // 1. Update KPIs
        const gasData = data.consumption.gas_total_kg;
        const steamDirect = data.consumption.direct_steam_kg;
        const steamIndirect = data.consumption.indirect_steam_kg;

        const latestGas = gasData[gasData.length - 1]?.gas || 0;
        const latestSteam = (steamDirect[steamDirect.length - 1]?.steam || 0) + 
                          (steamIndirect[steamIndirect.length - 1]?.steam || 0);

        document.getElementById('val-gas').innerText = latestGas.toLocaleString() + " kg";
        document.getElementById('val-steam').innerText = latestSteam.toLocaleString() + " kg";

        // Calculate Efficiency (Last 24 hours approximation)
        const deltaGas = latestGas - (gasData[0]?.gas || latestGas);
        const deltaSteam = latestSteam - ((steamDirect[0]?.steam || 0) + (steamIndirect[0]?.steam || 0));
        const efficiency = deltaGas > 0 ? (deltaSteam / deltaGas).toFixed(2) : "0.00";
        document.getElementById('val-efficiency').innerText = efficiency;

        // Status Pill Logic
        const b01Status = document.getElementById('status-b01');
        const b1rt = data.boiler_01.stage_1_runtime;
        const isRunning = b1rt[b1rt.length-1]?.runtime > b1rt[b1rt.length-2]?.runtime;
        b01Status.innerText = isRunning ? "ACTIVE" : "STANDBY";
        b01Status.className = isRunning ? "status-pill active" : "status-pill warning";

        // 2. Render Charts
        renderCharts(data);
        
        // 3. Populate Table
        populateTable(data);

    } catch (err) {
        console.error("Dashboard Error:", err);
    }
}

function renderCharts(data) {
    // Runtime Chart
    new Chart(document.getElementById('runtimeChart'), {
        type: 'line',
        data: {
            labels: data.boiler_01.stage_1_runtime.map(d => d.time),
            datasets: [{
                label: 'B01 Stage 1',
                data: data.boiler_01.stage_1_runtime.map(d => d.runtime),
                borderColor: '#3b82f6',
                backgroundColor: 'rgba(59, 130, 246, 0.1)',
                fill: true,
                tension: 0.3
            }]
        },
        options: { 
            responsive: true, 
            maintainAspectRatio: false,
            plugins: { legend: { display: false } }
        }
    });

    // Consumption Correlation
    new Chart(document.getElementById('consumptionChart'), {
        type: 'line',
        data: {
            labels: data.consumption.gas_total_kg.map(d => d.time),
            datasets: [
                {
                    label: 'Gas (kg)',
                    data: data.consumption.gas_total_kg.map(d => d.gas),
                    borderColor: '#f59e0b',
                    yAxisID: 'y'
                },
                {
                    label: 'Steam (kg)',
                    data: data.consumption.direct_steam_kg.map((d, i) => d.steam + (data.consumption.indirect_steam_kg[i]?.steam || 0)),
                    borderColor: '#10b981',
                    yAxisID: 'y1'
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: { type: 'linear', position: 'left' },
                y1: { type: 'linear', position: 'right', grid: { drawOnChartArea: false } }
            }
        }
    });
}

function populateTable(data) {
    const body = document.getElementById('data-log-body');
    const logs = data.consumption.gas_total_kg.slice(-5).reverse();
    body.innerHTML = logs.map((log, i) => `
        <tr>
            <td>${log.time}</td>
            <td>${log.gas}</td>
            <td>${data.consumption.direct_steam_kg.slice(-5).reverse()[i]?.steam || 0}</td>
            <td>${data.boiler_01.stage_1_runtime.slice(-5).reverse()[i]?.runtime || 0}</td>
            <td><span class="status-pill active">OK</span></td>
        </tr>
    `).join('');
}

// Simple Clock
setInterval(() => {
    document.getElementById('clock').innerText = new Date().toLocaleTimeString();
}, 1000);

initDashboard();