document.addEventListener("DOMContentLoaded", async () => {
    const utils = window.lightingMonitoringUtils;
    const charts = {};
    const state = {
        search: "",
        status: "all",
        selectedAreas: new Set(),
        alertOnly: false
    };

    if (!utils) {
        console.error("Lighting monitoring helpers are unavailable.");
        return;
    }

    const searchInput = document.getElementById("lighting-search");
    const statusFilter = document.getElementById("status-filter");
    const areaFilterList = document.getElementById("area-filter-list");
    const areaFilterAll = document.getElementById("area-filter-all");
    const areaFilterClear = document.getElementById("area-filter-clear");
    const alertOnlyToggle = document.getElementById("alert-only-toggle");
    const areaSections = document.getElementById("area-sections");
    const dataset = await loadLightingDataset();
    const summary = utils.summarizePortfolio(dataset);

    populateSummary(summary);
    populateAreaFilter(summary);
    renderNotionalEnergyModule(summary);

    requestAnimationFrame(() => {
        renderCharts(summary);
        setTimeout(() => renderAreaSections(summary), 0);
    });

    searchInput?.addEventListener("input", (event) => {
        state.search = event.target.value.trim().toLowerCase();
        renderAreaSections(summary);
    });

    statusFilter?.addEventListener("change", (event) => {
        state.status = event.target.value;
        renderAreaSections(summary);
    });

    areaFilterAll?.addEventListener("click", () => {
        state.selectedAreas.clear();
        syncAreaFilterButtons();
        renderAreaSections(summary);
    });

    areaFilterClear?.addEventListener("click", () => {
        state.selectedAreas.clear();
        syncAreaFilterButtons();
        renderAreaSections(summary);
    });

    alertOnlyToggle?.addEventListener("click", () => {
        state.alertOnly = !state.alertOnly;
        alertOnlyToggle.classList.toggle("active", state.alertOnly);
        alertOnlyToggle.setAttribute("aria-pressed", String(state.alertOnly));
        alertOnlyToggle.textContent = state.alertOnly ? "Showing Alerted Fixtures Only" : "Show Alerted Fixtures Only";
        renderAreaSections(summary);
    });

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
                renderAreaSections(summary);
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
        const circuitBreakdown = document.getElementById("lighting-circuit-breakdown");

        if (energyBreakdown) {
            energyBreakdown.innerHTML = currentSummary.areas
                .slice(0, 10)
                .map((area) => `
                    <div class="lighting-breakdown-item">
                        <span class="lighting-breakdown-room">${escapeHTML(area.areaName)}</span>
                        <span class="lighting-breakdown-kwh">${formatNumber(area.totalNotionalEnergy, 1)} kWh</span>
                    </div>
                `)
                .join("");
        }

        if (circuitBreakdown) {
            circuitBreakdown.innerHTML = currentSummary.circuits
                .slice(0, 10)
                .map((circuit) => `
                    <div class="lighting-breakdown-item">
                        <span class="lighting-breakdown-room">${escapeHTML(circuit.circuitName)}</span>
                        <span class="lighting-breakdown-kwh">${formatNumber(circuit.totalNotionalEnergy, 1)} kWh</span>
                    </div>
                `)
                .join("");
        }

        createChart("lighting-area-energy-chart", {
            type: "bar",
            data: {
                labels: currentSummary.areas.slice(0, 8).map((area) => area.areaName),
                datasets: [{
                    label: "Lighting Energy (kWh)",
                    data: currentSummary.areas.slice(0, 8).map((area) => area.totalNotionalEnergy),
                    backgroundColor: "#2563eb",
                    borderRadius: 10
                }]
            },
            options: chartOptions({ horizontal: true })
        });
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
        const statusMatch = state.status === "all" || fixture.status.toLowerCase() === state.status;
        const areaMatch = state.selectedAreas.size === 0 || state.selectedAreas.has(fixture["Area Name"]);
        const alertMatch = !state.alertOnly || fixture.alerts.length > 0;
        const searchMatch = !state.search || [
            fixture["Fixture Name"],
            fixture["Area Name"],
            fixture["Circuit Name"]
        ].some((value) => String(value).toLowerCase().includes(state.search));

        return statusMatch && areaMatch && alertMatch && searchMatch;
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

    function renderCharts(currentSummary) {
        createChart("area-health-chart", {
            type: "bar",
            data: {
                labels: currentSummary.charts.areaHealth.labels,
                datasets: [{
                    label: "Average Fixture Health (%)",
                    data: currentSummary.charts.areaHealth.values,
                    backgroundColor: "#0891b2",
                    borderRadius: 10
                }]
            },
            options: chartOptions({ horizontal: true, suggestedMax: 100 })
        });

        createChart("lowest-health-chart", {
            type: "bar",
            data: {
                labels: currentSummary.charts.lowestHealthFixtures.labels,
                datasets: [{
                    label: "Fixture Health (%)",
                    data: currentSummary.charts.lowestHealthFixtures.values,
                    backgroundColor: "#ef4444",
                    borderRadius: 10
                }]
            },
            options: chartOptions({ horizontal: true, suggestedMax: 100 })
        });
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
            const response = await fetch("/api/lighting");
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
