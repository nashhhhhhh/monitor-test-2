let downtimePayload = null;
let downtimeCachePayload = null;
const chartRefs = {};

const CRITICALITY_ORDER = ["Critical", "Semi-Critical", "Support Systems", "Facility / Non-Critical"];
const CRITICALITY_COLORS = {
    "Critical": "#ef4444",
    "Semi-Critical": "#f59e0b",
    "Support Systems": "#0f766e",
    "Facility / Non-Critical": "#64748b",
};

function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}

function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (match) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        "\"": "&quot;",
        "'": "&#39;",
    }[match]));
}

function fmtHours(hours) {
    if (hours === null || hours === undefined || Number.isNaN(Number(hours))) return "--";
    const numeric = Number(hours);
    if (numeric <= 0) return "0 min";
    if (numeric < 1) return `${Math.round(numeric * 60)} min`;
    const wholeHours = Math.floor(numeric);
    const minutes = Math.round((numeric - wholeHours) * 60);
    if (minutes === 60) return `${wholeHours + 1} hr`;
    if (minutes > 0) return `${wholeHours} hr ${minutes} min`;
    return `${wholeHours} hr`;
}

function fmtAxisHours(hours) {
    if (hours === null || hours === undefined || Number.isNaN(Number(hours))) return "--";
    return `${Number(hours).toLocaleString(undefined, { maximumFractionDigits: 1 })} hrs`;
}

function fmtDaysHours(hours) {
    if (hours === null || hours === undefined || Number.isNaN(Number(hours))) return "--";
    const numeric = Number(hours);
    if (numeric <= 0) return "0 hr";
    if (numeric < 24) return fmtHours(numeric);
    const days = numeric / 24;
    if (days >= 10) return `${days.toLocaleString(undefined, { maximumFractionDigits: 0 })} days`;
    return `${days.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 })} days`;
}

function fmtMtbfDays(hours) {
    if (hours === null || hours === undefined || Number.isNaN(Number(hours))) return "";
    return fmtDaysHours(hours);
}

function fmtNumber(value) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
    return Number(value).toLocaleString();
}

function fmtDateTime(value) {
    if (!value) return "--";
    const dt = new Date(value);
    if (Number.isNaN(dt.getTime())) return "--";
    return dt.toLocaleString("en-GB", {
        day: "2-digit",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
    });
}

function fmtDateOnly(value) {
    if (!value) return "";
    const dt = new Date(value);
    if (Number.isNaN(dt.getTime())) return "";
    return dt.toLocaleDateString("en-GB", {
        day: "2-digit",
        month: "short",
        year: "numeric",
    });
}

function getIsoDate(value) {
    if (!value) return "";
    const dt = new Date(value);
    if (Number.isNaN(dt.getTime())) return "";
    return dt.toISOString().slice(0, 10);
}

function buildStatusPill(status, label) {
    const normalized = String(status || "ok").toLowerCase();
    return `<span class="status-pill ${escapeHtml(normalized)}">${escapeHtml(label || normalized)}</span>`;
}

function populateSelect(id, values, defaultLabel) {
    const select = document.getElementById(id);
    if (!select) return;
    const current = select.value;
    select.innerHTML = `<option value="">${escapeHtml(defaultLabel)}</option>` + values.map((value) => (
        `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`
    )).join("");
    if (values.includes(current)) {
        select.value = current;
    }
}

function destroyChart(id) {
    if (chartRefs[id]) {
        chartRefs[id].destroy();
        delete chartRefs[id];
    }
}

function renderEmptyChart(canvasId, message) {
    const canvas = document.getElementById(canvasId);
    const container = canvas?.parentElement || document.querySelector(`.chart-container[data-chart-id="${canvasId}"]`);
    if (!container) return;
    destroyChart(canvasId);
    container.innerHTML = `<div class="empty-state">${escapeHtml(message)}</div>`;
}

function ensureCanvas(canvasId) {
    const existing = document.getElementById(canvasId);
    if (existing) return existing;
    const target = document.querySelector(`.chart-container[data-chart-id="${canvasId}"]`);
    if (!target) return null;
    target.innerHTML = `<canvas id="${canvasId}"></canvas>`;
    return document.getElementById(canvasId);
}

async function loadDowntimeCacheFile() {
    try {
        const response = await fetch(`./downtime-cache.json?v=20260424-criticality&_=${Date.now()}`, {
            cache: "no-store",
        });
        if (!response.ok) {
            downtimeCachePayload = false;
            return null;
        }
        downtimeCachePayload = await response.json();
        return downtimeCachePayload;
    } catch (error) {
        console.warn("Downtime cache load failed:", error);
        downtimeCachePayload = false;
        return null;
    }
}

function getCachedDowntimePayload(period, month) {
    const payloads = downtimeCachePayload?.payloads || {};
    const key = period === "mtd" && month ? `mtd:${month}` : period;
    return payloads[key] || null;
}

async function loadDowntimeData(period, month) {
    if (downtimeCachePayload === null) {
        await loadDowntimeCacheFile();
    }

    let payload = getCachedDowntimePayload(period, month);
    if (!payload || !payload.management) {
        const url = month
            ? `/api/downtime?period=${encodeURIComponent(period)}&month=${encodeURIComponent(month)}&_=${Date.now()}`
            : `/api/downtime?period=${encodeURIComponent(period)}&_=${Date.now()}`;
        const response = await fetch(url, { cache: "no-store" });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        payload = await response.json();
    }

    downtimePayload = payload;
    populateMonthOptions(payload?.months || buildMonthOptions(payload?.meta?.reference_end), payload?.meta?.month || month || payload?.months?.[0]?.value || "");
    renderDowntimePage();
}

function getManagement() {
    return downtimePayload?.management || {
        summary: {},
        mtbf: {
            summary: {},
            criticality_rows: [],
            machine_group_rows: [],
            asset_rows: [],
            trend: { labels: [], mtbf_hours: [], pair_counts: [] },
        },
        criticality_rows: [],
        machine_group_rows: [],
        location_rows: [],
        trend: { labels: [], downtime_hours: [], work_order_counts: [] },
        work_orders: [],
        filters: { criticalities: [], machine_groups: [], locations: [], asset_ids: [], statuses: [] },
        alerts: [],
        mapping_meta: {},
    };
}

function getMtbfData() {
    return getManagement().mtbf || {
        summary: {},
        criticality_rows: [],
        machine_group_rows: [],
        asset_rows: [],
        trend: { labels: [], mtbf_hours: [], pair_counts: [] },
    };
}

function buildMonthOptions(referenceEnd) {
    const dt = referenceEnd ? new Date(referenceEnd) : new Date();
    if (Number.isNaN(dt.getTime())) return [];
    const options = [];
    for (let month = 1; month <= dt.getMonth() + 1; month += 1) {
        const value = `${dt.getFullYear()}-${String(month).padStart(2, "0")}`;
        const label = new Date(dt.getFullYear(), month - 1, 1).toLocaleDateString("en-GB", {
            month: "short",
            year: "numeric",
        });
        options.push({ value, label });
    }
    return options.reverse();
}

function populateMonthOptions(options, selectedValue) {
    const select = document.getElementById("month-select");
    if (!select) return;
    select.innerHTML = options.map((option) => (
        `<option value="${escapeHtml(option.value)}">${escapeHtml(option.label)}</option>`
    )).join("");
    select.value = selectedValue || options[0]?.value || "";
}

function toggleMonthFilter(period) {
    const wrap = document.getElementById("month-filter-wrap");
    if (!wrap) return;
    wrap.style.display = period === "mtd" ? "flex" : "none";
}

function renderAlerts(alerts) {
    const banner = document.getElementById("alert-banner");
    const items = document.getElementById("alert-items");
    if (!banner || !items) return;

    if (!alerts || !alerts.length) {
        banner.classList.add("hidden");
        items.innerHTML = "";
        return;
    }

    items.innerHTML = alerts.map((alert) => (
        `<div class="alert-item ${escapeHtml(alert.level || "warning")}">${escapeHtml(alert.message)}</div>`
    )).join("");
    banner.classList.remove("hidden");
}

function renderSummary(summary, downtimeSummary = {}) {
    const workOrderRecordCount = downtimeSummary.work_order_record_count ?? summary.total_work_orders;
    setText("kpi-total-downtime", fmtHours(summary.total_downtime_hours));
    setText("kpi-total-downtime-sub", `${fmtNumber(workOrderRecordCount)} work orders using imported TTR as downtime`);
    setText("kpi-total-work-orders", fmtNumber(workOrderRecordCount));
    setText("kpi-total-work-orders-sub", "Imported work order records in the selected period");
    setText("kpi-status-events", fmtNumber(downtimeSummary.energy_event_count));
    setText(
        "kpi-status-events-sub",
        downtimeSummary.energy_event_count !== null && downtimeSummary.energy_event_count !== undefined
            ? "Fault / down machine-status events in the selected period"
            : "No status-derived events"
    );
    setText("kpi-overall-mttr", fmtHours(summary.overall_mttr_hours));
    setText("kpi-overall-mttr-sub", "Average downtime per grouped work order");
    setText("kpi-highest-mttr-group", fmtHours(downtimeSummary.energy_hours));
    setText(
        "kpi-highest-mttr-group-sub",
        downtimeSummary.energy_hours !== null && downtimeSummary.energy_hours !== undefined
            ? "Fault / down machine-status hours in the selected period"
            : "No status-derived downtime data"
    );
}

function renderCriticalityCards(rows) {
    const container = document.getElementById("criticality-cards");
    if (!container) return;

    if (!rows || !rows.length) {
        container.innerHTML = `<div class="empty-state compact">No criticality data available</div>`;
        return;
    }

    container.innerHTML = rows.map((row) => {
        const color = CRITICALITY_COLORS[row.criticality] || "#64748b";
        return `
            <div class="criticality-card" style="border-top-color:${escapeHtml(color)};">
                <div class="criticality-header">
                    <span class="criticality-name">${escapeHtml(row.criticality)}</span>
                    <span class="criticality-share">${escapeHtml((row.share_of_total_pct || 0).toFixed(1))}% of total</span>
                </div>
                <div class="criticality-metric">${escapeHtml(fmtHours(row.average_mttr_hours))}</div>
                <div class="criticality-meta">${escapeHtml(fmtNumber(row.work_order_count))} work orders</div>
                <div class="criticality-meta criticality-meta-mttr"><strong>Total Downtime</strong><span>${escapeHtml(fmtHours(row.total_downtime_hours))}</span></div>
            </div>
        `;
    }).join("");
}

function renderMtbfSummary(summary) {
    setText("mtbf-overall-average", fmtMtbfDays(summary.overall_average_mtbf_hours));
    setText(
        "mtbf-overall-average-sub",
        summary.assets_with_valid_mtbf
            ? `${fmtNumber(summary.assets_with_valid_mtbf)} asset(s) with valid repeat failure gaps`
            : ""
    );

    const lowestAsset = summary.lowest_mtbf_asset_name || summary.lowest_mtbf_asset_id || "No data";
    setText("mtbf-lowest-asset", lowestAsset);
    setText(
        "mtbf-lowest-asset-sub",
        summary.lowest_mtbf_hours
            ? `${fmtDaysHours(summary.lowest_mtbf_hours)} average run time${summary.lowest_mtbf_asset_id ? ` | ${summary.lowest_mtbf_asset_id}` : ""}`
            : ""
    );

    setText("mtbf-repeated-assets", fmtNumber(summary.repeated_failure_assets || 0));
    setText(
        "mtbf-repeated-assets-sub",
        summary.repeated_failure_assets
            ? "Assets showing repeated repair cycles"
            : "No repeated failure pattern detected"
    );

    setText("mtbf-valid-assets", fmtNumber(summary.assets_with_valid_mtbf || 0));
    setText(
        "mtbf-valid-assets-sub",
        summary.assets_with_valid_mtbf
            ? "Assets with at least one valid failure gap"
            : ""
    );
}

function renderMtbfCriticalityCards(rows) {
    const container = document.getElementById("mtbf-criticality-cards");
    if (!container) return;

    const normalizedRows = CRITICALITY_ORDER.map((criticality) => (
        rows.find((row) => row.criticality === criticality) || {
            criticality,
            asset_count: 0,
            work_order_count: 0,
            average_mtbf_hours: null,
            valid_mtbf_asset_count: 0,
        }
    ));

    if (!normalizedRows.length) {
        container.innerHTML = `<div class="empty-state compact">No MTBF data available for the selected period</div>`;
        return;
    }

    container.innerHTML = normalizedRows.map((row) => {
        const color = CRITICALITY_COLORS[row.criticality] || "#64748b";
        return `
            <div class="criticality-card" style="border-top-color:${escapeHtml(color)};">
                <div class="criticality-header">
                    <span class="criticality-name">${escapeHtml(row.criticality)}</span>
                    <span class="criticality-share">${escapeHtml(fmtNumber(row.asset_count || 0))} assets</span>
                </div>
                <div class="criticality-metric">${escapeHtml(fmtMtbfDays(row.average_mtbf_hours))}</div>
                <div class="criticality-meta">${escapeHtml(fmtNumber(row.work_order_count || 0))} work orders</div>
            </div>
        `;
    }).join("");
}

function renderLowestMtbfList(rows) {
    const container = document.getElementById("mtbf-lowest-list");
    if (!container) return;

    if (!rows.length) {
        container.innerHTML = `<div class="empty-state">No MTBF data available</div>`;
        return;
    }

    destroyChart("mtbfLowestChart");

    container.innerHTML = rows.map((row) => `
        <div class="mtbf-mini-item">
            <div>
                <div class="mtbf-mini-name">${escapeHtml(row.asset_name || row.asset_display_name || row.asset_id || "--")}</div>
                <div class="mtbf-mini-sub">${escapeHtml(row.asset_id || "--")}${row.machine_group ? ` | ${escapeHtml(row.machine_group)}` : ""}</div>
            </div>
            <div class="mtbf-mini-value">${escapeHtml(fmtMtbfDays(row.average_mtbf_hours))}</div>
        </div>
    `).join("");
}

function renderBarChart(id, labels, data, color, axisTitle) {
    const canvas = ensureCanvas(id);
    if (!canvas) return;
    destroyChart(id);
    if (!labels.length) {
        renderEmptyChart(id, "No data available");
        return;
    }
    chartRefs[id] = new Chart(canvas.getContext("2d"), {
        type: "bar",
        data: {
            labels,
            datasets: [{
                data,
                backgroundColor: color,
                borderRadius: 8,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                y: {
                    beginAtZero: true,
                    grid: { color: "#e2e8f0" },
                    title: { display: true, text: axisTitle },
                    ticks: { callback: (value) => fmtAxisHours(value) },
                },
                x: {
                    grid: { display: false },
                    ticks: { font: { size: 11, weight: "600" } },
                },
            },
        },
    });
}

function renderHorizontalBarChart(id, labels, data, color, axisTitle) {
    const canvas = ensureCanvas(id);
    if (!canvas) return;
    destroyChart(id);
    if (!labels.length) {
        renderEmptyChart(id, "No data available");
        return;
    }
    chartRefs[id] = new Chart(canvas.getContext("2d"), {
        type: "bar",
        data: {
            labels,
            datasets: [{
                data,
                backgroundColor: color,
                borderRadius: 8,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            indexAxis: "y",
            plugins: { legend: { display: false } },
            scales: {
                x: {
                    beginAtZero: true,
                    grid: { color: "#e2e8f0" },
                    title: { display: true, text: axisTitle },
                    ticks: { callback: (value) => fmtAxisHours(value) },
                },
                y: {
                    grid: { display: false },
                    ticks: { font: { size: 11, weight: "600" } },
                },
            },
        },
    });
}

function renderTrendChart(trend) {
    const canvas = ensureCanvas("trendChart");
    if (!canvas) return;
    destroyChart("trendChart");
    if (!trend?.labels?.length) {
        renderEmptyChart("trendChart", "No dated work order history available");
        return;
    }
    chartRefs.trendChart = new Chart(canvas.getContext("2d"), {
        type: "line",
        data: {
            labels: trend.labels,
            datasets: [{
                label: "Downtime Hours",
                data: trend.downtime_hours,
                borderColor: "#ef4444",
                backgroundColor: "rgba(239, 68, 68, 0.14)",
                fill: true,
                tension: 0.28,
                borderWidth: 3,
                pointRadius: 3,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: (context) => `Downtime: ${fmtHours(context.raw)}`,
                        afterLabel: (context) => {
                            const count = trend.work_order_counts?.[context.dataIndex] || 0;
                            return `${fmtNumber(count)} work orders`;
                        },
                    },
                },
            },
            scales: {
                y: {
                    beginAtZero: true,
                    grid: { color: "#e2e8f0" },
                    ticks: { callback: (value) => fmtAxisHours(value) },
                },
                x: {
                    grid: { display: false },
                },
            },
        },
    });
}

function renderMtbfTrendChart(trend) {
    const canvas = ensureCanvas("mtbfTrendChart");
    if (!canvas) return;
    destroyChart("mtbfTrendChart");
    if (!trend?.labels?.length) {
        renderEmptyChart("mtbfTrendChart", "No repeat failure history available");
        return;
    }
    chartRefs.mtbfTrendChart = new Chart(canvas.getContext("2d"), {
        type: "line",
        data: {
            labels: trend.labels,
            datasets: [{
                label: "Average MTBF",
                data: trend.mtbf_hours,
                borderColor: "#0f766e",
                backgroundColor: "rgba(15, 118, 110, 0.12)",
                fill: true,
                tension: 0.28,
                borderWidth: 3,
                pointRadius: 3,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: (context) => `Average MTBF: ${fmtDaysHours(context.raw)}`,
                        afterLabel: (context) => {
                            const count = trend.pair_counts?.[context.dataIndex] || 0;
                            return `${fmtNumber(count)} failure gap pair(s)`;
                        },
                    },
                },
            },
            scales: {
                y: {
                    beginAtZero: true,
                    grid: { color: "#e2e8f0" },
                    ticks: { callback: (value) => fmtAxisHours(value) },
                },
                x: {
                    grid: { display: false },
                },
            },
        },
    });
}

function renderCharts(management) {
    const criticalityRows = (management.criticality_rows || []).filter((row) => Number(row.work_order_count || 0) > 0);
    renderBarChart(
        "criticalityChart",
        criticalityRows.map((row) => row.criticality),
        criticalityRows.map((row) => Number(row.total_downtime_hours || 0)),
        criticalityRows.map((row) => CRITICALITY_COLORS[row.criticality] || "#64748b"),
        "Downtime Hours"
    );

    const mttrRows = [...(management.machine_group_rows || [])]
        .filter((row) => Number(row.mttr_hours || 0) > 0)
        .sort((a, b) => Number(b.mttr_hours || 0) - Number(a.mttr_hours || 0))
        .slice(0, 12);
    renderHorizontalBarChart(
        "mttrChart",
        mttrRows.map((row) => row.machine_group),
        mttrRows.map((row) => Number(row.mttr_hours || 0)),
        "#8b5cf6",
        "MTTR (hrs)"
    );

    const locationRows = [...(management.location_rows || [])].slice(0, 12);
    renderHorizontalBarChart(
        "locationChart",
        locationRows.map((row) => row.location),
        locationRows.map((row) => Number(row.total_downtime_hours || 0)),
        "#0f766e",
        "Downtime Hours"
    );

    renderTrendChart(management.trend || {});

    const mtbf = management.mtbf || {};
    const lowestMtbfAssets = [...(mtbf.asset_rows || [])]
        .filter((row) => Number(row.average_mtbf_hours || 0) > 0)
        .sort((a, b) => Number(a.average_mtbf_hours || 0) - Number(b.average_mtbf_hours || 0))
        .slice(0, 10);
    renderLowestMtbfList(lowestMtbfAssets);

    const mtbfCriticalityLookup = new Map((mtbf.criticality_rows || []).map((row) => [row.criticality, row]));
    const mtbfCriticalityRows = CRITICALITY_ORDER.map((criticality) => (
        mtbfCriticalityLookup.get(criticality) || {
            criticality,
            average_mtbf_hours: 0,
            valid_mtbf_asset_count: 0,
        }
    ));
    renderBarChart(
        "mtbfCriticalityChart",
        mtbfCriticalityRows.map((row) => row.criticality),
        mtbfCriticalityRows.map((row) => Number(row.average_mtbf_hours || 0)),
        mtbfCriticalityRows.map((row) => CRITICALITY_COLORS[row.criticality] || "#64748b"),
        "MTBF (hrs)"
    );

    renderMtbfTrendChart(mtbf.trend || {});
}

function getFilteredMachineGroups() {
    const management = getManagement();
    const criticality = document.getElementById("group-criticality-filter")?.value || "";
    const location = document.getElementById("group-location-filter")?.value || "";
    const search = (document.getElementById("group-search")?.value || "").trim().toLowerCase();

    return (management.machine_group_rows || []).filter((row) => {
        if (row.mapping_source === "status_derived_downtime" || row.machine_group === "Utilities") return false;
        if (criticality && row.criticality !== criticality) return false;
        if (location && row.location !== location) return false;
        if (search) {
            const haystack = [
                row.machine_group,
                row.location,
                ...(row.asset_ids || []),
            ].join(" ").toLowerCase();
            if (!haystack.includes(search)) return false;
        }
        return true;
    });
}

function getMtbfMachineGroupLookup() {
    const rows = getMtbfData().machine_group_rows || [];
    const lookup = new Map();
    rows.forEach((row) => {
        const key = [
            row.machine_group || "",
            row.location || row.building || "",
            row.criticality || "",
        ].join("||");
        lookup.set(key, row);
    });
    return lookup;
}

function renderMachineGroupTable() {
    const tbody = document.getElementById("machine-group-tbody");
    if (!tbody) return;
    const rows = getFilteredMachineGroups();
    const mtbfLookup = getMtbfMachineGroupLookup();
    if (!rows.length) {
        tbody.innerHTML = `<tr><td colspan="10" class="empty-cell">No machine group rows match the selected filters.</td></tr>`;
        return;
    }

    tbody.innerHTML = rows.map((row) => `
        <tr class="${escapeHtml(row.status_flag || "ok")}-row">
            <td>${escapeHtml(row.criticality)}</td>
            <td>
                <div class="cell-title">${escapeHtml(row.machine_group)}</div>
            </td>
            <td class="asset-id-cell">
                ${row.asset_ttr_rows?.length ? row.asset_ttr_rows.map((assetRow) => `
                    <div class="asset-breakdown-item">
                        <div class="cell-title">${escapeHtml(assetRow.asset_display_name || assetRow.asset_id)}</div>
                        <div class="cell-sub">${escapeHtml(assetRow.asset_id)} | TTR ${escapeHtml(fmtHours(assetRow.total_ttr_hours))} | MTTR ${escapeHtml(fmtHours(assetRow.mttr_hours))}</div>
                    </div>
                `).join("") : escapeHtml((row.asset_ids || []).join(", ") || "--")}
            </td>
            <td>${escapeHtml(row.location || "--")}</td>
            <td>${escapeHtml(fmtNumber(row.work_order_count))}</td>
            <td>${escapeHtml(fmtHours(row.total_downtime_hours))}</td>
            <td>${escapeHtml(fmtHours(row.mttr_hours))}</td>
            <td>${escapeHtml((() => {
                const mtbfRow = mtbfLookup.get([
                    row.machine_group || "",
                    row.location || row.building || "",
                    row.criticality || "",
                ].join("||"));
                return mtbfRow?.average_mtbf_hours ? fmtDaysHours(mtbfRow.average_mtbf_hours) : "";
            })())}</td>
            <td>${escapeHtml(fmtDateTime(row.latest_work_order_time))}</td>
            <td>
                ${buildStatusPill(row.status_flag, row.status_flag || "ok")}
                <div class="cell-sub">${escapeHtml((row.alert_flags || []).join(" | ") || "No active flags")}</div>
            </td>
        </tr>
    `).join("");
}

function getUtilitiesRows() {
    return (downtimePayload?.events || [])
        .filter((row) => row?.source === "Status-derived")
        .sort((a, b) => String(b?.start_time || "").localeCompare(String(a?.start_time || "")));
}

function renderUtilitiesTable() {
    const tbody = document.getElementById("utilities-tbody");
    if (!tbody) return;
    const rows = getUtilitiesRows();
    if (!rows.length) {
        tbody.innerHTML = `<tr><td colspan="8" class="empty-cell">No status-derived downtime rows are available for the selected period.</td></tr>`;
        return;
    }
    tbody.innerHTML = rows.map((row) => `
        <tr>
            <td>${escapeHtml(row.system || "--")}</td>
            <td>${escapeHtml(row.machine_name || "--")}</td>
            <td>${escapeHtml(row.machine_code || "--")}</td>
            <td>${escapeHtml(row.area || row.location || "--")}</td>
            <td>${escapeHtml(fmtHours(row.duration_hours))}</td>
            <td>${escapeHtml(fmtDateTime(row.start_time))}</td>
            <td>${escapeHtml(fmtDateTime(row.end_time))}</td>
            <td>${escapeHtml(row.detection_type || row.source || "--")}</td>
        </tr>
    `).join("");
}

function populateFilters(management) {
    const rows = (management.machine_group_rows || []).filter((row) => row.mapping_source !== "status_derived_downtime" && row.machine_group !== "Utilities");
    populateSelect("group-criticality-filter", [...new Set(rows.map((row) => row.criticality).filter(Boolean))], "All Criticalities");
    populateSelect("group-location-filter", [...new Set(rows.map((row) => row.location).filter(Boolean))], "All Locations");
}

function renderDowntimePage() {
    const management = getManagement();
    const meta = downtimePayload?.meta || {};
    const downtimeSummary = downtimePayload?.summary || {};

    setText("last-synced", meta.last_synced ? `Last synced ${fmtDateTime(meta.last_synced)}` : "Last synced unavailable");
    renderAlerts(management.alerts || []);
    renderSummary(management.summary || {}, downtimeSummary);
    renderMtbfSummary(management.mtbf?.summary || {});
    renderCriticalityCards(management.criticality_rows || []);
    renderMtbfCriticalityCards(management.mtbf?.criticality_rows || []);
    renderCharts(management);
    populateFilters(management);
    renderMachineGroupTable();
    renderUtilitiesTable();
}

function handlePeriodChange() {
    const period = document.getElementById("period-select")?.value || "ytd";
    toggleMonthFilter(period);
    const month = period === "mtd" ? (document.getElementById("month-select")?.value || "") : "";
    loadDowntimeData(period, month).catch((error) => {
        console.error("Downtime period change failed:", error);
    });
}

function setSummaryView(view) {
    document.querySelectorAll("[data-summary-view]").forEach((button) => {
        button.classList.toggle("active", button.dataset.summaryView === view);
    });
    document.getElementById("criticality-summary-panel")?.classList.toggle("active", view === "criticality");
    document.getElementById("mtbf-summary-panel")?.classList.toggle("active", view === "mtbf");
}

function setPerformanceView(view) {
    document.querySelectorAll("[data-performance-view]").forEach((button) => {
        button.classList.toggle("active", button.dataset.performanceView === view);
    });
    document.getElementById("machine-groups-panel")?.classList.toggle("active", view === "machine-groups");
    document.getElementById("utilities-panel")?.classList.toggle("active", view === "utilities");
}

function wireFilters() {
    [
        "group-criticality-filter",
        "group-location-filter",
        "group-search",
    ].forEach((id) => {
        const element = document.getElementById(id);
        if (element) element.addEventListener("input", renderMachineGroupTable);
        if (element && element.tagName === "SELECT") element.addEventListener("change", renderMachineGroupTable);
    });

    document.getElementById("period-select")?.addEventListener("change", handlePeriodChange);
    document.getElementById("month-select")?.addEventListener("change", handlePeriodChange);
    document.querySelectorAll("[data-summary-view]").forEach((button) => {
        button.addEventListener("click", () => setSummaryView(button.dataset.summaryView || "criticality"));
    });
    document.querySelectorAll("[data-performance-view]").forEach((button) => {
        button.addEventListener("click", () => setPerformanceView(button.dataset.performanceView || "machine-groups"));
    });
}

async function init() {
    wireFilters();
    setSummaryView("criticality");
    setPerformanceView("machine-groups");
    const period = document.getElementById("period-select")?.value || "ytd";
    toggleMonthFilter(period);

    try {
        await loadDowntimeCacheFile();
        const cachedDefault = getCachedDowntimePayload(period, "");
        const monthOptions = cachedDefault?.months || buildMonthOptions(cachedDefault?.meta?.reference_end);
        populateMonthOptions(monthOptions, cachedDefault?.meta?.month || monthOptions[0]?.value || "");
        const month = period === "mtd" ? (document.getElementById("month-select")?.value || "") : "";
        await loadDowntimeData(period, month);
    } catch (error) {
        console.error("Downtime page load error:", error);
        renderAlerts([{ level: "critical", message: "Downtime data could not be loaded from the current imported work order source." }]);
    }
}

function refreshCurrentView() {
    const period = document.getElementById("period-select")?.value || "ytd";
    const month = period === "mtd" ? (document.getElementById("month-select")?.value || "") : "";
    loadDowntimeData(period, month).catch((error) => {
        console.error("Downtime refresh failed:", error);
    });
}

document.addEventListener("DOMContentLoaded", init);
window.addEventListener("focus", refreshCurrentView);
document.addEventListener("visibilitychange", () => {
    if (!document.hidden) refreshCurrentView();
});
setInterval(refreshCurrentView, 60000);
