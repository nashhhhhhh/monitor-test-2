document.addEventListener("DOMContentLoaded", () => {
    const charts = {};

    const distributionPicker = document.getElementById("distribution-date-picker");
    const distributionTimePicker = document.getElementById("distribution-time-picker");
    const emdbPicker = document.getElementById("emdb-date-picker");
    const genPicker = document.getElementById("gen-date-picker");

    if (distributionPicker) distributionPicker.valueAsDate = new Date();
    if (distributionTimePicker) distributionTimePicker.value = "23:45";
    if (emdbPicker) emdbPicker.valueAsDate = new Date();
    if (genPicker) genPicker.valueAsDate = new Date();

    function renderChart(id, type, data, options = {}) {
        const ctx = document.getElementById(id);
        if (!ctx) return;
        if (charts[id]) charts[id].destroy();

        charts[id] = new Chart(ctx, {
            type,
            data,
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: "bottom",
                        labels: {
                            boxWidth: 12,
                            font: { family: "Inter", size: 11 }
                        }
                    }
                },
                scales: {
                    y: { beginAtZero: false },
                    x: { grid: { display: false } }
                },
                ...options
            }
        });
    }

    function renderDistributionChart(distributionMap, selectedDate, selectedTime) {
        const mdbKeys = ["mdb_6", "mdb_7", "mdb_8", "mdb_9", "mdb_10"];
        const distributionData = mdbKeys.map((key) => distributionMap[key] || 0);
        const chartMoment = [selectedDate, selectedTime].filter(Boolean).join(" ");
        const chartLabel = chartMoment
            ? `Energy (kWh) at ${chartMoment}`
            : "Energy (kWh)";

        renderChart("distributionChart", "bar", {
            labels: ["MDB-6", "MDB-7", "MDB-8", "MDB-9", "MDB-10"],
            datasets: [{
                label: chartLabel,
                data: distributionData,
                backgroundColor: "#3b82f6",
                borderRadius: 6
            }]
        });
    }

    function renderSummaryDistribution(energy) {
        renderDistributionChart({
            mdb_6: energy.mdb_6?.latest || 0,
            mdb_7: energy.mdb_7?.latest || 0,
            mdb_8: energy.mdb_8?.latest || 0,
            mdb_9: energy.mdb_9?.latest || 0,
            mdb_10: energy.mdb_10?.latest || 0
        });
    }

    async function loadMDBData() {
        try {
            const response = await fetch("/api/mdb/summary");
            const data = await response.json();

            updateKPIs(data);
            updateGenTable(data.generators);
            updateSyncStamp(data.meta?.last_synced);
            renderSummaryDistribution(data.energy);

            requestAnimationFrame(() => {
                setTimeout(() => fetchDistributionHistory(distributionPicker?.value, distributionTimePicker?.value), 0);
                setTimeout(() => fetchEMDBHistory(emdbPicker.value), 40);
                setTimeout(() => fetchGenHistory(genPicker.value), 80);
            });
        } catch (err) {
            console.error("MDB real-time load error:", err);
        }
    }

    function updateSyncStamp(lastSynced) {
        const syncedAt = lastSynced ? new Date(lastSynced) : null;
        if (!syncedAt || Number.isNaN(syncedAt.getTime())) return;

        const dateLabel = syncedAt.toLocaleDateString("en-GB", {
            day: "2-digit",
            month: "short",
            year: "numeric"
        });
        const timeLabel = syncedAt.toLocaleTimeString("en-GB", {
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit"
        });

        const dateNode = document.getElementById("mdb-last-synced-date");
        const timeNode = document.getElementById("mdb-last-synced-time");
        if (dateNode) dateNode.textContent = dateLabel;
        if (timeNode) timeNode.textContent = timeLabel;
    }

    async function fetchEMDBHistory(date) {
        try {
            const res = await fetch(`/api/mdb/history?category=energy&date=${date}`);
            const data = await res.json();

            if (data.selected_date) emdbPicker.value = data.selected_date;

            renderChart("emdbTrendChart", "line", {
                labels: data.emdb_1.map((d) => d.time),
                datasets: [{
                    label: "EMDB-1 Energy Profile (kWh)",
                    data: data.emdb_1.map((d) => d.value),
                    borderColor: "#10b981",
                    backgroundColor: "rgba(16, 185, 129, 0.1)",
                    fill: true,
                    tension: 0.3
                }]
            });
        } catch (err) {
            console.error("EMDB History Error:", err);
        }
    }

    async function fetchDistributionHistory(date, time) {
        try {
            const params = new URLSearchParams({ category: "distribution" });
            if (date) params.set("date", date);
            if (time) params.set("time", time);

            const res = await fetch(`/api/mdb/history?${params.toString()}`);
            const data = await res.json();

            if (distributionPicker && data.selected_date) {
                distributionPicker.value = data.selected_date;
            }
            if (distributionTimePicker && data.selected_time) {
                distributionTimePicker.value = data.selected_time;
            }

            renderDistributionChart(
                data.distribution || {},
                data.selected_date,
                data.selected_time
            );
        } catch (err) {
            console.error("MDB Distribution History Error:", err);
        }
    }

    async function fetchGenHistory(date) {
        try {
            const res = await fetch(`/api/mdb/history?category=gens&date=${date}`);
            const data = await res.json();

            if (data.selected_date) genPicker.value = data.selected_date;

            renderChart("genRuntimeChart", "line", {
                labels: data.gen_1.map((d) => d.time),
                datasets: [
                    { label: "Gen-1", data: data.gen_1.map((d) => d.value), borderColor: "#f59e0b", tension: 0.1 },
                    { label: "Gen-2", data: data.gen_2.map((d) => d.value), borderColor: "#ef4444", tension: 0.1 },
                    { label: "Gen-3", data: data.gen_3.map((d) => d.value), borderColor: "#3b82f6", tension: 0.1 },
                    { label: "Gen-4", data: data.gen_4.map((d) => d.value), borderColor: "#94a3b8", tension: 0.1 }
                ]
            });
        } catch (err) {
            console.error("Generator History Error:", err);
        }
    }

    function updateKPIs(data) {
        const emdbVal = data.energy.emdb_1?.latest || 0;
        document.getElementById("kpi-emdb").textContent = emdbVal.toLocaleString();

        let totalMdb = 0;
        ["mdb_6", "mdb_7", "mdb_8", "mdb_9", "mdb_10"].forEach((key) => {
            totalMdb += data.energy[key]?.latest || 0;
        });
        document.getElementById("kpi-total-mdb").textContent = totalMdb.toLocaleString();

        let activeGens = 0;
        [1, 2, 3, 4].forEach((n) => {
            const generator = data.generators[`gen_${n}`];
            if ((generator?.latest || 0) > (generator?.previous || 0) && (generator?.previous || 0) !== 0) {
                activeGens++;
            }
        });
        document.getElementById("kpi-gen-status").textContent = `${activeGens} / 4`;

    }

    function updateGenTable(gens) {
        const tbody = document.getElementById("gen-table-body");
        if (!tbody) return;
        tbody.innerHTML = "";

        [1, 2, 3, 4].forEach((n) => {
            const key = `gen_${n}`;
            const latest = gens[key]?.latest || 0;
            const prev = gens[key]?.previous || 0;
            const isRunning = latest > prev && prev !== 0;

            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td>Generator ${n}</td>
                <td>${latest.toFixed(1)} hrs</td>
                <td><span class="status-pill ${isRunning ? "active" : "warning"}">${isRunning ? "RUNNING" : "STANDBY"}</span></td>
            `;
            tbody.appendChild(tr);
        });
    }

    if (emdbPicker) {
        emdbPicker.addEventListener("change", (event) => fetchEMDBHistory(event.target.value));
    }
    if (distributionPicker) {
        distributionPicker.addEventListener("change", (event) => fetchDistributionHistory(event.target.value, distributionTimePicker?.value));
    }
    if (distributionTimePicker) {
        distributionTimePicker.addEventListener("change", (event) => fetchDistributionHistory(distributionPicker?.value, event.target.value));
    }
    if (genPicker) {
        genPicker.addEventListener("change", (event) => fetchGenHistory(event.target.value));
    }

    loadMDBData();
    setInterval(loadMDBData, 60000);
});
