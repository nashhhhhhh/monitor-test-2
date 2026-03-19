document.addEventListener("DOMContentLoaded", () => {
    let charts = {};
    const lightingDataset = window.lightingMonitoringMockData;
    const lightingUtils = window.lightingMonitoringUtils;

    // Reference the Date Pickers
    const emdbPicker = document.getElementById('emdb-date-picker');
    const genPicker = document.getElementById('gen-date-picker');

    // Initialize pickers with today's date
    if (emdbPicker) emdbPicker.valueAsDate = new Date();
    if (genPicker) genPicker.valueAsDate = new Date();

    if (lightingDataset && lightingUtils) {
        renderLightingEnergyModule();
    }

    /**
     * Main data loader for Real-time KPIs and Distribution
     */
    async function loadMDBData() {
        try {
            console.log("⚡ Syncing MDB Real-time Data...");
            const response = await fetch("/api/mdb");
            const data = await response.json();

            // 1. Update KPIs (Real-time)
            updateKPIs(data);
            
            // 2. Update Generator Status Table (Real-time)
            updateGenTable(data.generators);

            // 3. MDB Distribution Chart (Latest Load)
            const mdbKeys = ['mdb_6', 'mdb_7', 'mdb_8', 'mdb_9', 'mdb_10'];
            const distributionData = mdbKeys.map(key => {
                const list = data.energy[key];
                return list.length > 0 ? list[list.length - 1].kwh : 0;
            });

            renderChart('distributionChart', 'bar', {
                labels: ['MDB-6', 'MDB-7', 'MDB-8', 'MDB-9', 'MDB-10'],
                datasets: [{
                    label: 'Energy (kWh)',
                    data: distributionData,
                    backgroundColor: '#3b82f6',
                    borderRadius: 6
                }]
            });

            // 4. Trigger initial historical fetch for the trends
            fetchEMDBHistory(emdbPicker.value);
            fetchGenHistory(genPicker.value);

        } catch (err) {
            console.error("🔥 MDB real-time load error:", err);
        }
    }

    /**
     * Fetches EMDB-1 line profile for a specific date
     */
    async function fetchEMDBHistory(date) {
        try {
            const res = await fetch(`/api/mdb/history?category=energy&date=${date}`);
            const data = await res.json();
            
            // If the backend auto-corrected the date (to latest available), update the picker
            if (data.selected_date) emdbPicker.value = data.selected_date;

            renderChart('emdbTrendChart', 'line', {
                labels: data.emdb_1.map(d => d.time),
                datasets: [{
                    label: `EMDB-1 Energy Profile (kWh)`,
                    data: data.emdb_1.map(d => d.value),
                    borderColor: '#10b981',
                    backgroundColor: 'rgba(16, 185, 129, 0.1)',
                    fill: true,
                    tension: 0.3
                }]
            });
        } catch (err) {
            console.error("EMDB History Error:", err);
        }
    }

    /**
     * Fetches all 4 Generator runtimes for a specific date
     */
    async function fetchGenHistory(date) {
        try {
            const res = await fetch(`/api/mdb/history?category=gens&date=${date}`);
            const data = await res.json();
            
            if (data.selected_date) genPicker.value = data.selected_date;

            renderChart('genRuntimeChart', 'line', {
                labels: data.gen_1.map(d => d.time),
                datasets: [
                    { label: 'Gen-1', data: data.gen_1.map(d => d.value), borderColor: '#f59e0b', tension: 0.1 },
                    { label: 'Gen-2', data: data.gen_2.map(d => d.value), borderColor: '#ef4444', tension: 0.1 },
                    { label: 'Gen-3', data: data.gen_3.map(d => d.value), borderColor: '#3b82f6', tension: 0.1 },
                    { label: 'Gen-4', data: data.gen_4.map(d => d.value), borderColor: '#94a3b8', tension: 0.1 }
                ]
            });
        } catch (err) {
            console.error("Generator History Error:", err);
        }
    }

    /**
     * Universal Chart Renderer
     */
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
                plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, font: { family: 'Inter', size: 11 } } } },
                scales: { 
                    y: { beginAtZero: false }, 
                    x: { grid: { display: false } } 
                }
            }
        });
    }

    function renderLightingEnergyModule() {
        const summary = lightingUtils.summarizePortfolio(lightingDataset);
        const totalLightingKwh = summary.totals.totalEnergyConsumption;
        const topRoom = summary.highestConsumingRoom;

        document.getElementById("kpi-lighting-energy").textContent = `${totalLightingKwh.toLocaleString()} kWh`;
        document.getElementById("lighting-energy-room").textContent = topRoom
            ? `Highest consuming room: ${topRoom.roomName} (${topRoom.totalEnergyConsumption} kWh)`
            : "No lighting room breakdown available";
        document.getElementById("lighting-energy-breakdown").innerHTML = summary.rooms
            .map(room => `
                <div class="lighting-breakdown-item">
                    <span class="lighting-breakdown-room">${room.roomName}</span>
                    <span class="lighting-breakdown-kwh">${room.totalEnergyConsumption} kWh</span>
                </div>
            `)
            .join('');

        renderChart('lightingEnergyTrendChart', 'line', {
            labels: summary.trend.map(point => point.time),
            datasets: [{
                label: 'Lighting Energy (kWh)',
                data: summary.trend.map(point => point.energyKwh),
                borderColor: '#3b82f6',
                backgroundColor: 'rgba(59, 130, 246, 0.12)',
                fill: true,
                tension: 0.35
            }]
        });
    }

    /**
     * Updates KPI cards (Latest values)
     */
    function updateKPIs(data) {
        const emdbVal = data.energy.emdb_1.slice(-1)[0]?.kwh || 0;
        document.getElementById("kpi-emdb").textContent = emdbVal.toLocaleString();

        let totalMdb = 0;
        ['mdb_6', 'mdb_7', 'mdb_8', 'mdb_9', 'mdb_10'].forEach(key => {
            totalMdb += data.energy[key].slice(-1)[0]?.kwh || 0;
        });
        document.getElementById("kpi-total-mdb").textContent = totalMdb.toLocaleString();

        let activeGens = 0;
        [1,2,3,4].forEach(n => {
            const list = data.generators[`gen_${n}`];
            if (list.length >= 2) {
                if (list[list.length-1].runtime > list[list.length-2].runtime) activeGens++;
            }
        });
        document.getElementById("kpi-gen-status").textContent = `${activeGens} / 4`;

        if (lightingDataset && lightingUtils) {
            const lightingSummary = lightingUtils.summarizePortfolio(lightingDataset);
            const share = totalMdb > 0 ? ((lightingSummary.totals.totalEnergyConsumption / totalMdb) * 100).toFixed(1) : "0.0";
            document.getElementById("lighting-energy-share").textContent = `${share}% of current monitored MDB load`;
        }
    }

    /**
     * Updates Generator Table (Latest values)
     */
    function updateGenTable(gens) {
        const tbody = document.getElementById('gen-table-body');
        if (!tbody) return;
        tbody.innerHTML = '';
        [1,2,3,4].forEach(n => {
            const key = `gen_${n}`;
            const latest = gens[key].slice(-1)[0]?.runtime || 0;
            const prev = gens[key].slice(-2)[0]?.runtime || 0;
            const isRunning = latest > prev && prev !== 0;

            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>Generator ${n}</td>
                <td>${latest.toFixed(1)} hrs</td>
                <td><span class="status-pill ${isRunning ? 'active' : 'warning'}">${isRunning ? 'RUNNING' : 'STANDBY'}</span></td>
            `;
            tbody.appendChild(tr);
        });
    }

    // --- Listeners for Date Pickers ---
    if (emdbPicker) {
        emdbPicker.addEventListener('change', (e) => fetchEMDBHistory(e.target.value));
    }
    if (genPicker) {
        genPicker.addEventListener('change', (e) => fetchGenHistory(e.target.value));
    }

    // Initial Load
    loadMDBData();

    // Refresh real-time data every 60 seconds
    setInterval(loadMDBData, 60000);
});
