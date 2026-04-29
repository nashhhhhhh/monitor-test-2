document.addEventListener("DOMContentLoaded", () => {
    const statusLight = document.getElementById("status-indicator-light");
    const statusText = document.getElementById("overall-status-text");
    const lastSyncEl = document.getElementById("last-sync");
    const container = document.getElementById("health-tiles");
    const alertBox = document.getElementById("global-alert-box");

    function setText(id, value) {
        const el = document.getElementById(id);
        if (el) el.textContent = value;
    }

    function fmtHours(hours) {
        if (hours === null || hours === undefined || Number.isNaN(Number(hours))) return "--";
        const numeric = Number(hours);
        if (numeric <= 0) return "0 min";
        if (numeric < 1) return `${Math.round(numeric * 60)} min`;
        if (numeric >= 24) {
            const days = Math.max(1, Math.round(numeric / 24));
            return `${days} ${days === 1 ? "day" : "days"}`;
        }

        const wholeHours = Math.floor(numeric);
        const minutes = Math.round((numeric - wholeHours) * 60);
        if (minutes === 60) return `${wholeHours + 1} hr`;
        if (minutes > 0) return `${wholeHours} hr ${minutes} min`;
        return `${wholeHours} hr`;
    }

    function formatMonthKey(date) {
        return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
    }

    function shiftMonthKey(monthKey, offset) {
        const [year, month] = String(monthKey || "").split("-").map(Number);
        if (!year || !month) return null;
        return formatMonthKey(new Date(year, month - 1 + offset, 1));
    }

    function formatMonthLabel(monthKey) {
        const [year, month] = String(monthKey || "").split("-").map(Number);
        if (!year || !month) return "current month";
        return new Date(year, month - 1, 1).toLocaleDateString("en-GB", { month: "short", year: "numeric" });
    }

    function getDowntimeHours(summary = {}) {
        const total = Number(summary.total_hours);
        if (Number.isFinite(total)) return total;
        const monthTotal = Number(summary.this_month_hours);
        return Number.isFinite(monthTotal) ? monthTotal : 0;
    }

    function buildDowntimeComparison(currentHours, previousHours, hasPreviousData) {
        if (!hasPreviousData) {
            return { comparison: "No previous month comparison", trend: "Trend: stable" };
        }

        if (previousHours <= 0 && currentHours <= 0) {
            return { comparison: "vs last month: 0%", trend: "Trend: stable" };
        }
        if (previousHours <= 0) {
            return { comparison: "vs last month: new downtime", trend: "Trend: worsening" };
        }

        const pct = ((currentHours - previousHours) / previousHours) * 100;
        const formattedPct = `${pct > 0 ? "+" : ""}${Math.round(pct)}%`;
        const trend = pct < 0 ? "improving" : pct > 0 ? "worsening" : "stable";
        return { comparison: `vs last month: ${formattedPct}`, trend: `Trend: ${trend}` };
    }

    function isWorkOrderRepairEvent(event) {
        const sourceText = `${event?.source || ""} ${event?.detection_type || ""} ${event?.duration_context || ""}`.toLowerCase();
        return sourceText.includes("work order") || sourceText.includes("ttr");
    }

    function calculateMttr(events = []) {
        const durations = events
            .filter(isWorkOrderRepairEvent)
            .map((event) => Number(event?.duration_hours))
            .filter((duration) => Number.isFinite(duration) && duration > 0);

        if (!durations.length) return { averageHours: null, count: 0 };

        const totalHours = durations.reduce((sum, duration) => sum + duration, 0);
        return { averageHours: totalHours / durations.length, count: durations.length };
    }

    function setCardTone(cardId, toneClass) {
        const card = document.getElementById(cardId);
        if (!card) return;
        card.classList.remove("dt-red", "dt-amber", "dt-purple", "dt-green", "dt-link");
        card.classList.add(toneClass);
    }

    async function fetchJsonNoStore(url) {
        const separator = url.includes("?") ? "&" : "?";
        const response = await fetch(`${url}${separator}_=${Date.now()}`, { cache: "no-store" });
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        return response.json();
    }

    async function loadDowntimePayload(period = "ytd") {
        try {
            return await fetchJsonNoStore(`/api/downtime?period=${encodeURIComponent(period)}`);
        } catch (error) {
            console.warn("Overview downtime API load failed, falling back to cache:", error);
        }

        const cacheResponse = await fetch(`/Downtime/downtime-cache.json?v=20260420-ttr-window&_=${Date.now()}`, {
            cache: "no-store",
        });
        if (!cacheResponse.ok) {
            throw new Error(`HTTP ${cacheResponse.status}`);
        }
        const cachePayload = await cacheResponse.json();
        return cachePayload?.payloads?.[period] || {};
    }

    async function loadDowntimeMonthPayload(month) {
        try {
            return await fetchJsonNoStore(`/api/downtime?period=mtd&month=${encodeURIComponent(month)}`);
        } catch (error) {
            console.warn("Overview monthly downtime API load failed, falling back to cache:", error);
        }

        const cacheResponse = await fetch(`/Downtime/downtime-cache.json?v=20260420-ttr-window&_=${Date.now()}`, {
            cache: "no-store",
        });
        if (!cacheResponse.ok) {
            throw new Error(`HTTP ${cacheResponse.status}`);
        }
        const cachePayload = await cacheResponse.json();
        return cachePayload?.payloads?.[`mtd:${month}`] || {};
    }

    function getCurrentMonthKey() {
        return formatMonthKey(new Date());
    }

    async function loadMaintenanceMonthPayload(month = getCurrentMonthKey()) {
        return fetchJsonNoStore(`/api/maintenance/overview?month=${encodeURIComponent(month)}&mix_month=${encodeURIComponent(month)}`);
    }

    async function loadHealthPayload() {
        return fetchJsonNoStore("/api/overview/health-fast");
    }

    function latestMetricValue(rows, keyCandidates = []) {
        if (!Array.isArray(rows) || !rows.length) return null;
        const latest = rows[rows.length - 1] || {};
        for (const key of keyCandidates) {
            const numeric = Number(latest?.[key]);
            if (Number.isFinite(numeric)) return numeric;
        }
        return null;
    }

    function computeLightingAverageHealth(fixtures = []) {
        const healthValues = fixtures
            .map((fixture) => Number(fixture?.["Lamp Life Remaining"]))
            .filter((value) => Number.isFinite(value))
            .map((value) => Math.max(0, Math.min(100, (value / 20000) * 100)));

        if (!healthValues.length) return null;
        const average = healthValues.reduce((sum, value) => sum + value, 0) / healthValues.length;
        return Math.round(average * 10) / 10;
    }

    async function enrichSystemsFromPageApis(systems = []) {
        const systemMap = new Map(systems.map((system) => [String(system?.id || "").toLowerCase(), system]));
        const enrichers = [];

        if (systemMap.has("mdb")) {
            enrichers.push(
                fetchJsonNoStore("/api/mdb/summary").then((data) => {
                    const latest = Number(data?.energy?.emdb_1?.latest);
                    if (Number.isFinite(latest)) {
                        systemMap.get("mdb").value = `${latest.toLocaleString()} kWh`;
                    }
                }).catch((error) => console.warn("Overview MDB sync failed:", error))
            );
        }

        if (systemMap.has("wtp")) {
            enrichers.push(
                fetchJsonNoStore("/api/wtp").then((data) => {
                    const roTotal = Number(data?.flow_totals?.ro_water?.slice(-1)[0]?.m3 || 0);
                    const soft1Total = Number(data?.flow_totals?.soft_water_1?.slice(-1)[0]?.m3 || 0);
                    const soft2Total = Number(data?.flow_totals?.soft_water_2?.slice(-1)[0]?.m3 || 0);
                    const total = roTotal + soft1Total + soft2Total;
                    systemMap.get("wtp").value = `${total.toLocaleString()} m³`;
                }).catch((error) => console.warn("Overview WTP sync failed:", error))
            );
        }

        if (systemMap.has("wwtp")) {
            enrichers.push(
                fetchJsonNoStore("/api/wwtp/latest").then((data) => {
                    const latestEffluent = Number(data?.effluent?.slice(-1)[0]?.value || 0);
                    const latestRaw = Number(data?.rawPump?.slice(-1)[0]?.value || 0);
                    const activePumps = (latestEffluent > 0 ? 1 : 0) + (latestRaw > 0 ? 1 : 0);
                    systemMap.get("wwtp").value = `${activePumps} Active ${activePumps === 1 ? "Pump" : "Pumps"}`;
                }).catch((error) => console.warn("Overview WWTP sync failed:", error))
            );
        }

        if (systemMap.has("temp")) {
            enrichers.push(
                fetchJsonNoStore("/api/temperature/rooms").then((rooms) => {
                    const roomCount = Array.isArray(rooms) ? rooms.length : 0;
                    systemMap.get("temp").value = `${roomCount.toLocaleString()} Rooms Monitored`;
                }).catch((error) => console.warn("Overview temperature sync failed:", error))
            );
        }

        if (systemMap.has("sbf")) {
            enrichers.push(
                fetchJsonNoStore("/api/spiral_blast_freezer").then((data) => {
                    const statusData = data?.status_data || {};
                    const spiralKeys = Object.keys(statusData);
                    const linesOnline = spiralKeys.filter((key) => Array.isArray(statusData[key]?.data) && statusData[key].data.length > 0).length;
                    systemMap.get("sbf").value = `${linesOnline} Lines Online`;
                }).catch((error) => console.warn("Overview spiral freezer sync failed:", error))
            );
        }

        if (systemMap.has("cctv")) {
            enrichers.push(
                fetchJsonNoStore("/api/cctv/log").then((rows) => {
                    const cameras = Array.isArray(rows) ? rows : [];
                    const total = cameras.length;
                    const offline = cameras.filter((camera) => String(camera?.status || "").toLowerCase() !== "online").length;
                    const online = Math.max(0, total - offline);
                    systemMap.get("cctv").value = `${online} / ${total} Online`;
                }).catch((error) => console.warn("Overview CCTV sync failed:", error))
            );
        }

        if (systemMap.has("lighting")) {
            enrichers.push(
                fetchJsonNoStore("/api/lighting").then((data) => {
                    const fixtures = Array.isArray(data?.fixtures) ? data.fixtures : [];
                    const averageHealth = computeLightingAverageHealth(fixtures);
                    systemMap.get("lighting").value = averageHealth == null
                        ? `${fixtures.length.toLocaleString()} Fixtures`
                        : `${averageHealth.toLocaleString()}% Avg Health`;
                }).catch((error) => console.warn("Overview lighting sync failed:", error))
            );
        }

        if (systemMap.has("boiler")) {
            enrichers.push(
                fetchJsonNoStore("/api/boiler").then((data) => {
                    const direct = latestMetricValue(data?.consumption?.direct_energy_kwh, ["energy", "value", "kwh"]) || 0;
                    const indirect = latestMetricValue(data?.consumption?.indirect_energy_kwh, ["energy", "value", "kwh"]) || 0;
                    systemMap.get("boiler").value = `${(direct + indirect).toLocaleString()} kWh`;
                }).catch((error) => console.warn("Overview boiler sync failed:", error))
            );
        }

        if (systemMap.has("air")) {
            enrichers.push(
                fetchJsonNoStore("/api/aircompressor").then((data) => {
                    const latestFlow = latestMetricValue(data?.flow, ["flow", "value", "m3"]);
                    if (latestFlow != null) {
                        systemMap.get("air").value = `${latestFlow.toLocaleString(undefined, { maximumFractionDigits: 2 })} Flow`;
                    }
                }).catch((error) => console.warn("Overview air sync failed:", error))
            );
        }

        await Promise.all(enrichers);
        return systems;
    }
    async function applyWastewaterPumpKpi(systems) {
        const wastewater = systems.find((system) => system.id === "wwtp");
        if (!wastewater) return systems;

        try {
            const response = await fetch(`/api/wwtp/latest?_=${Date.now()}`, { cache: "no-store" });
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const data = await response.json();
            const latestEffluent = Number(data?.effluent?.slice(-1)[0]?.value || 0);
            const latestRaw = Number(data?.rawPump?.slice(-1)[0]?.value || 0);
            const activePumps = (latestEffluent > 0 ? 1 : 0) + (latestRaw > 0 ? 1 : 0);
            wastewater.value = `${activePumps} Active ${activePumps === 1 ? "Pump" : "Pumps"}`;
        } catch (error) {
            console.warn("Wastewater pump KPI load failed:", error);
        }

        return systems;
    }

    async function applyWaterTreatmentKpi(systems) {
        const waterTreatment = systems.find((system) => system.id === "wtp");
        if (!waterTreatment) return systems;

        try {
            const response = await fetch(`/api/wtp?_=${Date.now()}`, { cache: "no-store" });
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const data = await response.json();
            const roTotal = Number(data?.flow_totals?.ro_water?.slice(-1)[0]?.m3 || 0);
            const soft1Total = Number(data?.flow_totals?.soft_water_1?.slice(-1)[0]?.m3 || 0);
            const soft2Total = Number(data?.flow_totals?.soft_water_2?.slice(-1)[0]?.m3 || 0);
            const treatedTotal = roTotal + soft1Total + soft2Total;

            if (treatedTotal > 0) {
                waterTreatment.value = `${treatedTotal.toLocaleString()} m³`;
            }
        } catch (error) {
            console.warn("Water Treatment KPI load failed:", error);
        }

        return systems;
    }

    async function updateHeartbeat() {
        let processedData = [];
        let lastSynced = null;

        try {
            const payload = await loadHealthPayload();
            processedData = payload.systems || [];
            processedData = await enrichSystemsFromPageApis(processedData);
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

    async function updateDowntimeStrip() {
        try {
            const ytdPayload = await loadDowntimePayload("ytd");
            const currentCalendarMonth = getCurrentMonthKey();
            const availableDowntimeMonths = (ytdPayload?.months || []).map((row) => row.value).filter(Boolean);
            const selectedMonth = availableDowntimeMonths.includes(currentCalendarMonth)
                ? currentCalendarMonth
                : (availableDowntimeMonths[0] || currentCalendarMonth);
            const previousMonth = shiftMonthKey(selectedMonth, -1);

            const [currentMonthPayload, previousMonthPayload, maintenancePayload, healthPayload] = await Promise.all([
                loadDowntimeMonthPayload(selectedMonth),
                previousMonth ? loadDowntimeMonthPayload(previousMonth) : Promise.resolve(null),
                loadMaintenanceMonthPayload(selectedMonth),
                loadHealthPayload(),
            ]);

            const currentMonthLabel = currentMonthPayload?.meta?.month_label || formatMonthLabel(selectedMonth);
            const currentHours = getDowntimeHours(currentMonthPayload?.summary);
            const previousHours = getDowntimeHours(previousMonthPayload?.summary);
            const hasPreviousData = Boolean(
                previousMonth
                && (
                    availableDowntimeMonths.includes(previousMonth)
                    || Number(previousMonthPayload?.summary?.event_count || 0) > 0
                    || previousHours > 0
                )
            );
            const downtimeTrend = buildDowntimeComparison(currentHours, previousHours, hasPreviousData);

            const monthlyMttr = calculateMttr(currentMonthPayload?.events || []);
            const ytdMttr = calculateMttr(ytdPayload?.events || []);
            const mttr = monthlyMttr.count ? monthlyMttr : ytdMttr;
            const mttrBasis = monthlyMttr.count
                ? `${currentMonthLabel} from work order TTR (${monthlyMttr.count} jobs)`
                : (ytdMttr.count ? `YTD fallback from work order TTR (${ytdMttr.count} jobs)` : "No valid TTR data");

            const maintenanceMix = maintenancePayload?.maintenance_mix || {};
            const preventiveCount = Number(maintenanceMix.preventive_scheduled_count || 0);
            const correctiveCount = Number(maintenanceMix.corrective_work_order_count || 0);
            const maintenanceVariance = correctiveCount - preventiveCount;
            const varianceText = maintenanceVariance > 0
                ? `+${maintenanceVariance.toLocaleString()} corrective above preventive`
                : maintenanceVariance < 0
                    ? `Corrective ${Math.abs(maintenanceVariance).toLocaleString()} below preventive`
                    : "Corrective matches preventive";

            const systems = healthPayload?.systems || [];
            const criticalStatuses = new Set(["CRITICAL", "OFFLINE"]);
            const warningStatuses = new Set(["ATTENTION", "WARNING"]);
            const criticalCount = systems.filter((system) => criticalStatuses.has(String(system?.status || "").toUpperCase())).length;
            const warningCount = systems.filter((system) => warningStatuses.has(String(system?.status || "").toUpperCase())).length;
            const attentionCount = criticalCount + warningCount;

            setText("dt-total-label", "Downtime This Month");
            setText("dt-total", fmtHours(currentHours));
            setText("dt-total-sub", `${currentMonthLabel} ${downtimeTrend.comparison}`);
            setText("dt-total-trend", downtimeTrend.trend);

            setText("dt-events-label", "Average MTTR");
            setText("dt-events", mttr.count ? fmtHours(mttr.averageHours) : "--");
            setText("dt-events-sub", mttrBasis);

            setText("dt-period-label", "Preventive vs Corrective");
            setText("dt-period", `${preventiveCount.toLocaleString()} vs ${correctiveCount.toLocaleString()}`);
            setText("dt-period-sub", varianceText);

            setText("dt-critical-label", "Active Critical Issues");
            setText("dt-critical", attentionCount.toLocaleString());
            if (criticalCount > 0) {
                setText("dt-critical-sub", `${criticalCount} critical system(s), ${warningCount} warning`);
                setCardTone("dt-critical-card", "dt-red");
            } else if (warningCount > 0) {
                setText("dt-critical-sub", `${warningCount} system(s) need attention`);
                setCardTone("dt-critical-card", "dt-amber");
            } else {
                setText("dt-critical-sub", "No critical issues active");
                setCardTone("dt-critical-card", "dt-green");
            }
        } catch (error) {
            console.error("Overview downtime strip load failed:", error);
            setText("dt-total", "--");
            setText("dt-events", "--");
            setText("dt-period", "--");
            setText("dt-critical", "--");
            setText("dt-total-sub", "No data available");
            setText("dt-total-trend", "Trend unavailable");
            setText("dt-events-sub", "No valid TTR data");
            setText("dt-period-sub", "Maintenance mix unavailable");
            setText("dt-critical-sub", "System status unavailable");
        }
    }

    function refreshOverview() {
        updateDowntimeStrip();
        updateHeartbeat();
    }

    refreshOverview();
    setInterval(updateHeartbeat, 30000);
    setInterval(updateDowntimeStrip, 60000);

    window.addEventListener("focus", refreshOverview);
    document.addEventListener("visibilitychange", () => {
        if (!document.hidden) refreshOverview();
    });
});
