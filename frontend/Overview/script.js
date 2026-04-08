document.addEventListener("DOMContentLoaded", () => {
    const statusLight = document.getElementById("status-indicator-light");
    const statusText = document.getElementById("overall-status-text");
    const lastSyncEl = document.getElementById("last-sync");
    const container = document.getElementById("health-tiles");
    const alertBox = document.getElementById("global-alert-box");

    async function updateHeartbeat() {
        let processedData = [];
        let lastSynced = null;

        try {
            const response = await fetch("/api/overview/health-fast");
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const payload = await response.json();
            processedData = payload.systems || [];
            lastSynced = payload.last_synced || null;
        } catch (error) {
            console.error("Overview summary load failed:", error);
            container.innerHTML = `
                <div class="loading-state">
                    <p>Overview summary unavailable. Check backend data sources.</p>
                </div>
            `;
            statusLight.className = "status-light critical";
            statusText.textContent = "Overview data unavailable";
            alertBox.classList.remove("hidden");
            return;
        }

        container.innerHTML = "";

        let hasOffline = false;
        let hasAttention = false;

        processedData.forEach((health) => {
            const tile = document.createElement("div");

            if (health.status === "OFFLINE") hasOffline = true;
            if (health.status === "ATTENTION" || health.status === "WARNING") hasAttention = true;

            tile.className = `status-card ${health.status.toLowerCase()}`;
            tile.onclick = () => {
                window.location.href = health.path;
            };

            tile.innerHTML = `
                <div class="card-header">
                    <h3>${health.name}</h3>
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

        if (lastSynced) {
            const syncedAt = new Date(lastSynced);
            lastSyncEl.textContent = Number.isNaN(syncedAt.getTime())
                ? new Date().toLocaleTimeString()
                : syncedAt.toLocaleTimeString();
        } else {
            lastSyncEl.textContent = new Date().toLocaleTimeString();
        }

        if (hasOffline) {
            statusLight.className = "status-light critical";
            statusText.textContent = "One or more systems are offline";
            alertBox.classList.remove("hidden");
        } else if (hasAttention) {
            statusLight.className = "status-light critical";
            statusText.textContent = "Attention required on one or more systems";
            alertBox.classList.remove("hidden");
        } else {
            statusLight.className = "status-light ok";
            statusText.textContent = "All systems operational";
            alertBox.classList.add("hidden");
        }
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

        equipment.forEach(eq => {
            const down = eq.events.reduce((s, e) => s + e.durationMins, 0);
            totalDownMins += down;
            totalEvents   += eq.events.length;
        });

        const uptimePct = ((MINS_IN_DAY * equipment.length - totalDownMins) /
                           (MINS_IN_DAY * equipment.length) * 100).toFixed(1);

        function fmtDur(m) {
            const h = Math.floor(m / 60), mm = Math.round(m % 60);
            return h > 0 ? `${h}h ${mm}m` : `${mm}m`;
        }

        document.getElementById('dt-total').textContent    = fmtDur(totalDownMins);
        document.getElementById('dt-events').textContent   = totalEvents;
        document.getElementById('dt-uptime').textContent   = uptimePct + '%';
    }

    calcDowntimeKPIs();
    // ────────────────────────────────────────────────────────────────

    updateHeartbeat();
    setInterval(updateHeartbeat, 30000);
});
