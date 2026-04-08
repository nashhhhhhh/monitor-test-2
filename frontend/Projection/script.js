document.addEventListener("DOMContentLoaded", () => {
    const charts = {};

    function setText(id, value) {
        const node = document.getElementById(id);
        if (node) node.textContent = value;
    }

    function formatNumber(value, digits = 1) {
        return Number(value).toLocaleString(undefined, {
            minimumFractionDigits: digits,
            maximumFractionDigits: digits
        });
    }

    function formatMetricValue(value, unit, emptyState = "Unavailable") {
        if (value == null || Number.isNaN(Number(value))) return emptyState;
        const digits = Math.abs(Number(value)) >= 100 ? 0 : 2;
        return `${formatNumber(Number(value), digits)}${unit ? ` ${unit}` : ""}`;
    }

    function renderChart(id, config) {
        const canvas = document.getElementById(id);
        if (!canvas) return;
        if (charts[id]) charts[id].destroy();

        charts[id] = new Chart(canvas, {
            ...config,
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
                scales: config.type === "doughnut"
                    ? {}
                    : {
                        x: { grid: { display: false } },
                        y: { beginAtZero: true }
                    },
                ...config.options
            }
        });
    }

    function renderMetricCards(containerId, cards) {
        const container = document.getElementById(containerId);
        if (!container) return;

        if (!Array.isArray(cards) || cards.length === 0) {
            container.innerHTML = '<div class="empty-state">No projection data available.</div>';
            return;
        }

        container.innerHTML = cards.map((card) => {
            const hasValue = card.value != null && !Number.isNaN(Number(card.value));
            return `
                <article class="metric-card ${card.status || "normal"}">
                    <span class="metric-label">${card.title}</span>
                    <strong class="metric-value">${hasValue ? formatMetricValue(card.value, card.unit, card.empty_state) : card.empty_state}</strong>
                    <span class="metric-subtext">${card.subtitle || ""}</span>
                </article>
            `;
        }).join("");
    }

    function renderFreezerUnits(units) {
        const container = document.getElementById("freezer-forecast-grid");
        if (!container) return;

        if (!Array.isArray(units) || units.length === 0) {
            container.innerHTML = '<div class="empty-state">No spiral freezer projection data available.</div>';
            return;
        }

        container.innerHTML = units.map((unit) => `
            <article class="freezer-card ${unit.status || "normal"}">
                <div class="freezer-card-header">
                    <div>
                        <h3>${unit.name}</h3>
                        <p>${unit.subtitle || "Unavailable"}</p>
                    </div>
                    <span class="status-pill ${unit.status || "normal"}">${unit.status === "warning" ? "Watch" : unit.status === "unavailable" ? "Unavailable" : "Stable"}</span>
                </div>
                <div class="freezer-metrics">
                    <div class="freezer-metric">
                        <span>Top Temp (1h)</span>
                        <strong>${formatMetricValue(unit.top_temp_projected, "deg C", "No trend data")}</strong>
                    </div>
                    <div class="freezer-metric">
                        <span>Bottom Temp (1h)</span>
                        <strong>${formatMetricValue(unit.bottom_temp_projected, "deg C", "No trend data")}</strong>
                    </div>
                    <div class="freezer-metric">
                        <span>Pressure (1h)</span>
                        <strong>${formatMetricValue(unit.pressure_projected, "kg/cm2", "No trend data")}</strong>
                    </div>
                    <div class="freezer-metric">
                        <span>Projected Runtime</span>
                        <strong>${formatMetricValue(unit.runtime_projected, "hrs", "Unavailable")}</strong>
                    </div>
                    <div class="freezer-metric full">
                        <span>Threshold Risk</span>
                        <strong>${unit.threshold_hours != null ? `${formatNumber(unit.threshold_hours, 1)} hr to -18 deg C limit` : "No active breach risk"}</strong>
                    </div>
                </div>
            </article>
        `).join("");
    }

    function renderRiskList(items, generatorNote) {
        const container = document.getElementById("risk-forecast-list");
        if (!container) return;

        const blocks = [];
        if (generatorNote) {
            blocks.push(`
                <article class="risk-card info">
                    <div class="risk-topline">
                        <span class="risk-system">Generator</span>
                        <span class="risk-severity info">Info</span>
                    </div>
                    <h3>Generator projection note</h3>
                    <p>${generatorNote}</p>
                </article>
            `);
        }

        if (Array.isArray(items)) {
            items.forEach((item) => {
                blocks.push(`
                    <article class="risk-card ${item.severity || "warning"}">
                        <div class="risk-topline">
                            <span class="risk-system">${item.system || "Projection"}</span>
                            <span class="risk-severity ${item.severity || "warning"}">${item.severity || "warning"}</span>
                        </div>
                        <h3>${item.title || "Forecast risk"}</h3>
                        <p>${item.message || "No details available."}</p>
                    </article>
                `);
            });
        }

        if (!blocks.length) {
            container.innerHTML = '<div class="empty-state">No forecast risks identified from the current imported data.</div>';
            return;
        }

        container.innerHTML = blocks.join("");
    }

    function renderSupportingMetrics(supportingMetrics = {}) {
        const directShare = supportingMetrics.boiler_direct_share;
        const indirectShare = supportingMetrics.boiler_indirect_share;
        setText("boiler-direct-share", directShare != null ? `${formatNumber(directShare * 100, 1)}%` : "Unavailable");
        setText("boiler-indirect-share", indirectShare != null ? `${formatNumber(indirectShare * 100, 1)}%` : "Unavailable");
        setText("lighting-warning-count", supportingMetrics.lighting_warning_count ?? "Unavailable");
        setText("lighting-critical-count", supportingMetrics.lighting_critical_count ?? "Unavailable");
    }

    function updateTopKpis(topKpis = {}) {
        setText("kpi-energy-total", formatMetricValue(topKpis.projected_energy_total, "kWh"));
        setText("kpi-water-total", formatMetricValue(topKpis.projected_water_total, "m3"));
        setText("kpi-coverage", `${topKpis.systems_covered ?? 0} / ${topKpis.systems_total ?? 0}`);
        setText("kpi-risk-count", topKpis.risk_count ?? 0);
        setText(
            "kpi-risk-text",
            (topKpis.risk_count || 0) > 0
                ? `${topKpis.risk_count} forecast item(s) need review`
                : "No active forecast risks"
        );
    }

    function renderEnergyComparison(chartData = {}) {
        renderChart("energyComparisonChart", {
            type: "bar",
            data: {
                labels: chartData.labels || [],
                datasets: [
                    {
                        label: "Actual",
                        data: chartData.actual || [],
                        backgroundColor: "#93c5fd",
                        borderRadius: 8
                    },
                    {
                        label: "Projected",
                        data: chartData.projected || [],
                        backgroundColor: "#2563eb",
                        borderRadius: 8
                    }
                ]
            }
        });
    }

    function renderWtpContribution(chartData = {}) {
        renderChart("wtpContributionChart", {
            type: "doughnut",
            data: {
                labels: chartData.labels || [],
                datasets: [{
                    data: chartData.values || [],
                    backgroundColor: ["#2563eb", "#0ea5e9", "#10b981"],
                    borderWidth: 0
                }]
            },
            options: {
                cutout: "62%"
            }
        });
    }

    function renderWwtpFlow(chartData = {}) {
        renderChart("wwtpFlowChart", {
            type: "bar",
            data: {
                labels: chartData.labels || [],
                datasets: [
                    {
                        label: "Actual",
                        data: chartData.actual || [],
                        backgroundColor: "#93c5fd",
                        borderRadius: 8
                    },
                    {
                        label: "Projected",
                        data: chartData.projected || [],
                        backgroundColor: "#0ea5e9",
                        borderRadius: 8
                    }
                ]
            }
        });
    }

    async function loadProjectionPage() {
        try {
            const response = await fetch("/api/projection", { cache: "no-store" });
            if (!response.ok) throw new Error(`Projection API error: ${response.status}`);

            const payload = await response.json();
            updateTopKpis(payload.top_kpis);
            setText("generator-note", payload.meta?.generator_note || payload.risk_alert_forecast?.generator_note || "Unavailable");

            renderMetricCards("energy-forecast-cards", payload.energy_forecast?.cards);
            renderMetricCards("water-forecast-cards", payload.water_flow_forecast?.cards);
            renderMetricCards("thermal-forecast-cards", payload.thermal_process_forecast?.cards);
            renderMetricCards("ratio-forecast-cards", payload.ratio_efficiency_forecast?.cards);

            renderEnergyComparison(payload.energy_forecast?.comparison_chart);
            renderWtpContribution(payload.water_flow_forecast?.contribution_chart);
            renderWwtpFlow(payload.water_flow_forecast?.wastewater_chart);
            renderFreezerUnits(payload.thermal_process_forecast?.freezer_units);
            renderSupportingMetrics(payload.ratio_efficiency_forecast?.supporting_metrics);
            renderRiskList(payload.risk_alert_forecast?.items, payload.risk_alert_forecast?.generator_note);
        } catch (error) {
            console.error("Projection page load failed:", error);
            setText("generator-note", "Unable to load projection data.");
            [
                "energy-forecast-cards",
                "water-forecast-cards",
                "thermal-forecast-cards",
                "ratio-forecast-cards",
                "freezer-forecast-grid",
                "risk-forecast-list"
            ].forEach((id) => {
                const node = document.getElementById(id);
                if (node) node.innerHTML = '<div class="empty-state">Projection data is currently unavailable.</div>';
            });
        }
    }

    loadProjectionPage();
    window.setInterval(loadProjectionPage, 5 * 60 * 1000);
});
