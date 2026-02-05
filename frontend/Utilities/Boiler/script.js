async function initDashboard() {
    try {
        const response = await fetch('/api/boiler');
        const data = await response.json();

        // 1. Diagnostics & Status Calculation
        const stages = {
            'b01-1': data.boiler_01.stage_1_runtime,
            'b01-2': data.boiler_01.stage_2_runtime,
            'b01-3': data.boiler_01.stage_3_runtime,
            'b02-1': data.boiler_02.stage_1_runtime,
            'b02-2': data.boiler_02.stage_2_runtime
        };

        const statusMap = {};
        for (const [key, arr] of Object.entries(stages)) {
            const isRunning = arr.length > 1 && arr[arr.length - 1].runtime > arr[arr.length - 2].runtime;
            statusMap[key] = isRunning;
            const dot = document.getElementById(`dot-${key}`);
            if (dot) dot.className = isRunning ? 'dot active' : 'dot offline';
        }

        const b1Active = statusMap['b01-1'] || statusMap['b01-2'] || statusMap['b01-3'];
        const b2Active = statusMap['b02-1'] || statusMap['b02-2'];

        const updateMaster = (id, active) => {
            const el = document.getElementById(`status-${id}-master`);
            if (el) {
                el.innerText = active ? "ONLINE" : "STANDBY";
                el.className = active ? "status-pill active" : "status-pill warning";
            }
        };
        updateMaster('b01', b1Active);
        updateMaster('b02', b2Active);

        // 2. Consumption & Efficiency (B1=Indirect, B2=Direct)
        const gas = data.consumption.gas_total_kg;
        const deltaGas = (gas[gas.length - 1]?.gas || 0) - (gas[0]?.gas || 0);
        const latestDirect = data.consumption.direct_steam_kg[data.consumption.direct_steam_kg.length - 1]?.steam || 0;
        const latestIndirect = data.consumption.indirect_steam_kg[data.consumption.indirect_steam_kg.length - 1]?.steam || 0;

        document.getElementById('val-gas').innerText = (gas[gas.length - 1]?.gas || 0).toLocaleString();
        document.getElementById('val-steam').innerText = (latestDirect + latestIndirect).toLocaleString();
        
        const deltaDirect = latestDirect - (data.consumption.direct_steam_kg[0]?.steam || 0);
        const deltaIndirect = latestIndirect - (data.consumption.indirect_steam_kg[0]?.steam || 0);

        document.getElementById('val-eff-b1').innerText = deltaGas > 0 ? (deltaIndirect / (deltaGas * 0.5)).toFixed(2) : "0.00";
        document.getElementById('val-eff-b2').innerText = deltaGas > 0 ? (deltaDirect / (deltaGas * 0.5)).toFixed(2) : "0.00";

        // 3. Energy Logic
        const b1Energy = data.consumption.indirect_energy_kwh;
        const b2Energy = data.consumption.direct_energy_kwh;
        const b1Latest = b1Energy[b1Energy.length - 1]?.energy || 0;
        const b2Latest = b2Energy[b2Energy.length - 1]?.energy || 0;
        const totalEnergy = b1Latest + b2Latest;

        document.getElementById('val-energy-total').innerText = totalEnergy.toLocaleString();
        document.getElementById('val-energy-b1').innerText = b1Latest.toLocaleString() + " kWh";
        document.getElementById('val-energy-b2').innerText = b2Latest.toLocaleString() + " kWh";

        if (totalEnergy > 0) {
            document.getElementById('bar-energy-b1').style.width = ((b1Latest / totalEnergy) * 100) + "%";
            document.getElementById('bar-energy-b2').style.width = ((b2Latest / totalEnergy) * 100) + "%";
        }

        renderCharts(data);
    } catch (e) {
        console.error("Initialization Error:", e);
    }
}

function renderCharts(data) {
    // 1. Detailed Stage Runtime Chart
    const ctx = document.getElementById('runtimeChart');
    if (ctx) {
        new Chart(ctx, {
            type: 'line',
            data: {
                labels: data.boiler_01.stage_1_runtime.map(d => d.time),
                datasets: [
                    // Boiler 01 Stages (Green Tones)
                    { label: 'B1 Stage 1', data: data.boiler_01.stage_1_runtime.map(d => d.runtime), borderColor: '#10b981', tension: 0.3 },
                    { label: 'B1 Stage 2', data: data.boiler_01.stage_2_runtime.map(d => d.runtime), borderColor: '#34d399', tension: 0.3 },
                    { label: 'B1 Stage 3', data: data.boiler_01.stage_3_runtime.map(d => d.runtime), borderColor: '#6ee7b7', tension: 0.3 },
                    // Boiler 02 Stages (Blue Tones)
                    { label: 'B2 Stage 1', data: data.boiler_02.stage_1_runtime.map(d => d.runtime), borderColor: '#3b82f6', tension: 0.3 },
                    { label: 'B2 Stage 2', data: data.boiler_02.stage_2_runtime.map(d => d.runtime), borderColor: '#60a5fa', tension: 0.3 }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 10 } } } },
                scales: { y: { title: { display: true, text: 'Hours' } } }
            }
        });
    }

    // 2. Consumption Chart
    const ctx2 = document.getElementById('consumptionChart');
    if (ctx2) {
        new Chart(ctx2, {
            type: 'line',
            data: {
                labels: data.consumption.gas_total_kg.map(d => d.time),
                datasets: [
                    { label: 'Gas (kg)', data: data.consumption.gas_total_kg.map(d => d.gas), borderColor: '#f59e0b', yAxisID: 'y' },
                    { 
                        label: 'Steam (kg)', 
                        data: data.consumption.direct_steam_kg.map((d, i) => d.steam + (data.consumption.indirect_steam_kg[i]?.steam || 0)), 
                        borderColor: '#6366f1', 
                        yAxisID: 'y1' 
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: { position: 'left', title: { display: true, text: 'Gas (kg)' } },
                    y1: { position: 'right', grid: { drawOnChartArea: false }, title: { display: true, text: 'Steam (kg)' } }
                }
            }
        });
    }
}

setInterval(() => { 
    const clock = document.getElementById('clock');
    if (clock) clock.innerText = new Date().toLocaleTimeString(); 
}, 1000);

document.addEventListener('DOMContentLoaded', initDashboard);