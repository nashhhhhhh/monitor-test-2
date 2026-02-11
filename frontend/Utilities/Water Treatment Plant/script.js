document.addEventListener("DOMContentLoaded", () => {
    // 1. SHARED STATE
    let charts = {}; 
    const chlorineDatePicker = document.getElementById('chlorine-date-picker');
    const pressureDatePicker = document.getElementById('pressure-date-picker');
    
    // Set default dates to today
    const today = new Date().toISOString().split('T')[0];
    if (chlorineDatePicker) chlorineDatePicker.value = today;
    if (pressureDatePicker) pressureDatePicker.value = today;

    // 2. DATA LOADERS
    async function loadWTPData() {
        try {
            const response = await fetch("/api/wtp");
            const data = await response.json();

            updateKPIs(data);
            updateFlowRateDisplay(data.flow_rates);
            
            // Source Distribution
            renderBarChart('flowDistributionChart', {
                labels: ['Deep Well', 'Soft 1', 'Soft 2', 'RO Water', 'Fire Tank'],
                datasets: [{
                    label: 'Total Accumulation (m³)',
                    data: [
                        data.flow_totals.deep_well?.slice(-1)[0]?.m3 || 0,
                        data.flow_totals.soft_water_1?.slice(-1)[0]?.m3 || 0,
                        data.flow_totals.soft_water_2?.slice(-1)[0]?.m3 || 0,
                        data.flow_totals.ro_water?.slice(-1)[0]?.m3 || 0,
                        data.flow_totals.fire_water?.slice(-1)[0]?.m3 || 0
                    ],
                    backgroundColor: ['#1e293b', '#3b82f6', '#60a5fa', '#10b981', '#ef4444'],
                    borderRadius: 6
                }]
            });

            // Initial filtered data load
            fetchChlorine(chlorineDatePicker.value);
            fetchPressure(pressureDatePicker.value);

        } catch (err) {
            console.error("🔥 WTP load error:", err);
        }
    }

    async function fetchPressure(date) {
        try {
            const res = await fetch(`/api/wtp/pressure?date=${date}`);
            const data = await res.json();
            
            renderChart('pressureChart', 'line', {
                labels: data.ro_supply.map(d => d.time),
                datasets: [
                    { 
                        label: `RO Supply (${date})`, 
                        data: data.ro_supply.map(d => d.bar), 
                        borderColor: '#3b82f6', 
                        tension: 0.3 
                    },
                    { 
                        label: `Soft Water (${date})`, 
                        data: data.soft_water.map(d => d.bar), 
                        borderColor: '#94a3b8', 
                        borderDash: [5, 5],
                        tension: 0.3 
                    }
                ]
            });
        } catch (err) {
            console.error("Error fetching filtered pressure data:", err);
        }
    }

    async function fetchChlorine(date) {
        try {
            const res = await fetch(`/api/wtp/chlorine?date=${date}`);
            const chlorineData = await res.json();
            
            renderChart('chlorineChart', 'line', {
                labels: chlorineData.map(d => d.time),
                datasets: [{
                    label: `Residual Cl2 mg (${date})`,
                    data: chlorineData.map(d => d.mg),
                    borderColor: '#f59e0b',
                    backgroundColor: 'rgba(245, 158, 11, 0.1)',
                    fill: true,
                    tension: 0.3
                }]
            });
        } catch (err) {
            console.error("Error fetching filtered chlorine data:", err);
        }
    }

    // 3. CHART HELPERS
    function renderChart(id, type, data) {
        const ctx = document.getElementById(id);
        if (!ctx) return;
        if (charts[id]) charts[id].destroy();

        charts[id] = new Chart(ctx, {
            type: type,
            data: data,
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { position: 'bottom' },
                    tooltip: { mode: 'index', intersect: false }
                },
                scales: {
                    x: { grid: { display: false } },
                    y: { grid: { color: '#f1f5f9' }, title: { display: true, text: 'Value' } }
                }
            }
        });
    }

    function renderBarChart(id, chartData) {
        const ctx = document.getElementById(id);
        if (!ctx || !window.ChartDataLabels) return;
        if (charts[id]) charts[id].destroy();

        charts[id] = new Chart(ctx, {
            type: 'bar',
            data: chartData,
            plugins: [ChartDataLabels],
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    datalabels: { anchor: 'end', align: 'top', color: '#475569' }
                }
            }
        });
    }

    // 4. UI UPDATERS
    function updateFlowRateDisplay(rates) {
        document.getElementById('rate-well').textContent = (rates.deep_well || 0).toFixed(2);
        document.getElementById('rate-soft1').textContent = (rates.soft_water_1 || 0).toFixed(2);
        document.getElementById('rate-soft2').textContent = (rates.soft_water_2 || 0).toFixed(2);
        document.getElementById('rate-ro').textContent = (rates.ro_water || 0).toFixed(2);
        document.getElementById('rate-fire').textContent = (rates.fire_water || 0).toFixed(2);
    }

    function updateKPIs(data) {
        const lastRO = data.flow_totals.ro_water?.slice(-1)[0]?.m3 || 0;
        const lastPres = data.pressure.ro_supply?.slice(-1)[0]?.bar || 0;
        const lastCl = data.quality.ro_chlorine?.slice(-1)[0]?.mg || 0;

        document.getElementById("kpi-ro-total").textContent = lastRO.toLocaleString();
        document.getElementById("kpi-ro-pres").textContent = lastPres.toFixed(1);
        document.getElementById("kpi-chlorine").textContent = lastCl.toFixed(2);

        const statusEl = document.getElementById("kpi-wtp-status");
        if (lastCl < 0.1 || lastPres > 7.5) {
            statusEl.textContent = "ATTENTION";
            statusEl.className = "kpi-value neg";
        } else {
            statusEl.textContent = "NORMAL";
            statusEl.className = "kpi-value pos";
        }
    }

    // 5. LISTENERS & INIT
    if (chlorineDatePicker) {
        chlorineDatePicker.addEventListener('change', (e) => fetchChlorine(e.target.value));
    }
    if (pressureDatePicker) {
        pressureDatePicker.addEventListener('change', (e) => fetchPressure(e.target.value));
    }

    loadWTPData();
    setInterval(loadWTPData, 60000); // Sync every minute
});