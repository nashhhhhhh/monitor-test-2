document.addEventListener("DOMContentLoaded", () => {
    // Store chart instances to manage updates/destruction
    let charts = {};
    const datePicker = document.getElementById('chlorine-date-picker');
    
    // Set default date to today's date
    if (datePicker) {
        datePicker.valueAsDate = new Date();
    }

    /**
     * Main data loader for WTP Dashboard
     */
    async function loadWTPData() {
        try {
            console.log("💧 Syncing WTP Data...");
            const response = await fetch("/api/wtp");
            const data = await response.json();

            // Safety Check: If backend fails, stop execution
            if (!data.flow_totals || !data.flow_rates) {
                console.error("Data structure incomplete from API:", data);
                return;
            }

            // 1. Update Numeric KPIs (Top Cards)
            updateKPIs(data);

            // 2. Update Real-time Flow Rate Monitor (5 items)
            updateFlowRateDisplay(data.flow_rates);

            // 3. Water Source Distribution Chart (Bar Chart with 5 Sources)
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

            // 4. Pressure Trends Chart (Line Chart)
            renderChart('pressureChart', 'line', {
                labels: data.pressure.ro_supply?.map(d => d.time).slice(-20) || [],
                datasets: [
                    { 
                        label: 'RO Supply (bar)', 
                        data: data.pressure.ro_supply?.map(d => d.bar).slice(-20) || [], 
                        borderColor: '#3b82f6', 
                        backgroundColor: 'transparent',
                        tension: 0.3 
                    },
                    { 
                        label: 'Soft Water (bar)', 
                        data: data.pressure.soft_water?.map(d => d.bar).slice(-20) || [], 
                        borderColor: '#94a3b8', 
                        backgroundColor: 'transparent',
                        borderDash: [5, 5],
                        tension: 0.3 
                    }
                ]
            });

            // 5. Load Chlorine Trend for selected date
            if (datePicker) fetchChlorine(datePicker.value);

        } catch (err) {
            console.error("🔥 WTP load error:", err);
        }
    }

    /**
     * Historical Chlorine fetcher with date filtering
     */
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

    /**
     * Customized Bar Chart with DataLabels and precise Tooltips
     */
    function renderBarChart(id, chartData) {
        const ctx = document.getElementById(id);
        if (!ctx) return;

        if (charts[id]) charts[id].destroy();

        charts[id] = new Chart(ctx, {
            type: 'bar',
            data: chartData,
            plugins: [ChartDataLabels],
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    datalabels: {
                        anchor: 'end',
                        align: 'top',
                        // Show exact value on bar if it's large enough to fit
                        formatter: (val) => val > 10 ? val.toLocaleString() + ' m³' : '',
                        color: '#475569',
                        font: { weight: 'bold', size: 10 }
                    },
                    tooltip: {
                        enabled: true,
                        mode: 'index',
                        intersect: false,
                        callbacks: {
                            title: (items) => "Water Source: " + items[0].label,
                            label: (context) => `Volume: ${context.parsed.y.toLocaleString()} m³`
                        }
                    }
                },
                scales: {
                    y: { 
                        beginAtZero: true, 
                        grid: { color: '#f1f5f9' },
                        ticks: { font: { size: 10 } }
                    },
                    x: { grid: { display: false } }
                }
            }
        });
    }

    /**
     * Standard Line Chart Helper
     */
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
                    legend: { position: 'bottom', labels: { boxWidth: 12, font: { family: 'Inter', size: 11 } } },
                    tooltip: { mode: 'index', intersect: false }
                },
                scales: {
                    x: { grid: { display: false } },
                    y: { grid: { color: '#f1f5f9' } }
                }
            }
        });
    }

    /**
     * Update the 5-item Real-time Flow Rate Monitor
     */
    function updateFlowRateDisplay(rates) {
        document.getElementById('rate-well').textContent = (rates.deep_well || 0).toFixed(2);
        document.getElementById('rate-soft1').textContent = (rates.soft_water_1 || 0).toFixed(2);
        document.getElementById('rate-soft2').textContent = (rates.soft_water_2 || 0).toFixed(2);
        document.getElementById('rate-ro').textContent = (rates.ro_water || 0).toFixed(2);
        document.getElementById('rate-fire').textContent = (rates.fire_water || 0).toFixed(2);
    }

    /**
     * Update KPI Cards (Top of Page)
     */
    function updateKPIs(data) {
        // RO Water Supply Totalizer
        const lastRO = data.flow_totals.ro_water?.slice(-1)[0]?.m3 || 0;
        // Pressure
        const lastPres = data.pressure.ro_supply?.slice(-1)[0]?.bar || 0;
        // Chlorine
        const lastCl = data.quality.ro_chlorine?.slice(-1)[0]?.mg || 0;

        document.getElementById("kpi-ro-total").textContent = lastRO.toLocaleString();
        document.getElementById("kpi-ro-pres").textContent = lastPres.toFixed(1);
        document.getElementById("kpi-chlorine").textContent = lastCl.toFixed(2);

        // System Status Logic
        const statusEl = document.getElementById("kpi-wtp-status");
        if (lastCl < 0.1 || lastPres > 7.5) {
            statusEl.textContent = "ATTENTION";
            statusEl.className = "kpi-value neg";
        } else {
            statusEl.textContent = "NORMAL";
            statusEl.className = "kpi-value pos";
        }
    }

    // Event listener for Chlorine Date Picker
    if (datePicker) {
        datePicker.addEventListener('change', (e) => fetchChlorine(e.target.value));
    }

    // Initial Load & Set Automatic Refresh (Every 60 Seconds)
    loadWTPData();
    setInterval(loadWTPData, 60000);
});