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
        { id: "lighting", name: "Lighting Control", path: "/Lighting/index.html", localData: true },
        { id: "boiler", name: "Boiler Systems", path: "/Utilities/Boiler/index.html", api: "/api/boiler" },
        { id: "air", name: "Air Compressor", path: "/Utilities/Air%20Compressor/index.html", api: "/api/aircompressor" },
        { id: "kitchen", name: "Kitchen Equipment", path: "/Kitchen%20Equipment/index.html", api: "/api/kitchen" }
    ];

    async function updateHeartbeat() {
        const fetchSystem = async (sys) => {
            if (sys.localData) {
                if (sys.id === "lighting" && lightingDataset && lightingUtils) {
                    return {
                        ...sys,
                        data: lightingUtils.summarizePortfolio(lightingDataset),
                        error: false
                    };
                }
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
                displayValue = `${data.operatingAvailability || 0}% Online`;
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

        return {
            status: "NORMAL",
            message: "System Operational",
            value: displayValue
        };
    }

    updateHeartbeat();
    setInterval(updateHeartbeat, 30000);
});
