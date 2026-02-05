async function initDashboard() {
    try {
        // Fetch data from your Spiral API endpoint
        const response = await fetch('/api/spiral_blast_freezer');
        const data = await response.json();

        // 1. Drive Status & Frequency Calculations
        const drives = {
            'sf1-main': data.spiral_01.main_drive, // Array of {time, hz}
            'sf1-sub': data.spiral_01.sub_drive,
            'sf2-main': data.spiral_02.main_drive
        };

        const statusMap = {};
        for (const [key, arr] of Object.entries(drives)) {
            const latestHz = arr[arr.length - 1]?.hz || 0;
            const isRunning = latestHz > 0.5;
            statusMap[key] = isRunning;

            // Update Hz text and Status Dot
            document.getElementById(`${key}-hz`).innerText = latestHz.toFixed(1);
            const dot = document.getElementById(`dot-${key}`);
            if (dot) dot.className = isRunning ? 'dot active' : 'dot offline';
        }

        // Master Status Pills
        const updateMaster = (id, active) => {
            const el = document.getElementById(`status-${id}-master`);
            if (el) {
                el.innerText = active ? "RUNNING" : "STANDBY";
                el.className = active ? "status-pill active" : "status-pill warning";
            }
        };
        updateMaster('sf01', statusMap['sf1-main'] || statusMap['sf1-sub']);
        updateMaster('sf02', statusMap['sf2-main']);

        // 2. Production & Efficiency
        const prodData = data.conveyor.accumulate_pcs;
        const totalPcs = prodData[prodData.length - 1]?.pcs || 0;
        const capacity = data.conveyor.current_capacity || 0;

        document.getElementById('val-production').innerText = totalPcs.toLocaleString();
        document.getElementById('val-capacity').innerText = capacity + " Pcs/Min";

        // 3. Energy & Efficiency
        // Summing MLF (Freezer) and MDB (Compressor) energy
        const energyTotal = (data.energy.mlf_total_kwh || 0) + (data.energy.mdb_total_kwh || 0);
        document.getElementById('val-energy-total').innerText = energyTotal.toLocaleString() + " kWh";

        const eff = energyTotal > 0 ? (totalPcs / energyTotal).toFixed(2) : "0.00";
        document.getElementById('val-eff-calc').innerText = eff;

        // 4. Temperatures
        const t1 = data.spiral_01.temp_tef01[data.spiral_01.temp_tef01.length - 1]?.temp || 0;
        const t2 = data.spiral_01.temp_tef02[data.spiral_01.temp_tef02.length - 1]?.temp || 0;
        document.getElementById('val-temp-avg').innerText = ((t1 + t2) / 2).toFixed(1) + "°C";

        // 5. Populate Refrigeration Table
        const tableBody = document.getElementById('refrig-table-body');
        tableBody.innerHTML = data.refrigeration.receivers.map(r => `
            <tr>
                <td>${r.name}</td>
                <td>${r.temp.toFixed(1)}°C</td>
                <td>${r.pressure.toFixed(2)} kg/cm²</td>
                <td><span class="status-pill ${r.temp < -20 ? 'active' : 'warning'}">
                    ${r.temp < -20 ? 'OPTIMAL' : 'WARMING'}
                </span></td>
            </tr>
        `).join('');

        renderCharts(data);
    } catch (e) {
        console.error("Dashboard Load Error:", e);
    }
}

function renderCharts(data) {
    const ctx = document.getElementById('performanceChart');
    if (!ctx) return;

    new Chart(ctx, {
        type: 'line',
        data: {
            labels: data.spiral_01.temp_tef01.map(d => d.time),
            datasets: [
                { 
                    label: 'SF01 Temp (°C)', 
                    data: data.spiral_01.temp_tef01.map(d => d.temp), 
                    borderColor: '#3b82f6', 
                    yAxisID: 'y',
                    tension: 0.3 
                },
                { 
                    label: 'Capacity (Pcs/Min)', 
                    data: data.conveyor.capacity_history.map(d => d.val), 
                    borderColor: '#10b981', 
                    yAxisID: 'y1',
                    fill: true,
                    backgroundColor: 'rgba(16, 185, 129, 0.1)'
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: { type: 'linear', position: 'left', title: { display: true, text: 'Temp °C' } },
                y1: { type: 'linear', position: 'right', grid: { drawOnChartArea: false }, title: { display: true, text: 'Pcs/Min' } }
            }
        }
    });
}

// Clock UI
setInterval(() => {
    const clock = document.getElementById('clock');
    if (clock) clock.innerText = new Date().toLocaleTimeString();
}, 1000);

document.addEventListener('DOMContentLoaded', initDashboard);