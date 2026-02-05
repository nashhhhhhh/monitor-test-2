async function initDashboard() {
    try {
        const response = await fetch('/api/boiler');
        const data = await response.json();

        // 1. Data References
        const gas = data.consumption.gas_total_kg;
        const direct = data.consumption.direct_steam_kg;
        const indirect = data.consumption.indirect_steam_kg;

        // 2. Sub-Boiler Status Mapping & Diagnostic Report
        const stages = {
            'b01-1': data.boiler_01.stage_1_runtime,
            'b01-2': data.boiler_01.stage_2_runtime,
            'b01-3': data.boiler_01.stage_3_runtime,
            'b02-1': data.boiler_02.stage_1_runtime,
            'b02-2': data.boiler_02.stage_2_runtime
        };

        const statusMap = {};
        for (const [key, arr] of Object.entries(stages)) {
            // Online if runtime increased in the last interval
            const isRunning = arr.length > 1 && arr[arr.length - 1].runtime > arr[arr.length - 2].runtime;
            statusMap[key] = isRunning;

            // Update Diagnostic Dots using CSS classes defined in your style.css
            const dot = document.getElementById(`dot-${key}`);
            if (dot) {
                dot.className = isRunning ? 'dot active' : 'dot offline';
                // Remove inline styles to let CSS handle the transitions/glow
                dot.style.backgroundColor = '';
                dot.style.boxShadow = '';
            }
        }

        // 3. Master Status Calculation (derived from stages)
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

        // 4. Totals & High-Impact Efficiency Calculations
        const latestGas = gas[gas.length - 1]?.gas || 0;
        const startGas = gas[0]?.gas || 0;
        const deltaGas = latestGas - startGas;

        const latestDirect = direct[direct.length - 1]?.steam || 0;
        const startDirect = direct[0]?.steam || 0;
        const deltaDirect = latestDirect - startDirect;

        const latestIndirect = indirect[indirect.length - 1]?.steam || 0;
        const startIndirect = indirect[0]?.steam || 0;
        const deltaIndirect = latestIndirect - startIndirect;

        // Update Top KPIs
        document.getElementById('val-gas').innerText = latestGas.toLocaleString();
        document.getElementById('val-steam').innerText = (latestDirect + latestIndirect).toLocaleString();

        // Overall Efficiency (Steam Out / Gas In)
        const sysEff = deltaGas > 0 ? ((deltaDirect + deltaIndirect) / deltaGas).toFixed(2) : "0.00";
        document.getElementById('val-eff-sys').innerText = sysEff;

        // Boiler-Specific Efficiencies (formatted the same as overall)
        // Note: Approximation assumes roughly 50% gas distribution if sub-meters are shared
        const b1Eff = deltaGas > 0 ? (deltaDirect / (deltaGas * 0.5)).toFixed(2) : "0.00";
        const b2Eff = deltaGas > 0 ? (deltaIndirect / (deltaGas * 0.5)).toFixed(2) : "0.00";

        document.getElementById('val-eff-b1').innerText = b1Eff;
        document.getElementById('val-eff-b2').innerText = b2Eff;

        // 5. Update UI Components
        renderCharts(data);
        populateTable(data);
        
    } catch (e) { 
        console.error("Dashboard Initialization Error:", e); 
    }
}

function renderCharts(data) {
    const ctx = document.getElementById('runtimeChart');
    if (!ctx) return;
    
    new Chart(ctx, {
        type: 'line',
        data: {
            labels: data.boiler_01.stage_1_runtime.map(d => d.time),
            datasets: [
                { label: 'B1-S1', data: data.boiler_01.stage_1_runtime.map(d => d.runtime), borderColor: '#3b82f6', tension: 0.3 },
                { label: 'B1-S2', data: data.boiler_01.stage_2_runtime.map(d => d.runtime), borderColor: '#60a5fa', tension: 0.3 },
                { label: 'B1-S3', data: data.boiler_01.stage_3_runtime.map(d => d.runtime), borderColor: '#93c5fd', tension: 0.3 },
                { label: 'B2-S1', data: data.boiler_02.stage_1_runtime.map(d => d.runtime), borderColor: '#10b981', tension: 0.3 },
                { label: 'B2-S2', data: data.boiler_02.stage_2_runtime.map(d => d.runtime), borderColor: '#34d399', tension: 0.3 }
            ]
        },
        options: { 
            responsive: true, 
            maintainAspectRatio: false,
            plugins: { legend: { position: 'bottom' } },
            scales: { y: { beginAtZero: false } }
        }
    });

    const ctx2 = document.getElementById('consumptionChart');
    if (ctx2) {
        new Chart(ctx2, {
            type: 'line',
            data: {
                labels: data.consumption.gas_total_kg.map(d => d.time),
                datasets: [
                    { label: 'Total Gas', data: data.consumption.gas_total_kg.map(d => d.gas), borderColor: '#f59e0b', yAxisID: 'y' },
                    { 
                        label: 'Combined Steam', 
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
                    y: { type: 'linear', position: 'left', title: { display: true, text: 'Gas (kg)' } },
                    y1: { type: 'linear', position: 'right', grid: { drawOnChartArea: false }, title: { display: true, text: 'Steam (kg)' } }
                }
            }
        });
    }
}

function populateTable(data) {
    const body = document.getElementById('data-log-body');
    if (!body) return;
    
    // Get latest 8 entries for the log
    const logs = data.consumption.gas_total_kg.slice(-8).reverse();
    const directLogs = data.consumption.direct_steam_kg.slice(-8).reverse();
    const indirectLogs = data.consumption.indirect_steam_kg.slice(-8).reverse();
    
    const b1Status = document.getElementById('status-b01-master')?.innerText || "OFFLINE";
    const b2Status = document.getElementById('status-b02-master')?.innerText || "OFFLINE";

    body.innerHTML = logs.map((log, i) => `
        <tr>
            <td>${log.time}</td>
            <td>${log.gas.toLocaleString()}</td>
            <td>${(directLogs[i]?.steam || 0).toLocaleString()}</td>
            <td>${(indirectLogs[i]?.steam || 0).toLocaleString()}</td>
            <td><span class="status-pill ${b1Status === 'ONLINE' ? 'active' : 'warning'}">${b1Status}</span></td>
            <td><span class="status-pill ${b2Status === 'ONLINE' ? 'active' : 'warning'}">${b2Status}</span></td>
        </tr>
    `).join('');
}

// Startup
document.addEventListener('DOMContentLoaded', initDashboard);