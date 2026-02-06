document.addEventListener("DOMContentLoaded", () => {
    // Store chart instances globally within this scope to manage updates/destruction
    let charts = {};

    // Reference the Date Pickers
    const pickers = {
        energy: document.getElementById('energy-date-picker'),
        flow: document.getElementById('flow-date-picker'),
        temp: document.getElementById('temp-date-picker')
    };

    // 1. Set all date pickers to today's date by default
    Object.values(pickers).forEach(p => { 
        if (p) p.valueAsDate = new Date(); 
    });

    /**
     * Updates the 4 KPI cards at the top of the page
     * Calculates efficiency and counts active pumps
     */
    function updateKPIs(data) {
        try {
            const lastPmg = data.pmgEnergy?.slice(-1)[0]?.value || 0;
            const lastCtrl = data.ctrlEnergy?.slice(-1)[0]?.value || 0;
            const lastTemp = data.rawTemp?.slice(-1)[0]?.value || 0;
            const lastRaw = data.rawPump?.slice(-1)[0]?.value || 0;
            const lastEffluent = data.effluent?.slice(-1)[0]?.value || 0;

            // Update DOM Elements
            document.getElementById("kpi-energy").textContent = (lastPmg + lastCtrl).toLocaleString();
            document.getElementById("kpi-temp").textContent = `${lastTemp.toFixed(1)}°C`;

            const active = (lastEffluent > 0 ? 1 : 0) + (lastRaw > 0 ? 1 : 0);
            document.getElementById("kpi-pumps").textContent = active;

            let efficiency = 0;
            if (lastRaw > 0) {
                efficiency = ((lastRaw - lastEffluent) / lastRaw) * 100;
            }
            document.getElementById("kpi-efficiency").textContent = `${efficiency.toFixed(1)}%`;
            
            // Update Sync Time
            const now = new Date();
            document.getElementById('last-sync').textContent = now.toLocaleTimeString();
            document.getElementById('status-text').textContent = "NORMAL";
            document.getElementById('status-text').style.color = "var(--success)";
        } catch (err) {
            console.error("KPI Update Error:", err);
        }
    }

    /**
     * Standardized Chart Renderer
     */
    function renderChart(id, type, data) {
        const ctx = document.getElementById(id);
        if (!ctx) return;
        
        // Destroy existing chart to prevent hover/render glitches
        if (charts[id]) { charts[id].destroy(); }

        charts[id] = new Chart(ctx, {
            type: type,
            data: data,
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { 
                        position: 'bottom', 
                        labels: { boxWidth: 12, font: { size: 11, family: 'Inter' } } 
                    }
                },
                scales: {
                    x: { grid: { display: false } },
                    y: { beginAtZero: false }
                }
            }
        });
    }

    /**
     * Fetches historical data based on category and date selection
     */
    async function fetchWWTPHistory(category, date) {
        try {
            const res = await fetch(`/api/wwtp/history?category=${category}&date=${date}`);
            const data = await res.json();

            if (category === 'energy') {
                renderChart('energyChart', 'line', {
                    labels: data.pmg?.map(d => d.time) || [],
                    datasets: [
                        { label: 'Plant Energy', data: data.pmg?.map(d => d.value) || [], borderColor: '#3b82f6', tension: 0.3 },
                        { label: 'Control Panel', data: data.ctrl?.map(d => d.value) || [], borderColor: '#10b981', tension: 0.3 }
                    ]
                });
            } else if (category === 'flow') {
                renderChart('flowChart', 'bar', {
                    labels: data.effluent?.map(d => d.time) || [],
                    datasets: [
                        { label: 'Effluent Out', data: data.effluent?.map(d => d.value) || [], backgroundColor: '#3b82f6' },
                        { label: 'Raw Inflow', data: data.raw?.map(d => d.value) || [], backgroundColor: '#94a3b8' }
                    ]
                });
            } else if (category === 'temp') {
                renderChart('tempChart', 'line', {
                    labels: data.temp?.map(d => d.time) || [],
                    datasets: [{ 
                        label: 'Temp °C', 
                        data: data.temp?.map(d => d.value) || [], 
                        borderColor: '#f59e0b', 
                        fill: true,
                        backgroundColor: 'rgba(245, 158, 11, 0.1)',
                        tension: 0.3
                    }]
                });
            }
        } catch (err) {
            console.error(`Error loading ${category} history:`, err);
        }
    }

    /**
     * Loads the most recent data for KPIs and initial chart state
     */
    async function loadWWTPData() {
        try {
            console.log("🚰 Syncing WWTP Real-time Data...");
            const res = await fetch("/api/wwtp/latest");
            const data = await res.json();
            
            // Update the top KPI cards
            updateKPIs(data);

            // Fetch history for charts based on current picker values
            fetchWWTPHistory('energy', pickers.energy.value);
            fetchWWTPHistory('flow', pickers.flow.value);
            fetchWWTPHistory('temp', pickers.temp.value);

        } catch (err) {
            console.error("🔥 WWTP load error:", err);
            const statusText = document.getElementById('status-text');
            if (statusText) {
                statusText.textContent = "ERROR";
                statusText.style.color = "var(--danger)";
            }
        }
    }

    // --- EVENT LISTENERS ---

    // Listen for changes on date pickers
    if (pickers.energy) pickers.energy.addEventListener('change', (e) => fetchWWTPHistory('energy', e.target.value));
    if (pickers.flow) pickers.flow.addEventListener('change', (e) => fetchWWTPHistory('flow', e.target.value));
    if (pickers.temp) pickers.temp.addEventListener('change', (e) => fetchWWTPHistory('temp', e.target.value));

    // --- INITIALIZATION ---

    // Run once on load
    loadWWTPData();

    // Refresh KPIs and charts every 60 seconds
    setInterval(loadWWTPData, 60000);
});