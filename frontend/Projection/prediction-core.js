/**
 * prediction-core.js
 * Shared prediction math, mock data, chart helpers and utilities.
 * Included by all Projection subpages via <script src="/Projection/prediction-core.js">
 */

const THRESHOLDS = {
    wastewater: { maxFlow: 500, capacityWarnPct: 0.7, capacityCritPct: 0.9 },
    mdb: { maxLoad: 300000, warnPct: 0.7, critPct: 0.9 },
    boiler: { minEff: 70 },
    compressor: { maxEnergy: 200 },
    freezer: { maxEnergy: 150 },
    cctv: { maxEventsPerDay: 4 },
};

function buildMockSeries(base, noise, length = 24) {
    return Array.from({ length }, (_, index) =>
        Math.max(0, base + Math.sin(index / 3) * (noise * 0.4) + (Math.random() - 0.5) * noise * 0.6)
    );
}

const MOCK = {
    wastewater: buildMockSeries(280, 60, 24),
    mdb: buildMockSeries(180000, 30000, 24),
    boiler_eff: buildMockSeries(82, 8, 24),
    boiler_gas: buildMockSeries(450, 60, 24),
    compressor: buildMockSeries(95, 20, 24),
    freezer_kwh: buildMockSeries(110, 25, 24),
    freezer_temp: buildMockSeries(-22, 3, 24),
    wtp_flow: buildMockSeries(320, 40, 24),
    wtp_chlorine: buildMockSeries(0.8, 0.2, 24),
    cctv_events: [2, 1, 3, 0, 2, 4, 1, 2, 3, 1, 5, 2],
};

function movingAverage(values, window = 5) {
    if (!values || values.length === 0) return 0;
    const slice = values.slice(-Math.min(window, values.length));
    return slice.reduce((sum, value) => sum + value, 0) / slice.length;
}

function linearExtrapolate(values, steps = 1) {
    const pointCount = Math.min(values.length, 10);
    if (pointCount < 2) return values[values.length - 1] || 0;

    const slice = values.slice(-pointCount);
    const meanX = (pointCount - 1) / 2;
    const meanY = slice.reduce((sum, value) => sum + value, 0) / pointCount;
    let numerator = 0;
    let denominator = 0;

    slice.forEach((value, index) => {
        numerator += (index - meanX) * (value - meanY);
        denominator += (index - meanX) ** 2;
    });

    const slope = denominator !== 0 ? numerator / denominator : 0;
    return (meanY - slope * meanX) + slope * (pointCount - 1 + steps);
}

function generatePredictions(history, count = 6) {
    const series = [...history];
    const output = [];

    for (let index = 0; index < count; index += 1) {
        const nextValue = Math.max(0, linearExtrapolate(series, 1));
        output.push(nextValue);
        series.push(nextValue);
    }

    return output;
}

function rSquared(values) {
    const pointCount = Math.min(values.length, 10);
    if (pointCount < 3) return 85;

    const slice = values.slice(-pointCount);
    const meanY = slice.reduce((sum, value) => sum + value, 0) / pointCount;
    const ssTot = slice.reduce((sum, value) => sum + (value - meanY) ** 2, 0);
    if (ssTot === 0) return 99;

    const meanX = (pointCount - 1) / 2;
    let numerator = 0;
    let denominator = 0;
    slice.forEach((value, index) => {
        numerator += (index - meanX) * (value - meanY);
        denominator += (index - meanX) ** 2;
    });

    const slope = denominator !== 0 ? numerator / denominator : 0;
    const intercept = meanY - slope * meanX;
    const ssRes = slice.reduce((sum, value, index) => sum + (value - (intercept + slope * index)) ** 2, 0);
    return Math.max(0, Math.min(100, Math.round((1 - ssRes / ssTot) * 100)));
}

function trendDirection(values, higherIsBetter = true) {
    if (!values || values.length < 3) return { label: "Stable", cls: "ok" };

    const slope = linearExtrapolate(values, 1) - values[values.length - 1];
    const rising = slope > 0.5;
    const falling = slope < -0.5;

    if (higherIsBetter) {
        if (rising) return { label: "Improving", cls: "ok" };
        if (falling) return { label: "Declining", cls: "danger" };
    } else {
        if (falling) return { label: "Improving", cls: "ok" };
        if (rising) return { label: "Rising", cls: "warn" };
    }

    return { label: "Stable", cls: "ok" };
}

function statusFromRisk(risk) {
    if (risk === "danger") return { label: "CRITICAL", cls: "danger" };
    if (risk === "warn") return { label: "WARNING", cls: "warn" };
    return { label: "NORMAL", cls: "ok" };
}

function buildTimeLabels(historyCount, futureCount) {
    const now = new Date();
    const labels = [];

    for (let index = historyCount; index > 0; index -= 1) {
        const pointTime = new Date(now.getTime() - index * 3600000);
        labels.push(pointTime.getHours().toString().padStart(2, "0") + ":00");
    }

    for (let index = 1; index <= futureCount; index += 1) {
        const pointTime = new Date(now.getTime() + index * 3600000);
        labels.push(pointTime.getHours().toString().padStart(2, "0") + ":00+");
    }

    return labels;
}

function renderForecastLineChart(canvasId, historical, predictions, options = {}) {
    const {
        label = "Value",
        unit = "",
        color = "#3b82f6",
        FUTURE = predictions.length,
    } = options;

    const canvas = document.getElementById(canvasId);
    if (!canvas) return null;

    const existing = Chart.getChart(canvas);
    if (existing) existing.destroy();

    const labels = buildTimeLabels(historical.length, FUTURE);
    const historyData = [...historical, ...Array(FUTURE).fill(null)];
    const predictionData = [...Array(historical.length - 1).fill(null), historical[historical.length - 1], ...predictions];

    return new Chart(canvas.getContext("2d"), {
        type: "line",
        data: {
            labels,
            datasets: [
                {
                    label: `${label} (Historical)`,
                    data: historyData,
                    borderColor: color,
                    backgroundColor: `${color}14`,
                    borderWidth: 2.5,
                    pointRadius: 2,
                    tension: 0.4,
                    fill: true,
                    spanGaps: false,
                },
                {
                    label: `${label} (Predicted)`,
                    data: predictionData,
                    borderColor: "#f59e0b",
                    backgroundColor: "rgba(245, 158, 11, 0.06)",
                    borderWidth: 2.5,
                    borderDash: [8, 4],
                    pointRadius: 3,
                    pointBackgroundColor: "#f59e0b",
                    tension: 0.4,
                    fill: false,
                    spanGaps: false,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: "index", intersect: false },
            plugins: {
                legend: { position: "top", labels: { usePointStyle: true, font: { size: 12 } } },
                tooltip: {
                    callbacks: {
                        label(context) {
                            return `${context.dataset.label}: ${context.parsed.y !== null ? context.parsed.y.toFixed(1) + (unit ? ` ${unit}` : "") : "N/A"}`;
                        },
                    },
                },
            },
            scales: {
                x: { grid: { display: false }, ticks: { maxRotation: 45, font: { size: 10 } } },
                y: { grid: { color: "#f1f5f9" }, ticks: { font: { size: 11 } } },
            },
        },
    });
}

function setText(id, value) {
    const element = document.getElementById(id);
    if (element) element.textContent = value;
}

function setHtml(id, html) {
    const element = document.getElementById(id);
    if (element) element.innerHTML = html;
}

function fmt(value, digits = 1) {
    return value == null || Number.isNaN(Number(value)) ? "--" : Number(value).toFixed(digits);
}

function fmt0(value) {
    return fmt(value, 0);
}

function fmtK(value) {
    return value >= 1000 ? `${(value / 1000).toFixed(1)}k` : fmt0(value);
}

async function tryFetchAPI(url) {
    try {
        const response = await fetch(url);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const text = await response.text();
        return JSON.parse(text.replace(/: NaN/g, ": null"));
    } catch {
        return null;
    }
}

function startClock(id = "clock") {
    const tick = () => {
        const element = document.getElementById(id);
        if (element) element.textContent = new Date().toTimeString().slice(0, 8);
    };

    tick();
    setInterval(tick, 1000);
}
