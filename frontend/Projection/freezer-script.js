/**
 * freezer-script.js - Spiral Blast Freezer Projection
 * Cleaner operating view focused on recent top/bottom temperatures and runtime.
 * Depends on prediction-core.js
 */

const TEMP_THRESHOLD = -18;
const TEMP_CRITICAL = -10;
const RECENT_POINT_COUNT = 60;

const UNIT_COLORS = {
    "01": "#06b6d4",
    "02": "#8b5cf6",
    "03": "#f97316",
};

function makeFreezerMock(baseTemp, noise = 1.5) {
    return {
        rows: Array.from({ length: RECENT_POINT_COUNT }, (_, index) => ({
            time: `00:${String(index).padStart(2, "0")}:00`,
            tef01: baseTemp + Math.sin(index / 6) * noise + (Math.random() - 0.5) * noise,
            tef02: (baseTemp - 1.3) + Math.sin(index / 6) * noise + (Math.random() - 0.5) * noise,
            pt01: 2.1 + Math.sin(index / 10) * 0.15,
            runtime: 18.5 + (index / 60),
        })),
    };
}

const MOCK_UNITS = {
    "01": makeFreezerMock(-32),
    "02": makeFreezerMock(-28),
    "03": makeFreezerMock(-15),
};

function normalizeRows(rows) {
    if (!Array.isArray(rows) || rows.length === 0) return null;
    return rows
        .map((row) => ({
            time: String(row.time || "").trim(),
            tef01: Number(row.tef01),
            tef02: Number(row.tef02),
            pt01: Number(row.pt01),
            runtime: Number(row.runtime),
        }))
        .filter((row) => Number.isFinite(row.tef01) && Number.isFinite(row.tef02))
        .slice(-RECENT_POINT_COUNT);
}

function temperatureStatus(topTemp, bottomTemp, runtime) {
    const warmest = Math.max(topTemp, bottomTemp);

    if (!Number.isFinite(runtime) || runtime <= 0) {
        return { cls: "stopped", label: "STOPPED", tempCls: "temp-stopped" };
    }
    if (warmest > TEMP_CRITICAL) {
        return { cls: "danger", label: "CRITICAL", tempCls: "temp-critical" };
    }
    if (warmest > TEMP_THRESHOLD) {
        return { cls: "warn", label: "WARNING", tempCls: "temp-warning" };
    }
    return { cls: "ok", label: "NORMAL", tempCls: "temp-ok" };
}

function formatTrendLabel(series) {
    const trend = trendDirection(series, false);
    if (trend.label === "Improving") return { text: "Cooling", color: "#10b981" };
    if (trend.label === "Rising") return { text: "Warming", color: "#f59e0b" };
    if (trend.label === "Declining") return { text: "Warming", color: "#ef4444" };
    return { text: "Stable", color: "#64748b" };
}

function projectRuntimeToday(rows) {
    if (!rows.length) return null;
    const latest = rows[rows.length - 1];
    if (!Number.isFinite(latest.runtime)) return null;

    const startTime = rows[0].time;
    const endTime = latest.time;
    const startDate = new Date(`1970-01-01T${startTime}`);
    const endDate = new Date(`1970-01-01T${endTime}`);
    if (Number.isNaN(startDate.getTime()) || Number.isNaN(endDate.getTime())) {
        return latest.runtime;
    }

    const elapsedHours = Math.max((endDate - startDate) / 3600000, 0.25);
    return (latest.runtime / elapsedHours) * 24;
}

function renderUnitSparkline(id, rows) {
    const canvas = document.getElementById(`chart-unit-${id}`);
    if (!canvas) return;

    const existing = Chart.getChart(canvas);
    if (existing) existing.destroy();

    new Chart(canvas.getContext("2d"), {
        type: "line",
        data: {
            labels: rows.map((row) => row.time.slice(0, 5)),
            datasets: [
                {
                    data: rows.map((row) => row.tef01),
                    borderColor: UNIT_COLORS[id],
                    borderWidth: 2,
                    pointRadius: 0,
                    tension: 0.35,
                    fill: false,
                }
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false }, tooltip: { enabled: false } },
            scales: { x: { display: false }, y: { display: false } },
        },
    });
}

function renderUnitCard(id, rows) {
    const latest = rows[rows.length - 1];
    const status = temperatureStatus(latest.tef01, latest.tef02, latest.runtime);

    const pill = document.getElementById(`unit-status-${id}`);
    if (pill) {
        pill.textContent = status.label;
        pill.className = `sys-status-pill ${status.cls}`;
    }

    const card = document.getElementById(`unit-card-${id}`);
    if (card) {
        card.className = `freezer-unit-card border-${status.cls}`;
    }

    const topNode = document.getElementById(`unit-tef01-${id}`);
    const bottomNode = document.getElementById(`unit-tef02-${id}`);
    if (topNode) {
        topNode.textContent = `${latest.tef01.toFixed(1)} deg C`;
        topNode.className = `unit-temp-value ${status.tempCls}`;
    }
    if (bottomNode) {
        bottomNode.textContent = `${latest.tef02.toFixed(1)} deg C`;
        bottomNode.className = `unit-temp-value ${status.tempCls}`;
    }

    setText(`unit-pt01-${id}`, Number.isFinite(latest.pt01) ? `${latest.pt01.toFixed(2)} kg/cm2` : "Unavailable");
    setText(`unit-runtime-${id}`, Number.isFinite(latest.runtime) ? `${latest.runtime.toFixed(1)} hrs` : "Unavailable");

    const projectedRuntime = projectRuntimeToday(rows);
    setText(`unit-proj-runtime-${id}`, projectedRuntime != null ? `${projectedRuntime.toFixed(1)} hrs` : "Unavailable");

    const trendLabel = formatTrendLabel(rows.map((row) => row.tef01));
    const trendNode = document.getElementById(`unit-temp-trend-${id}`);
    if (trendNode) {
        trendNode.textContent = trendLabel.text;
        trendNode.style.color = trendLabel.color;
    }

    renderUnitSparkline(id, rows);

    return {
        id,
        latest,
        projectedRuntime,
        status,
        rows,
    };
}

function renderCombinedChart(unitResults) {
    const canvas = document.getElementById("combinedTempChart");
    if (!canvas) return;

    const existing = Chart.getChart(canvas);
    if (existing) existing.destroy();

    const referenceRows = unitResults[0]?.rows || [];
    const labels = referenceRows.map((row) => row.time.slice(0, 5));
    const datasets = unitResults.map((result) => ({
        label: `Spiral ${result.id}`,
        data: result.rows.map((row) => row.tef01),
        borderColor: UNIT_COLORS[result.id],
        backgroundColor: `${UNIT_COLORS[result.id]}20`,
        borderWidth: 2.5,
        pointRadius: 0,
        tension: 0.3,
        fill: false,
    }));

    datasets.push({
        label: "Limit",
        data: Array(labels.length).fill(TEMP_THRESHOLD),
        borderColor: "#ef4444",
        borderDash: [6, 4],
        borderWidth: 1.5,
        pointRadius: 0,
        fill: false,
    });

    new Chart(canvas.getContext("2d"), {
        type: "line",
        data: { labels, datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: "index", intersect: false },
            plugins: {
                legend: {
                    position: "top",
                    labels: { usePointStyle: true, font: { size: 11 } }
                },
                tooltip: {
                    callbacks: {
                        label(context) {
                            return `${context.dataset.label}: ${context.parsed.y.toFixed(1)} deg C`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: { display: false },
                    ticks: {
                        autoSkip: true,
                        maxTicksLimit: 10,
                        font: { size: 10 }
                    }
                },
                y: {
                    grid: { color: "#f1f5f9" },
                    ticks: { font: { size: 11 } },
                    title: { display: true, text: "deg C" }
                }
            }
        }
    });
}

function renderAlerts(unitResults) {
    const alerts = [];
    unitResults.forEach((result) => {
        const warmest = Math.max(result.latest.tef01, result.latest.tef02);
        if (result.status.cls === "danger") {
            alerts.push({
                critical: true,
                msg: `Spiral ${result.id} is above the safe freezer range at ${warmest.toFixed(1)} deg C.`
            });
        } else if (result.status.cls === "warn") {
            alerts.push({
                critical: false,
                msg: `Spiral ${result.id} is above the -18 deg C operating limit at ${warmest.toFixed(1)} deg C.`
            });
        }
    });

    const banner = document.getElementById("alert-banner");
    const list = document.getElementById("alert-list");
    if (!alerts.length) {
        banner.classList.add("hidden");
        return;
    }

    banner.classList.remove("hidden");
    list.innerHTML = alerts
        .map((alert) => `<div class="alert-item ${alert.critical ? "critical" : ""}">${alert.msg}</div>`)
        .join("");
}

async function init() {
    let apiData = null;
    try {
        const response = await fetch("/api/spiral_blast_freezer", { cache: "no-store" });
        const text = await response.text();
        apiData = JSON.parse(
            text
                .replace(/\bNaN\b/g, "null")
                .replace(/\bInfinity\b/g, "null")
                .replace(/\b-Infinity\b/g, "null")
        );
    } catch {
        apiData = null;
    }

    const unitIds = ["01", "02", "03"];
    const spiralKeys = ["spiral_01", "spiral_02", "spiral_03"];
    const unitResults = unitIds.map((id, index) => {
        const normalized = normalizeRows(apiData?.status_data?.[spiralKeys[index]]?.data);
        const rows = normalized && normalized.length ? normalized : MOCK_UNITS[id].rows;
        return renderUnitCard(id, rows);
    });

    const runningUnits = unitResults.filter((result) => result.status.cls !== "stopped").length;
    const warmestTop = Math.max(...unitResults.map((result) => result.latest.tef01));
    const coldestTop = Math.min(...unitResults.map((result) => result.latest.tef01));
    const nearLimitCount = unitResults.filter((result) => result.status.cls === "warn" || result.status.cls === "danger").length;
    const totalProjectedRuntime = unitResults.reduce((sum, result) => sum + (result.projectedRuntime || 0), 0);

    setText("kpi-active", `${runningUnits} / 3`);
    setText("kpi-coldest", `${coldestTop.toFixed(1)} deg C`);
    setText("kpi-warmest", `${warmestTop.toFixed(1)} deg C`);
    setText("kpi-runtime-24h", `${totalProjectedRuntime.toFixed(1)} hrs`);
    setText("kpi-near-limit", String(nearLimitCount));

    const warmCard = document.getElementById("kpi-warm-card");
    warmCard.className = `kpi-card ${warmestTop > TEMP_THRESHOLD ? "highlight-red" : "highlight-green"}`;

    renderAlerts(unitResults);
    renderCombinedChart(unitResults);
}

document.addEventListener("DOMContentLoaded", init);
setInterval(init, 5 * 60 * 1000);
