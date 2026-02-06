document.addEventListener("DOMContentLoaded", () => {
    let charts = {};
    const emdbPicker = document.getElementById('emdb-date-picker');
    const genPicker = document.getElementById('gen-date-picker');

    // Set default dates to today
    if (emdbPicker) emdbPicker.valueAsDate = new Date();
    if (genPicker) genPicker.valueAsDate = new Date();

    async function loadMDBData() {
        try {
            console.log("⚡ Syncing MDB Real-time Data...");
            const response = await fetch("/api/mdb");
            const data = await response.json();

            // 1. Update KPIs & Status (Includes Outlier Detection)
            updateKPIs(data);
            
            // 2. Update Generator Table
            updateGenTable(data.generators);

            // 3. MDB Distribution Chart (Latest values)
            const mdbKeys = ['mdb_6', 'mdb_7', 'mdb_8', 'mdb_9', 'mdb_10'];
            const distValues = mdbKeys.map(k => data.energy[k]?.slice(-1)[0]?.kwh || 0);
            
            renderChart('distributionChart', 'bar', {
                labels: ['MDB-6', 'MDB-7', 'MDB-8', 'MDB-9', 'MDB-10'],
                datasets: [{
                    label: 'Latest Energy (kWh)',
                    data: distValues,
                    backgroundColor: '#3b82f6',
                    borderRadius: 4
                }]
            });

            // 4. Initial load of Historical Charts
            fetchEMDBHistory(emdbPicker.value);
            fetchGenHistory(genPicker.value);

        } catch (err) {
            console.error("🔥 MDB load error:", err);
        }
    }

    async function fetchEMDBHistory(date) {
        try {
            const res = await fetch(`/api/mdb/history?category=energy&date=${date}`);
            const data = await res.json();
            
            renderChart('emdbTrendChart', 'line', {
                labels: data.emdb_1.map(d => d.time),
                datasets: [{
                    label: `EMDB-1 Load (${date})`,
                    data: data.emdb_1.map(d => d.value),
                    borderColor: '#10b981',
                    backgroundColor: 'rgba(16, 185, 129, 0.1)',
                    fill: true,
                    tension: 0.3
                }]
            });
        } catch (err) { console.error("EMDB History Error:", err); }
    }

    async function fetchGenHistory(date) {
        try {
            const res = await fetch(`/api/mdb/history?category=gens&date=${date}`);
            const data = await res.json();
            
            renderChart('genRuntimeChart', 'line', {
                labels: data.gen_1.map(d => d.time),
                datasets: [
                    { label: 'Gen 1', data: data.gen_1.map(d => d.value), borderColor: '#f59e0b', tension: 0.1 },
                    { label: 'Gen 2', data: data.gen_2.map(d => d.value), borderColor: '#ef4444', tension: 0.1 },
                    { label: 'Gen 3', data: data.gen_3.map(d => d.value), borderColor: '#3b82f6', tension: 0.1 },
                    { label: 'Gen 4', data: data.gen_4.map(d => d.value), borderColor: '#94a3b8', tension: 0.1 }
                ]
            });
        } catch (err) { console.error("Gen History Error:", err); }
    }

    function renderChart(id, type, data) {
        const ctx = document.getElementById(id);
        if (charts[id]) charts[id].destroy();
        charts[id] = new Chart(ctx, {
            type: type,
            data: data,
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 11 } } } },
                scales: { x: { grid: { display: false } } }
            }
        });
    }

    function updateKPIs(data) {
        const emdbVal = data.energy.emdb_1.slice(-1)[0]?.kwh || 0;
        document.getElementById("kpi-emdb").textContent = emdbVal.toLocaleString();

        let totalMdb = 0;
        let mdbVals = [];
        ['mdb_6', 'mdb_7', 'mdb_8', 'mdb_9', 'mdb_10'].forEach(k => {
            const val = data.energy[k]?.slice(-1)[0]?.kwh || 0;
            totalMdb += val;
            mdbVals.push(val);
        });
        document.getElementById("kpi-total-mdb").textContent = totalMdb.toLocaleString();

        // Generator Active Logic
        let runtimes = [1,2,3,4].map(n => {
            const list = data.generators[`gen_${n}`];
            return list.slice(-1)[0]?.runtime || 0;
        });

        let activeGens = 0;
        [1,2,3,4].forEach(n => {
            const list = data.generators[`gen_${n}`];
            if (list.length >= 2 && list[list.length-1].runtime > list[list.length-2].runtime) activeGens++;
        });
        document.getElementById("kpi-gen-status").textContent = `${activeGens} / 4`;

        // System Status Outlier Logic
        const statusEl = document.getElementById("kpi-system-status");
        const isAbnormal = detectOutlier(runtimes) || detectOutlier(mdbVals);
        
        statusEl.textContent = isAbnormal ? "ATTENTION" : "NORMAL";
        statusEl.className = isAbnormal ? "kpi-value neg" : "kpi-value pos";
    }

    function detectOutlier(arr) {
        if (arr.length < 2) return false;
        const mean = arr.reduce((a, b) => a + b, 0) / arr.length;
        if (mean === 0) return false;
        return arr.some(v => v > (mean * 2)); // Trigger alert if any value is 2x the average
    }

    function updateGenTable(gens) {
        const tbody = document.getElementById('gen-table-body');
        tbody.innerHTML = '';
        [1,2,3,4].forEach(n => {
            const list = gens[`gen_${n}`];
            const latest = list.slice(-1)[0]?.runtime || 0;
            const prev = list.slice(-2)[0]?.runtime || 0;
            const running = latest > prev && prev !== 0;
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>Generator ${n}</td>
                <td>${latest.toFixed(1)} hrs</td>
                <td><span class="status-pill ${running ? 'active' : 'warning'}">${running ? 'RUNNING' : 'STANDBY'}</span></td>
            `;
            tbody.appendChild(tr);
        });
    }

    // Listeners
    if (emdbPicker) emdbPicker.addEventListener('change', (e) => fetchEMDBHistory(e.target.value));
    if (genPicker) genPicker.addEventListener('change', (e) => fetchGenHistory(e.target.value));

    loadMDBData();
    setInterval(loadMDBData, 60000);
});