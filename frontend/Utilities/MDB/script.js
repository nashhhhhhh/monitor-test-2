document.addEventListener("DOMContentLoaded", () => {
    const charts = {};
    const lightingUtils = window.lightingMonitoringUtils;
    const fallbackLightingDataset = window.lightingMonitoringMockData;
    let lightingSummary = lightingUtils && fallbackLightingDataset
        ? lightingUtils.summarizePortfolio(fallbackLightingDataset)
        : null;

    const emdbPicker = document.getElementById("emdb-date-picker");
    const genPicker = document.getElementById("gen-date-picker");

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

    async function loadLightingData() {
        if (!lightingUtils || !fallbackLightingDataset) return;

        try {
            const response = await fetch("/api/lighting");
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const data = await response.json();
            if (Array.isArray(data?.fixtures) && data.fixtures.length) {
                lightingSummary = lightingUtils.summarizePortfolio(data);
            }
        } catch (error) {
            console.warn("Lighting API unavailable, keeping fallback lighting dataset on MDB.", error);
        }

        renderLightingEnergyModule();
    }

    async function loadMDBData() {
        try {
            const response = await fetch("/api/mdb");
            const data = await response.json();

            updateKPIs(data);
            updateGenTable(data.generators);

            const mdbKeys = ["mdb_6", "mdb_7", "mdb_8", "mdb_9", "mdb_10"];
            const distributionData = mdbKeys.map((key) => {
                const list = data.energy[key];
                return list.length > 0 ? list[list.length - 1].kwh : 0;
            });

            renderChart("distributionChart", "bar", {
                labels: ["MDB-6", "MDB-7", "MDB-8", "MDB-9", "MDB-10"],
                datasets: [{
                    label: "Energy (kWh)",
                    data: distributionData,
                    backgroundColor: "#3b82f6",
                    borderRadius: 6
                }]
            });

            fetchEMDBHistory(emdbPicker.value);
            fetchGenHistory(genPicker.value);
        } catch (err) {
            console.error("MDB real-time load error:", err);
        }
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

    function renderLightingEnergyModule() {
        if (!lightingSummary) return;

        const totalLightingKwh = lightingSummary.totals.totalEnergyConsumption;
        const topArea = lightingSummary.highestConsumingRoom;

        document.getElementById("kpi-lighting-energy").textContent = `${totalLightingKwh.toLocaleString()} kWh`;
        document.getElementById("lighting-energy-room").textContent = topArea
            ? `Highest lighting area: ${topArea.roomName} (${topArea.totalEnergyConsumption} kWh)`
            : "No area breakdown available";

        document.getElementById("lighting-energy-breakdown").innerHTML = lightingSummary.areas
            .slice(0, 10)
            .map((area) => `
                <div class="lighting-breakdown-item">
                    <span class="lighting-breakdown-room">${area.areaName}</span>
                    <span class="lighting-breakdown-kwh">${area.totalNotionalEnergy} kWh</span>
                </div>
            `)
            .join("");

        document.getElementById("lighting-circuit-breakdown").innerHTML = lightingSummary.circuits
            .slice(0, 10)
            .map((circuit) => `
                <div class="lighting-breakdown-item">
                    <span class="lighting-breakdown-room">${circuit.circuitName}</span>
                    <span class="lighting-breakdown-kwh">${circuit.totalNotionalEnergy} kWh</span>
                </div>
            `)
            .join("");

        renderChart("lightingAreaEnergyChart", "bar", {
            labels: lightingSummary.areas.slice(0, 8).map((area) => area.areaName),
            datasets: [{
                label: "Lighting Energy (kWh)",
                data: lightingSummary.areas.slice(0, 8).map((area) => area.totalNotionalEnergy),
                backgroundColor: "#2563eb",
                borderRadius: 8
            }]
        }, {
            indexAxis: "y",
            scales: {
                x: { beginAtZero: true, grid: { color: "rgba(148, 163, 184, 0.12)" } },
                y: { grid: { display: false } }
            }
        });

        const totalMdb = Number(String(document.getElementById("kpi-total-mdb")?.textContent || "0").replace(/,/g, ""));
        const share = totalMdb > 0
            ? ((lightingSummary.totals.totalEnergyConsumption / totalMdb) * 100).toFixed(1)
            : "0.0";
        document.getElementById("lighting-energy-share").textContent = `${share}% of current monitored MDB load attributed to lighting`;
    }

    function updateKPIs(data) {
        const emdbVal = data.energy.emdb_1.slice(-1)[0]?.kwh || 0;
        document.getElementById("kpi-emdb").textContent = emdbVal.toLocaleString();

        let totalMdb = 0;
        ["mdb_6", "mdb_7", "mdb_8", "mdb_9", "mdb_10"].forEach((key) => {
            totalMdb += data.energy[key].slice(-1)[0]?.kwh || 0;
        });
        document.getElementById("kpi-total-mdb").textContent = totalMdb.toLocaleString();

        let activeGens = 0;
        [1, 2, 3, 4].forEach((n) => {
            const list = data.generators[`gen_${n}`];
            if (list.length >= 2 && list[list.length - 1].runtime > list[list.length - 2].runtime) {
                activeGens++;
            }
        });
        document.getElementById("kpi-gen-status").textContent = `${activeGens} / 4`;

        if (lightingSummary) {
            const share = totalMdb > 0
                ? ((lightingSummary.totals.totalEnergyConsumption / totalMdb) * 100).toFixed(1)
                : "0.0";
            document.getElementById("lighting-energy-share").textContent = `${share}% of current monitored MDB load attributed to lighting`;
        }
    }

    function updateGenTable(gens) {
        const tbody = document.getElementById("gen-table-body");
        if (!tbody) return;
        tbody.innerHTML = "";

        [1, 2, 3, 4].forEach((n) => {
            const key = `gen_${n}`;
            const latest = gens[key].slice(-1)[0]?.runtime || 0;
            const prev = gens[key].slice(-2)[0]?.runtime || 0;
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
    if (genPicker) {
        genPicker.addEventListener("change", (event) => fetchGenHistory(event.target.value));
    }

    loadLightingData();
    loadMDBData();
    setInterval(loadMDBData, 60000);
});
