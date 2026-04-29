document.addEventListener("DOMContentLoaded", async () => {
    const utils = window.lightingMonitoringUtils;
    const charts = {};
    let refreshHandle = null;
    const LIGHTING_ZONE_CONFIG = [
        {
            id: "ow-1f",
            title: "Outgoing WH. 1st Floor",
            colorClass: "zone-blue-left",
            markerX: 12,
            markerY: 10,
            entries: [
                { label: "Area 2 LCP-OW-01", aliases: ["lcp-ow-01", "outgoing warehouse"] },
                { label: "Area 3 ELCP-OW-01", aliases: ["elcp-ow-01", "dispatch office"] }
            ]
        },
        {
            id: "hr-1f",
            title: "HR Area 1st Floor",
            colorClass: "zone-green",
            markerX: 28,
            markerY: 22,
            entries: [
                { label: "Area 4 LCP-HR-01", aliases: ["lcp-hr-01", "hr area", "hr room"] },
                { label: "Area 5 ELCP-HR-01", aliases: ["elcp-hr-01", "label printing", "uv entrance", "packaging store"] }
            ]
        },
        {
            id: "lr-1f",
            title: "LR Area 1st Floor",
            colorClass: "zone-red",
            markerX: 47,
            markerY: 24,
            entries: [
                { label: "Area 6 LCP-LR-01", aliases: ["lcp-lr-01", "lr area"] },
                { label: "Area 7 ELCP-LR-01", aliases: ["elcp-lr-01", "lr area"] }
            ]
        },
        {
            id: "iw-1f",
            title: "IW Area 1st Floor",
            colorClass: "zone-blue-right",
            markerX: 82,
            markerY: 18,
            entries: [
                { label: "Area 6 LCP-LR-01", aliases: ["lcp-lr-01", "lr area"] },
                { label: "Area 7 ELCP-LR-01", aliases: ["elcp-lr-01", "lr area"] },
                { label: "Area 8 LCP-IW-01", aliases: ["lcp-iw-01", "incoming warehouse 3", "incoming warehouse 2"] },
                { label: "Area 9 ELCP-IW-01", aliases: ["elcp-iw-01", "incoming warehouse 3", "incoming warehouse 2"] },
                { label: "Area 10 LCP-IW(OF)-01", aliases: ["lcp-iw(of)-01", "grn office", "corridor 1", "corridor 2", "office 1"] }
            ]
        },
        {
            id: "f1-f6",
            title: "Area Line F1-F6",
            colorClass: "zone-yellow",
            markerX: 17,
            markerY: 83,
            entries: [
                { label: "Area 2 LCP-OW-01", aliases: ["lcp-ow-01", "outgoing warehouse"] },
                { label: "Area 3 ELCP-OW-01", aliases: ["elcp-ow-01", "dispatch office"] },
                { label: "Area 50 OW Corridor (Sensor)", aliases: ["ow corridor", "corridor", "ambient packaging"] },
                { label: "Area 51 OW Changing Room (Sensor)", aliases: ["ow changing room", "changing room"] },
                { label: "Area 52 OW Toilet Male (Sensor)", aliases: ["ow toilet male", "toilet male"] },
                { label: "Area 53 OW Toilet Female (Sensor)", aliases: ["ow toilet female", "toilet female"] }
            ]
        },
        {
            id: "f7-f13",
            title: "Area Line F7-F13",
            colorClass: "zone-white",
            markerX: 41,
            markerY: 83,
            entries: [
                { label: "Area 1", aliases: ["area 1"] },
                { label: "Area 2 LCP-OW-01", aliases: ["lcp-ow-01", "outgoing warehouse"] },
                { label: "Area 3 ELCP-OW-01", aliases: ["elcp-ow-01", "dispatch office"] },
                { label: "Area 4 LCP-HR-01", aliases: ["lcp-hr-01", "hr area", "hr room"] },
                { label: "Area 5 ELCP-HR-01", aliases: ["elcp-hr-01", "label printing", "uv entrance", "packaging store"] },
                { label: "Area 6 LCP-LR-01", aliases: ["lcp-lr-01", "lr area"] },
                { label: "Area 54 HR Corridor (Sensor)", aliases: ["hr corridor", "hr area"] },
                { label: "Area 55 HR Toilet Male (Sensor)", aliases: ["hr toilet male", "toilet male"] },
                { label: "Area 57 HR Toilet Female (Sensor)", aliases: ["hr toilet female", "toilet female"] }
            ]
        },
        {
            id: "f14-f19",
            title: "Area Line F14-F19",
            colorClass: "zone-orange",
            markerX: 67,
            markerY: 87,
            entries: [
                { label: "Area 6 LCP-LR-01", aliases: ["lcp-lr-01", "lr area"] },
                { label: "Area 7 ELCP-LR-01", aliases: ["elcp-lr-01", "lr area"] },
                { label: "Area 58 LR Corridor Toilet", aliases: ["lr corridor", "lr toilet"] },
                { label: "Area 59 LR Toilet Male", aliases: ["lr toilet male", "toilet male"] },
                { label: "Area 61 LR Toilet Female", aliases: ["lr toilet female", "toilet female"] }
            ]
        }
    ];
    const state = {
        search: "",
        selectedAreas: new Set(),
        alertOnly: false,
        selectedLightingZoneId: null
    };

    if (!utils) {
        console.error("Lighting monitoring helpers are unavailable.");
        return;
    }

    const searchInput = document.getElementById("lighting-search");
    const areaFilterList = document.getElementById("area-filter-list");
    const areaFilterAll = document.getElementById("area-filter-all");
    const areaFilterClear = document.getElementById("area-filter-clear");
    const alertOnlyToggle = document.getElementById("alert-only-toggle");
    const areaSections = document.getElementById("area-sections");
    const lightingZoneList = document.getElementById("lighting-zone-list");
    const lightingZoneMeta = document.getElementById("lighting-zone-meta");
    const lightingFloorplanMarkers = document.getElementById("lighting-floorplan-markers");
    let currentSummary = null;

    await refreshLightingPage();

    searchInput?.addEventListener("input", (event) => {
        state.search = event.target.value.trim().toLowerCase();
        renderAreaSections(currentSummary);
    });

    areaFilterAll?.addEventListener("click", () => {
        state.selectedAreas.clear();
        syncAreaFilterButtons();
        renderAreaSections(currentSummary);
    });

    areaFilterClear?.addEventListener("click", () => {
        state.selectedAreas.clear();
        syncAreaFilterButtons();
        renderAreaSections(currentSummary);
    });

    alertOnlyToggle?.addEventListener("click", () => {
        state.alertOnly = !state.alertOnly;
        alertOnlyToggle.classList.toggle("active", state.alertOnly);
        alertOnlyToggle.setAttribute("aria-pressed", String(state.alertOnly));
        alertOnlyToggle.textContent = state.alertOnly ? "Showing Alerted Fixtures Only" : "Show Alerted Fixtures Only";
        renderAreaSections(currentSummary);
    });

    refreshHandle = window.setInterval(() => {
        refreshLightingPage({ preserveFilters: true }).catch((error) => {
            console.warn("Lighting auto-refresh failed:", error);
        });
    }, 60000);

    window.addEventListener("focus", () => {
        refreshLightingPage({ preserveFilters: true }).catch((error) => {
            console.warn("Lighting focus refresh failed:", error);
        });
    });

    document.addEventListener("visibilitychange", () => {
        if (!document.hidden) {
            refreshLightingPage({ preserveFilters: true }).catch((error) => {
                console.warn("Lighting visibility refresh failed:", error);
            });
        }
    });

    async function refreshLightingPage({ preserveFilters = false } = {}) {
        const dataset = await loadLightingDataset();
        const summary = utils.summarizePortfolio(dataset);
        const runtimeFixtures = normalizeRuntimeFixtures(dataset.channelRuntimeRows || dataset.fixtures || []);

        currentSummary = summary;

        populateSummary(summary);
        populateAreaFilter(summary);
        renderNotionalEnergyModule(summary);
        renderLightingFloorplan(summary, runtimeFixtures);

        requestAnimationFrame(() => {
            setTimeout(() => renderAreaSections(summary), 0);
        });
    }

    function formatNumber(value, digits = 1) {
        return utils.round(value, digits).toLocaleString(undefined, {
            minimumFractionDigits: digits === 0 ? 0 : 0,
            maximumFractionDigits: digits
        });
    }

    function formatMetric(value, suffix = "", digits = 1) {
        if (value == null) return "No data";
        return `${formatNumber(value, digits)}${suffix}`;
    }

    function populateSummary(currentSummary) {
        setText("summary-total-fixtures", currentSummary.totals.totalFixtures.toLocaleString());
        setText("summary-healthy-fixtures", currentSummary.totals.healthyFixtures.toLocaleString());
        setText("summary-warning-fixtures", currentSummary.totals.warningFixtures.toLocaleString());
        setText("summary-critical-fixtures", currentSummary.totals.criticalFixtures.toLocaleString());
        setText("summary-total-energy", `${formatNumber(currentSummary.totals.totalEnergyConsumption, 1)} kWh`);
        setText("summary-average-health", `${formatNumber(currentSummary.averageHealthScore, 1)}%`);

    }

    function populateAreaFilter(currentSummary) {
        areaFilterList.innerHTML = currentSummary.areas.map((area) => `
            <button
                type="button"
                class="area-chip"
                data-area="${escapeHTML(area.areaName)}"
                aria-pressed="false"
            >
                ${escapeHTML(area.areaName)}
            </button>
        `).join("");

        areaFilterList.querySelectorAll(".area-chip").forEach((button) => {
            button.addEventListener("click", () => {
                const areaName = button.dataset.area;
                if (!areaName) return;

                if (state.selectedAreas.has(areaName)) {
                    state.selectedAreas.delete(areaName);
                } else {
                    state.selectedAreas.add(areaName);
                }

                syncAreaFilterButtons();
                renderAreaSections(currentSummary);
            });
        });

        syncAreaFilterButtons();
    }

    function renderNotionalEnergyModule(currentSummary) {
        const totalLightingKwh = currentSummary.totals.totalEnergyConsumption;
        const topArea = currentSummary.highestConsumingRoom;

        setText("lighting-energy-total", `${formatNumber(totalLightingKwh, 1)} kWh`);
        setText("lighting-energy-health-meta", `${formatNumber(currentSummary.averageHealthScore, 1)}% portfolio average fixture health`);
        setText(
            "lighting-energy-top-area",
            topArea
                ? `Highest lighting area: ${topArea.roomName} (${formatNumber(topArea.totalEnergyConsumption, 1)} kWh)`
                : "No area breakdown available"
        );

        const energyBreakdown = document.getElementById("lighting-energy-breakdown");
        if (energyBreakdown) {
            energyBreakdown.innerHTML = currentSummary.areas
                .slice(0, 6)
                .map((area) => `
                    <div class="lighting-breakdown-item">
                        <span class="lighting-breakdown-room">${escapeHTML(area.areaName)}</span>
                        <span class="lighting-breakdown-kwh">${formatNumber(area.totalNotionalEnergy, 1)} kWh</span>
                    </div>
                `)
                .join("");
        }

        createChart("lighting-area-energy-chart", {
            type: "bar",
            data: {
                labels: currentSummary.areas.slice(0, 6).map((area) => area.areaName),
                datasets: [{
                    label: "Lighting Energy (kWh)",
                    data: currentSummary.areas.slice(0, 6).map((area) => area.totalNotionalEnergy),
                    backgroundColor: "#2563eb",
                    borderRadius: 10
                }]
            },
            options: chartOptions({ horizontal: true })
        });
    }

    function renderLightingFloorplan(currentSummary, runtimeRows) {
        const zoneSummaries = LIGHTING_ZONE_CONFIG.map((zone) => summarizeLightingZone(zone, runtimeRows));
        if (!state.selectedLightingZoneId || !zoneSummaries.some((zone) => zone.id === state.selectedLightingZoneId)) {
            state.selectedLightingZoneId = zoneSummaries[0]?.id || null;
        }
        const selectedZone = zoneSummaries.find((zone) => zone.id === state.selectedLightingZoneId) || null;

        if (lightingZoneMeta) {
            lightingZoneMeta.textContent = selectedZone
                ? `${selectedZone.title}`
                : `${zoneSummaries.length} configured zones`;
        }

        if (lightingFloorplanMarkers) {
            lightingFloorplanMarkers.innerHTML = zoneSummaries.map((zone) => `
                <button type="button" class="lighting-zone-pin ${zone.colorClass}${zone.id === state.selectedLightingZoneId ? " is-active" : ""}" data-zone-target="${zone.id}">
                    <span class="lighting-zone-pin-title">${escapeHTML(zone.shortTitle)}</span>
                    <strong>${zone.coverageText}</strong>
                </button>
            `).join("");

            lightingFloorplanMarkers.querySelectorAll(".lighting-zone-pin").forEach((button) => {
                button.addEventListener("click", () => {
                    state.selectedLightingZoneId = button.dataset.zoneTarget || null;
                    renderLightingFloorplan(currentSummary, runtimeRows);
                    const target = document.getElementById(`lighting-zone-card-${state.selectedLightingZoneId}`);
                    target?.scrollIntoView({ behavior: "smooth", block: "center" });
                    target?.classList.add("flash-focus");
                    window.setTimeout(() => target?.classList.remove("flash-focus"), 1400);
                });
            });

            zoneSummaries.forEach((zone, index) => {
                const marker = lightingFloorplanMarkers.children[index];
                if (!marker) return;
                marker.style.left = `${zone.markerX}%`;
                marker.style.top = `${zone.markerY}%`;
            });
        }

        if (lightingZoneList) {
            const visibleZones = selectedZone ? [selectedZone] : zoneSummaries;
            lightingZoneList.innerHTML = visibleZones.map((zone) => `
                <article class="lighting-zone-card ${zone.colorClass}" id="lighting-zone-card-${zone.id}">
                    <div class="lighting-zone-card-head">
                        <div>
                            <div class="lighting-zone-title">${escapeHTML(zone.title)}</div>
                            <div class="lighting-zone-subtitle">${escapeHTML(zone.coverageNote)}</div>
                        </div>
                        <div class="lighting-zone-percentage">${zone.coverageText}</div>
                    </div>
                    <div class="lighting-zone-metrics">
                        <span>${zone.matchedFixtures} channel box fixtures</span>
                        <span>${zone.averageHealthPct.toFixed(1)}% avg light health</span>
                        <span>${zone.totalWeightedEntries} mapped labels</span>
                    </div>
                    <div class="lighting-zone-entry-list">
                        ${zone.entries.map((entry) => `
                            <div class="lighting-zone-entry">
                                <span class="lighting-zone-entry-label">${escapeHTML(entry.label)}</span>
                                <span class="lighting-zone-entry-value">${entry.coverageText}</span>
                            </div>
                        `).join("")}
                    </div>
                </article>
            `).join("");
        }
    }

    function summarizeLightingZone(zone, fixtures) {
        const entries = zone.entries.map((entry) => summarizeZoneEntry(entry, fixtures));
        const zoneFixtureMap = new Map();
        entries.forEach((entry) => {
            entry.fixtures.forEach((fixture) => {
                zoneFixtureMap.set(fixture.fixtureKey, fixture);
            });
        });
        const zoneFixtures = [...zoneFixtureMap.values()];
        const zoneFixtureTotal = zoneFixtures.length;
        const matchedFixtures = zoneFixtureTotal;
        const totalHealthWeight = zoneFixtures.reduce((sum, fixture) => sum + (fixture.fixtureHealthPct ?? 0), 0);
        const coveragePct = zoneFixtureTotal
            ? utils.round(totalHealthWeight / zoneFixtureTotal, 1)
            : 0;

        return {
            ...zone,
            shortTitle: zone.title.replace(" 1st Floor", "").replace("Area Line ", ""),
            coveragePct,
            coverageText: `${coveragePct.toFixed(1)}%`,
            coverageNote: matchedFixtures
                ? "Based on mapped box-level channel runtime rows and their light health"
                : "No mapped lighting fixtures found yet for this highlighted zone",
            totalWeightedEntries: zone.entries.length,
            matchedFixtures,
            averageHealthPct: coveragePct,
            entries
        };
    }

    function summarizeZoneEntry(entry, fixtures) {
        const matchedFixtures = getEntryFixtures(entry, fixtures);
        const totalHealthWeight = matchedFixtures.reduce((sum, fixture) => sum + (fixture.fixtureHealthPct ?? 0), 0);
        const coveragePct = matchedFixtures.length
            ? utils.round(totalHealthWeight / matchedFixtures.length, 1)
            : 0;

        return {
            ...entry,
            fixtures: matchedFixtures,
            matchedFixtures: matchedFixtures.length,
            totalHealthWeight,
            coveragePct,
            coverageText: matchedFixtures.length
                ? `${coveragePct.toFixed(1)}% (${matchedFixtures.length} fixtures)`
                : "No data"
        };
    }

    function normalizeRuntimeFixtures(fixtures) {
        const fixtureMap = new Map();

        fixtures.forEach((fixture) => {
            const areaName = String(fixture["Area Name"] || "").trim();
            const circuitName = String(fixture["Circuit Name"] || "").trim();
            const fixtureName = String(fixture["Fixture Name"] || "").trim();
            if (!areaName || !fixtureName) return;

            const fixtureKey = [normalizeAreaName(areaName), circuitName.toLowerCase(), fixtureName.toLowerCase()].join("|");
            const runtimeHours = Number(fixture["Hours On In Period"] || 0);
            const runningHours = Number(fixture["Hours On Running"] || 0);
            const notionalEnergy = Number(fixture["Notional Energy"] || 0);
            const fixtureHealthPct = utils.computeFixtureHealth(fixture["Lamp Life Remaining"]);

            const existing = fixtureMap.get(fixtureKey);
            if (!existing) {
                fixtureMap.set(fixtureKey, {
                    fixtureKey,
                    areaName,
                    normalizedAreaName: normalizeAreaName(areaName),
                    circuitName,
                    fixtureName,
                    runtimeHours,
                    runningHours,
                    notionalEnergy,
                    fixtureHealthPct
                });
                return;
            }

            existing.runtimeHours = Math.max(existing.runtimeHours, runtimeHours);
            existing.runningHours = Math.max(existing.runningHours, runningHours);
            existing.notionalEnergy = Math.max(existing.notionalEnergy, notionalEnergy);
            existing.fixtureHealthPct = Math.max(existing.fixtureHealthPct ?? 0, fixtureHealthPct ?? 0);
        });

        return [...fixtureMap.values()];
    }

    function getEntryFixtures(entry, fixtures) {
        const normalizedLabel = normalizeAreaName(entry.label);
        const exactMatches = fixtures.filter((fixture) => fixture.normalizedAreaName === normalizedLabel);
        if (exactMatches.length) return exactMatches;

        const haystackMatches = fixtures.filter((fixture) => matchesLightingAlias(fixture, entry.aliases));
        return haystackMatches;
    }

    function matchesLightingAlias(fixture, aliases = []) {
        const haystack = [
            fixture.areaName,
            fixture.circuitName,
            fixture.fixtureName
        ].map((value) => String(value || "").toLowerCase()).join(" | ");

        return aliases.some((alias) => haystack.includes(String(alias).toLowerCase()));
    }

    function normalizeAreaName(value) {
        return String(value || "").toLowerCase().replace(/\s+/g, " ").trim();
    }

    function renderAreaSections(currentSummary) {
        const filteredAreas = currentSummary.areas
            .map((area) => ({
                ...area,
                fixtures: area.fixtures.filter(matchesFilters)
            }))
            .filter((area) => area.fixtures.length > 0);

        if (!filteredAreas.length) {
            areaSections.innerHTML = '<div class="empty-state">No lighting fixtures match the current filters.</div>';
            return;
        }

        areaSections.innerHTML = filteredAreas.map((area) => {
            const areaKey = makeAreaKey(area.areaName);
            const filteredHealth = utils.round(
                area.fixtures.reduce((sum, fixture) => sum + (fixture.fixtureHealthPct ?? 0), 0) / (area.fixtures.length || 1),
                1
            );
            const filteredEnergy = utils.round(
                area.fixtures.reduce((sum, fixture) => sum + fixture["Notional Energy"], 0),
                3
            );
            const filteredCritical = area.fixtures.filter((fixture) => fixture.status === "Critical").length;

            return `
                <section class="area-section" id="section-${areaKey}">
                    <button class="area-section-header" type="button" onclick="toggleLightingAreaSection('${areaKey}')">
                        <div class="area-header-left">
                            <div class="zone-dot ${area.status.toLowerCase()}"></div>
                            <span class="area-name">${escapeHTML(area.areaName)}</span>
                            <span class="badge-total">${area.fixtures.length} fixtures</span>
                            <span class="badge-energy">${formatNumber(filteredEnergy, 1)} kWh</span>
                            <span class="badge-health">${formatNumber(filteredHealth, 1)}% avg health</span>
                            ${filteredCritical > 0 ? `<span class="badge-critical">${filteredCritical} critical</span>` : ""}
                        </div>
                        <span class="toggle-icon">&#9662;</span>
                    </button>
                    <div class="area-body">
                        <div class="area-summary-grid">
                            <article class="mini-card">
                                <span class="mini-label">Fixtures</span>
                                <strong>${area.fixtures.length}</strong>
                            </article>
                            <article class="mini-card">
                                <span class="mini-label">Total Notional Energy</span>
                                <strong>${formatNumber(filteredEnergy, 1)} kWh</strong>
                            </article>
                            <article class="mini-card">
                                <span class="mini-label">Average Fixture Health</span>
                                <strong>${formatNumber(filteredHealth, 1)}%</strong>
                            </article>
                            <article class="mini-card">
                                <span class="mini-label">Critical Fixtures</span>
                                <strong>${filteredCritical}</strong>
                            </article>
                        </div>
                        <div class="fixture-grid">
                            ${area.fixtures.map(renderFixtureCard).join("")}
                        </div>
                    </div>
                </section>
            `;
        }).join("");
    }

    function matchesFilters(fixture) {
        const areaMatch = state.selectedAreas.size === 0 || state.selectedAreas.has(fixture["Area Name"]);
        const alertMatch = !state.alertOnly || fixture.alerts.length > 0;
        const searchMatch = !state.search || [
            fixture["Fixture Name"],
            fixture["Area Name"],
            fixture["Circuit Name"]
        ].some((value) => String(value).toLowerCase().includes(state.search));

        return areaMatch && alertMatch && searchMatch;
    }

    function syncAreaFilterButtons() {
        const showAll = state.selectedAreas.size === 0;
        areaFilterAll?.classList.toggle("active", showAll);
        areaFilterClear?.classList.toggle("active", false);

        areaFilterList.querySelectorAll(".area-chip").forEach((button) => {
            const areaName = button.dataset.area;
            const isActive = areaName ? state.selectedAreas.has(areaName) : false;
            button.classList.toggle("active", isActive);
            button.setAttribute("aria-pressed", String(isActive));
        });
    }

    function renderFixtureCard(fixture) {
        return `
            <article class="fixture-card ${fixture.status.toLowerCase()}">
                <div class="fixture-card-head">
                    <div>
                        <h3>${escapeHTML(fixture["Fixture Name"])}</h3>
                        <div class="fixture-subtitle">${escapeHTML(fixture["Area Name"])} | ${escapeHTML(fixture["Circuit Name"])}</div>
                    </div>
                    <span class="status-pill ${fixture.status.toLowerCase()}">${fixture.status}</span>
                </div>
                <div class="health-row">
                    <div>
                        <div class="health-label">Fixture Health %</div>
                        <div class="health-value">${fixture.fixtureHealthPct == null ? "No data" : `${formatNumber(fixture.fixtureHealthPct, 1)}%`}</div>
                    </div>
                    <div class="health-bar">
                        <span style="width:${fixture.fixtureHealthPct ?? 0}%"></span>
                    </div>
                </div>
                <dl class="metric-list">
                    <div><dt>Fixture Name</dt><dd>${escapeHTML(fixture["Fixture Name"])}</dd></div>
                    <div><dt>Area Name</dt><dd>${escapeHTML(fixture["Area Name"])}</dd></div>
                    <div><dt>Circuit Name</dt><dd>${escapeHTML(fixture["Circuit Name"])}</dd></div>
                    <div><dt>Hours On In Period</dt><dd>${formatMetric(fixture["Hours On In Period"], " hrs", 0)}</dd></div>
                    <div><dt>Notional Energy</dt><dd>${formatMetric(fixture["Notional Energy"], " kWh", 3)}</dd></div>
                    <div><dt>Hours On Running</dt><dd>${formatMetric(fixture["Hours On Running"], " hrs", 0)}</dd></div>
                    <div><dt>Lamp Life Remaining</dt><dd>${formatMetric(fixture["Lamp Life Remaining"], " hrs", 0)}</dd></div>
                    <div><dt>Status</dt><dd>${fixture.status}</dd></div>
                </dl>
                <div class="alert-badges">
                    ${fixture.alerts.length
                        ? fixture.alerts.map((alert) => `<span class="severity-pill ${alert.severity}">${escapeHTML(alert.label)}</span>`).join("")
                        : '<span class="severity-pill neutral">No active alerts</span>'}
                </div>
            </article>
        `;
    }

    function chartOptions({ horizontal = false, suggestedMax, doughnut = false } = {}) {
        return {
            responsive: true,
            maintainAspectRatio: false,
            indexAxis: horizontal ? "y" : "x",
            cutout: doughnut ? "64%" : undefined,
            plugins: {
                legend: {
                    position: "bottom",
                    labels: {
                        usePointStyle: true,
                        boxWidth: 10,
                        font: { family: "Inter", size: 11 }
                    }
                }
            },
            scales: doughnut ? {} : {
                x: {
                    beginAtZero: true,
                    suggestedMax,
                    grid: { display: !horizontal, color: "rgba(148, 163, 184, 0.14)" },
                    ticks: { color: "#64748b" }
                },
                y: {
                    beginAtZero: true,
                    suggestedMax,
                    grid: { display: horizontal ? false : true, color: "rgba(148, 163, 184, 0.14)" },
                    ticks: { color: "#64748b" }
                }
            }
        };
    }

    function createChart(id, config) {
        const canvas = document.getElementById(id);
        if (!canvas || typeof Chart === "undefined") return;
        if (charts[id]) charts[id].destroy();
        charts[id] = new Chart(canvas, config);
    }

    async function loadLightingDataset() {
        try {
            const response = await fetch(`/api/lighting?_=${Date.now()}`, { cache: "no-store" });
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const data = await response.json();
            return {
                generatedAt: data?.generatedAt ?? null,
                meta: data?.meta ?? {},
                fixtures: Array.isArray(data?.fixtures) ? data.fixtures : []
            };
        } catch (error) {
            console.warn("Lighting API unavailable.", error);
        }

        return {
            generatedAt: null,
            meta: {},
            fixtures: []
        };
    }

    function setText(id, value) {
        const node = document.getElementById(id);
        if (node) node.textContent = value;
    }

    function escapeHTML(value) {
        return String(value).replace(/[&<>"']/g, (match) => ({
            "&": "&amp;",
            "<": "&lt;",
            ">": "&gt;",
            '"': "&quot;",
            "'": "&#39;"
        })[match]);
    }

    function makeAreaKey(value) {
        return String(value)
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, "-")
            .replace(/^-+|-+$/g, "");
    }
});

window.toggleLightingAreaSection = function toggleLightingAreaSection(areaKey) {
    document.getElementById(`section-${areaKey}`)?.classList.toggle("collapsed");
};
