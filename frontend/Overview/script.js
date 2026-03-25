document.addEventListener("DOMContentLoaded", () => {
    const statusLight = document.getElementById("status-indicator-light");
    const statusText = document.getElementById("overall-status-text");
    const lastSyncEl = document.getElementById("last-sync");
    const container = document.getElementById("health-tiles");
    const alertBox = document.getElementById("global-alert-box");
    const lightingDataset = window.lightingMonitoringMockData;
    const lightingUtils = window.lightingMonitoringUtils;

    const systems = [
        { id: "mdb", name: "Power Systems (MDB)", path: "/Utilities/MDB/index.html", api: "/api/mdb" },
        { id: "wtp", name: "Water Treatment", path: "/Utilities/Water%20Treatment%20Plant/index.html", api: "/api/wtp" },
        { id: "wwtp", name: "Wastewater Plant", path: "/Utilities/Wastewater%20Plant/index.html", api: "/api/wwtp/latest" },
        { id: "temp", name: "Room Temperatures", path: "/Temperature/index.html", api: "/api/temperature/rooms" },
        { id: "sbf", name: "Spiral Blast Freezer", path: "/Spiral%20Blast%20Freezer/index.html", api: "/api/spiral_blast_freezer" },
        { id: "cctv", name: "CCTV Monitoring", path: "/CCTV/index.html", api: "/api/cctv/log" },
        { id: "lighting", name: "Lighting Control", path: "/Lighting/index.html", api: "/api/lighting", localData: true },
        { id: "boiler", name: "Boiler Systems", path: "/Utilities/Boiler/index.html", api: "/api/boiler" },
        { id: "air", name: "Air Compressor", path: "/Utilities/Air%20Compressor/index.html", api: "/api/aircompressor" },
        { id: "kitchen", name: "Kitchen Equipment", path: "/Kitchen%20Equipment/index.html", api: "/api/kitchen" }
    ];

    async function updateHeartbeat() {
        const fetchSystem = async (sys) => {
            if (sys.id === "lighting" && lightingUtils) {
                try {
                    const res = await fetch(sys.api);
                    if (!res.ok) {
                        throw new Error(`HTTP ${res.status}`);
                    }
                    const data = await res.json();
                    if (Array.isArray(data?.fixtures) && data.fixtures.length) {
                        return {
                            ...sys,
                            data: lightingUtils.summarizePortfolio(data),
                            error: false
                        };
                    }
                } catch (e) {
                    console.warn(`${sys.name} API unavailable, using fallback dataset.`, e);
                }

                if (lightingDataset) {
                    return {
                        ...sys,
                        data: lightingUtils.summarizePortfolio(lightingDataset),
                        error: false
                    };
                }

                return { ...sys, data: null, error: true };
            }

            if (sys.localData) {
                return { ...sys, data: null, error: true };
            }

            try {
                const res = await fetch(sys.api);
                if (!res.ok) {
                    throw new Error(`HTTP ${res.status}`);
                }
                const text = await res.text();
                const cleanText = text.replace(/: NaN/g, ": null");
                const data = JSON.parse(cleanText);
                return { ...sys, data, error: false };
            } catch (e) {
                console.warn(`${sys.name} Offline:`, e);
                return { ...sys, data: null, error: true };
            }
        };

        const processedData = await Promise.all(systems.map((system) => fetchSystem(system)));

        container.innerHTML = "";

        let hasOffline = false;
        let hasAttention = false;

        processedData.forEach((sys) => {
            const health = evaluateHealth(sys);
            const tile = document.createElement("div");

            if (health.status === "OFFLINE") hasOffline = true;
            if (health.status === "ATTENTION" || health.status === "WARNING") hasAttention = true;

            tile.className = `status-card ${health.status.toLowerCase()}`;
            tile.onclick = () => {
                window.location.href = sys.path;
            };

            tile.innerHTML = `
                <div class="card-header">
                    <h3>${sys.name}</h3>
                    <span class="badge">${health.status}</span>
                </div>
                <div class="card-body">
                    <p class="status-msg">${health.message}</p>
                    <p class="metric-val">${health.value || "--"}</p>
                </div>
                <div class="card-footer">Investigate Details -></div>
            `;

            container.appendChild(tile);
        });

        lastSyncEl.textContent = new Date().toLocaleTimeString();
        if (hasOffline) {
            statusLight.className = "status-light danger";
            statusText.textContent = "One or more systems are offline";
            alertBox.classList.remove("hidden");
        } else if (hasAttention) {
            statusLight.className = "status-light warn";
            statusText.textContent = "Attention required on one or more systems";
            alertBox.classList.remove("hidden");
        } else {
            statusLight.className = "status-light ok";
            statusText.textContent = "All systems operational";
            alertBox.classList.add("hidden");
        }
    }

    function evaluateHealth(sys) {
        if (sys.error || !sys.data) {
            return { status: "OFFLINE", message: "System Unreachable", value: "Check Data Source" };
        }

        const data = sys.data;
        let displayValue = "Online";

        try {
            if (sys.id === "wtp") {
                const cl2 = data.quality?.ro_chlorine?.slice(-1)[0]?.mg || 0;
                displayValue = `${cl2.toFixed(2)} mg`;
            } else if (sys.id === "mdb") {
                const load = data.energy?.emdb_1?.slice(-1)[0]?.kwh || 0;
                displayValue = `${load.toLocaleString()} kWh`;
            } else if (sys.id === "temp") {
                displayValue = `${data.length} Rooms Monitored`;
            } else if (sys.id === "wwtp") {
                const temp = data.rawTemp?.slice(-1)[0]?.value || 0;
                displayValue = `${temp.toFixed(1)} C`;
            } else if (sys.id === "lighting") {
                displayValue = `${data.averageHealthScore || 0}% Avg Health`;
            } else if (sys.id === "kitchen") {
                displayValue = `${data.online ?? 0} / ${data.total ?? 4} Online`;
            }
        } catch (e) {
            displayValue = "Connected";
        }

        if (sys.id === "wtp") {
            const cl2 = data.quality?.ro_chlorine?.slice(-1)[0]?.mg;
            if (typeof cl2 === "number" && cl2 < 0.1) {
                return {
                    status: "ATTENTION",
                    message: "Residual chlorine below threshold",
                    value: displayValue
                };
            }
        }

        if (sys.id === "wwtp") {
            const temp = data.rawTemp?.slice(-1)[0]?.value;
            if (typeof temp === "number" && temp >= 35) {
                return {
                    status: "WARNING",
                    message: "Wastewater inflow temperature elevated",
                    value: displayValue
                };
            }
        }

        if (sys.id === "kitchen") {
            const online = data.online ?? 0;
            const total = data.total ?? 4;
            if (online < total) {
                return {
                    status: "ATTENTION",
                    message: `${total - online} unit(s) offline`,
                    value: displayValue
                };
            }
        }

        if (sys.id === "lighting") {
            const criticalFixtures = data.totals?.criticalFixtures ?? 0;
            const warningFixtures = data.totals?.warningFixtures ?? 0;
            const totalFixtures = data.totals?.totalFixtures ?? 0;
            const totalEnergy = data.totals?.totalEnergyConsumption ?? 0;

            if (criticalFixtures > 0) {
                return {
                    status: "ATTENTION",
                    message: `${criticalFixtures} critical fixture(s) across ${totalFixtures} monitored lights`,
                    value: `${totalEnergy.toLocaleString()} kWh`
                };
            }

            if (warningFixtures > 0) {
                return {
                    status: "WARNING",
                    message: `${warningFixtures} fixture(s) approaching maintenance threshold`,
                    value: displayValue
                };
            }

            return {
                status: "NORMAL",
                message: `${totalFixtures} fixtures monitored`,
                value: displayValue
            };
        }

        return {
            status: "NORMAL",
            message: "System Operational",
            value: displayValue
        };
    }

    // ── Downtime KPI strip ──────────────────────────────────────────
    function calcDowntimeKPIs() {
        const todayBase = new Date();
        todayBase.setHours(0, 0, 0, 0);

        function ev(startH, startM, durMins) {
            return { durationMins: durMins };
        }

        const equipment = [
            { name: 'CCTV C.16',          events: [ev(1,15,12), ev(4,30,8), ev(7,45,20), ev(11,0,15), ev(14,20,9), ev(18,5,11)] },
            { name: 'CCTV C.08',          events: [ev(3,10,10), ev(9,45,25), ev(16,30,8)] },
            { name: 'Spiral Blast Freezer', events: [ev(2,0,45), ev(13,30,30)] },
            { name: 'Boiler 01',          events: [ev(6,15,25)] },
            { name: 'Boiler 02',          events: [] },
            { name: 'Air Compressor',     events: [ev(8,0,15), ev(17,45,20)] },
            { name: 'MDB Generator',      events: [ev(5,30,10)] },
            { name: 'Wastewater Pump',    events: [ev(10,0,35), ev(19,15,20)] },
            { name: 'Hobart Dishwasher',  events: [ev(7,0,10), ev(12,30,8)] },
            { name: 'X-Ray Inspector',    events: [ev(9,15,5)] },
        ];

        const MINS_IN_DAY = 24 * 60;
        let totalDownMins = 0;
        let totalEvents   = 0;
        let worstName     = '--';
        let worstMins     = 0;

        equipment.forEach(eq => {
            const down = eq.events.reduce((s, e) => s + e.durationMins, 0);
            totalDownMins += down;
            totalEvents   += eq.events.length;
            if (down > worstMins) { worstMins = down; worstName = eq.name; }
        });

        const uptimePct = ((MINS_IN_DAY * equipment.length - totalDownMins) /
                           (MINS_IN_DAY * equipment.length) * 100).toFixed(1);

        function fmtDur(m) {
            const h = Math.floor(m / 60), mm = Math.round(m % 60);
            return h > 0 ? `${h}h ${mm}m` : `${mm}m`;
        }

        document.getElementById('dt-total').textContent    = fmtDur(totalDownMins);
        document.getElementById('dt-events').textContent   = totalEvents;
        document.getElementById('dt-worst').textContent    = worstName;
        document.getElementById('dt-worst-sub').textContent = fmtDur(worstMins) + ' downtime';
        document.getElementById('dt-uptime').textContent   = uptimePct + '%';
    }

    calcDowntimeKPIs();
    // ────────────────────────────────────────────────────────────────

    updateHeartbeat();
    setInterval(updateHeartbeat, 30000);
});
