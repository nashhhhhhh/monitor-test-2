document.addEventListener("DOMContentLoaded", () => {
    const pageKey = document.body.dataset.projectionPage || "overview";
    const route = pageKey === "overview" ? "/api/projection" : `/api/projection/${pageKey}`;
    const charts = {};

    function getPeriodLabel(value) {
        if (value === "next_week") return "Next Week";
        if (value === "quarter") return "Quarter";
        return "Next Month";
    }

    function setText(id, value) {
        const node = document.getElementById(id);
        if (node) node.textContent = value;
    }

    function destroyCharts() {
        Object.values(charts).forEach((chart) => chart?.destroy?.());
        Object.keys(charts).forEach((key) => delete charts[key]);
    }

    function renderKpis(items = []) {
        const target = document.getElementById("projection-kpis");
        if (!target) return;
        const filteredItems = pageKey === "overview"
            ? items.filter((item) => !["Reactive Maintenance Forecast", "Critical Equipment Tasks Due"].includes(item.label))
            : items;

        if (!filteredItems.length) {
            target.innerHTML = '<div class="empty-state projection-empty-block">No projection KPI data available.</div>';
            return;
        }

        target.innerHTML = filteredItems.map((item) => `
            <article class="kpi-card ${item.tone ? `highlight-${item.tone}` : ""}">
                <span class="kpi-label">${item.label}</span>
                <strong class="kpi-value">${item.value}</strong>
                <span class="kpi-subtext">${item.subtext || ""}</span>
            </article>
        `).join("");
    }

    function createChartCard(index, chart) {
        const compactClass = chart.compact ? "compact" : "";
        return `
            <article class="chart-card">
                <div class="chart-header">
                    <h3>${chart.title}</h3>
                    <p>${chart.subtitle || ""}</p>
                </div>
                <div class="chart-wrap ${compactClass}">
                    <canvas id="projection-chart-${index}"></canvas>
                </div>
            </article>
        `;
    }

    function renderCharts(items = []) {
        const target = document.getElementById("projection-charts");
        if (!target) return;

        destroyCharts();

        if (!items.length) {
            target.innerHTML = '<div class="empty-state projection-empty-block">No projection charts available.</div>';
            return;
        }

        target.innerHTML = items.map((chart, index) => createChartCard(index, chart)).join("");

        items.forEach((chart, index) => {
            const canvas = document.getElementById(`projection-chart-${index}`);
            if (!canvas) return;

            charts[index] = new Chart(canvas, {
                type: chart.type || "bar",
                data: {
                    labels: chart.labels || [],
                    datasets: (chart.datasets || []).map((dataset) => ({
                        borderRadius: chart.type === "bar" ? 8 : 0,
                        tension: chart.type === "line" ? 0.35 : 0,
                        pointRadius: chart.type === "line" ? 3 : 0,
                        borderWidth: chart.type === "line" ? 3 : 0,
                        fill: chart.type === "line" ? Boolean(dataset.fill) : false,
                        ...dataset,
                    })),
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            position: "bottom",
                            labels: {
                                boxWidth: 12,
                                font: { family: "Inter", size: 11 },
                            },
                        },
                    },
                    scales: chart.type === "doughnut"
                        ? {}
                        : {
                            x: { grid: { display: false } },
                            y: { beginAtZero: true },
                        },
                },
            });
        });
    }

    function renderBreakdowns(items = []) {
        const target = document.getElementById("projection-breakdowns");
        if (!target) return;

        const filteredItems = (items || []).filter(
            (section) => section?.title !== "Critical Equipment Upcoming Load"
        );

        if (!filteredItems.length) {
            target.className = "breakdown-grid";
            target.innerHTML = '<div class="empty-state projection-empty-block">No projection breakdowns available.</div>';
            return;
        }

        target.className = "breakdown-grid";
        target.innerHTML = filteredItems.map((section) => `
            <article class="support-card">
                <h3>${section.title}</h3>
                <div class="insight-list">
                    ${(section.rows || []).map((row) => `
                        <div class="insight-row">
                            <div>
                                <span>${row.label}</span>
                                <div class="projection-row-subtext">${row.subtext || ""}</div>
                            </div>
                            <strong>${row.value}</strong>
                        </div>
                    `).join("")}
                </div>
            </article>
        `).join("");
    }

    function deferProjectionSection(callback) {
        window.requestAnimationFrame(() => window.setTimeout(callback, 0));
    }

    async function loadPage() {
        try {
            const period = document.getElementById("projection-period")?.value || "next_month";
            const periodLabel = getPeriodLabel(period);
            setText("projection-window-label", `Loading ${periodLabel} projection...`);
            setText("projection-window-subtext", "Refreshing KPI cards, charts, and breakdowns for the selected period.");

            const response = await fetch(`${route}?period=${encodeURIComponent(period)}&_=${Date.now()}`, { cache: "no-store" });
            if (!response.ok) throw new Error(`Projection API error: ${response.status}`);

            const payload = await response.json();
            setText("projection-page-title", payload.meta?.title || "Projection");
            setText("projection-page-subtitle", payload.meta?.subtitle || "");
            setText("projection-window-label", `${payload.meta?.period_label || "Next Month"} | ${payload.meta?.window_label || ""}`);
            setText("projection-window-subtext", "Projection updates dynamically from the current imported dashboard records.");
            renderKpis(payload.kpis || []);
            if (pageKey === "overview") {
                renderBreakdowns([]);
                deferProjectionSection(() => renderCharts(payload.charts || []));
                deferProjectionSection(() => renderBreakdowns(payload.breakdowns || []));
            } else {
                renderCharts(payload.charts || []);
                renderBreakdowns(payload.breakdowns || []);
            }
        } catch (error) {
            console.error("Projection page load failed:", error);
            setText("projection-window-label", "Unavailable");
            setText("projection-window-subtext", "Projection data could not be loaded from the current dashboard sources.");
            renderKpis([]);
            renderCharts([]);
            renderBreakdowns([]);
        }
    }

    document.getElementById("projection-period")?.addEventListener("change", loadPage);
    loadPage();
});
