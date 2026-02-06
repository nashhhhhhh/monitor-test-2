document.addEventListener("DOMContentLoaded", () => {
    // Store chart instances to prevent "Canvas already in use" errors
    let charts = {};

    async function loadWTPData() {
        try {
            console.log("💧 Syncing WTP Data...");
            const response = await fetch("/api/wtp");
            const data = await response.json();

            // 1. Update Numeric KPIs
            updateKPIs(data);

            // 2. Update Operational Summary Table
            updateWTPTable(data.flow_totals);

            // 3. Render/Update Charts
            
            // --- Chart 1: Pressure Trends (Line) ---
            renderChart('pressureChart', 'line', {
                labels: data.pressure.ro_supply.map(d => d.time).slice(-20),
                datasets: [
                    { 
                        label: 'RO Supply (bar)', 
                        data: data.pressure.ro_supply.map(d => d.bar).slice(-20), 
                        borderColor: '#3b82f6', 
                        tension: 0.3 
                    },
                    { 
                        label: 'Soft Water (bar)', 
                        data: data.pressure.soft_water.map(d => d.bar).slice(-20), 
                        borderColor: '#94a3b8', 
                        borderDash: [5, 5],
                        tension: 0.3 
                    }
                ]
            });

            // --- Chart 2: Source Distribution (Bar) ---
            const flow = data.flow_totals;
            renderChart('flowDistributionChart', 'bar', {
                labels: ['Deep Well', 'Soft Water 1', 'Soft Water 2', 'RO Total'],
                datasets: [{
                    label: 'Latest Meter Reading (m³)',
                    data: [
                        flow.deep_well.slice(-1)[0]?.m3 || 0,
                        flow.soft_water_1.slice(-1)[0]?.m3 || 0,
                        flow.soft_water_2.slice(-1)[0]?.m3 || 0,
                        flow.ro_water.slice(-1)[0]?.m3 || 0
                    ],
                    backgroundColor: ['#1e293b', '#3b82f6', '#60a5fa', '#10b981'],
                    borderRadius: 6
                }]
            });

            // --- Chart 3: Chlorine Quality Monitoring (Line) ---
            renderChart('chlorineChart', 'line', {
                labels: data.quality.ro_chlorine.map(d => d.time).slice(-20),
                datasets: [{
                    label: 'Residual Cl2 (mg)',
                    data: data.quality.ro_chlorine.map(d => d.mg).slice(-20),
                    borderColor: '#f59e0b',
                    backgroundColor: 'rgba(245, 158, 11, 0.1)',
                    fill: true,
                    tension: 0.3
                }]
            });

        } catch (err) {
            console.error("🔥 WTP load error:", err);
            document.getElementById("kpi-wtp-status").textContent = "OFFLINE";
            document.getElementById("kpi-wtp-status").className = "kpi-value neg";
        }
    }

    function renderChart(id, type, data) {
        const ctx = document.getElementById(id);
        if (!ctx) return;

        if (charts[id]) { charts[id].destroy(); }

        charts[id] = new Chart(ctx, {
            type: type,
            data: data,
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { position: 'bottom', labels: { boxWidth: 12, font: { family: 'Inter', size: 11 } } }
                },
                scales: {
                    x: { grid: { display: false } },
                    y: { beginAtZero: false }
                }
            }
        });
    }

    function updateKPIs(data) {
        const lastRO = data.flow_totals.ro_water.slice(-1)[0]?.m3 || 0;
        const lastPres = data.pressure.ro_supply.slice(-1)[0]?.bar || 0;
        const lastCl = data.quality.ro_chlorine.slice(-1)[0]?.mg || 0;

        document.getElementById("kpi-ro-total").textContent = lastRO.toLocaleString();
        document.getElementById("kpi-ro-pres").textContent = lastPres.toFixed(1);
        document.getElementById("kpi-chlorine").textContent = lastCl.toFixed(2);

        // SYSTEM STATUS LOGIC
        const statusEl = document.getElementById("kpi-wtp-status");
        
        // Alert if Chlorine is too low (< 0.1) or Pressure is too high (> 7.5)
        if (lastCl < 0.1 || lastPres > 7.5) {
            statusEl.textContent = "ATTENTION";
            statusEl.className = "kpi-value neg"; // Blinks red (if CSS added)
        } else {
            statusEl.textContent = "NORMAL";
            statusEl.className = "kpi-value pos"; // Green
        }
    }

    function updateWTPTable(flow) {
        const well = flow.deep_well.slice(-1)[0]?.m3 || 0;
        const s1 = flow.soft_water_1.slice(-1)[0]?.m3 || 0;
        const s2 = flow.soft_water_2.slice(-1)[0]?.m3 || 0;
        const fire = flow.fire_water.slice(-1)[0]?.m3 || 0;

        document.getElementById("table-well-val").textContent = `${well.toLocaleString()} m³`;
        document.getElementById("table-soft-val").textContent = `${(s1 + s2).toLocaleString()} m³`;
        document.getElementById("table-fire-val").textContent = `${fire.toLocaleString()} m³`;
    }

    loadWTPData();
    setInterval(loadWTPData, 60000); // Sync every minute
});