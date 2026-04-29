document.addEventListener("DOMContentLoaded", () => {
    let charts = {};
    let zoomedChart = null;
    let activeZoom = null; // 'pressure' | 'chlorine'

    const today = new Date().toISOString().split('T')[0];

    // Inline range inputs
    const presStart = document.getElementById('pressure-start');
    const presEnd   = document.getElementById('pressure-end');
    const clStart   = document.getElementById('chlorine-start');
    const clEnd     = document.getElementById('chlorine-end');
    [presStart, presEnd, clStart, clEnd].forEach(el => { if (el) el.value = today; });

    // Zoom modal elements
    const zoomModal      = document.getElementById('zoomModal');
    const zoomStartInput = document.getElementById('zoom-start-date');
    const zoomEndInput   = document.getElementById('zoom-end-date');
    const zoomTitleEl    = document.getElementById('zoomTitle');

    // ── HELPERS ──────────────────────────────────────────────────────────────

    function buildUrl(endpoint, source, start, end) {
        if (start && end) return `/api/wtp/${endpoint}?start_date=${start}&end_date=${end}&source=${source}`;
        return `/api/wtp/${endpoint}?source=${source}`;
    }

    async function fetchJson(url) {
        const res = await fetch(url);
        return res.json();
    }

    function classifyCombinedChlorine(value) {
        const val = Number(value);
        if (!Number.isFinite(val)) return "UNAVAILABLE";
        if (val < 0.1 || val > 1.5) return "WARNING";
        if (val < 0.2 || val > 1.2) return "ATTENTION";
        return "NORMAL";
    }

    function classifyPressureDeviation(data) {
        if (!Array.isArray(data) || data.length === 0) return "UNAVAILABLE";
        const values = data.map(d => Number(d.bar)).filter(Number.isFinite);
        if (values.length < 6) return "NORMAL";
        const latest = values[values.length - 1];
        const baselineValues = values.slice(0, -1);
        const baseline = baselineValues.reduce((sum, value) => sum + value, 0) / baselineValues.length;
        if (!Number.isFinite(baseline) || baseline <= 0) return "NORMAL";
        const deviation = Math.abs(latest - baseline) / baseline;
        if (deviation > 0.30) return "WARNING";
        if (deviation > 0.20) return "ATTENTION";
        return "NORMAL";
    }

    function applyKpiStatus(el, status) {
        if (!el) return;
        el.textContent = status;
        el.className = status === "NORMAL" ? "kpi-status pos" : status === "UNAVAILABLE" ? "kpi-status unavailable" : "kpi-status neg";
    }

    // ── DATA LOADERS ─────────────────────────────────────────────────────────

    async function loadWTPData() {
        try {
            const response = await fetch("/api/wtp");
            const data = await response.json();

            updateKPIs(data);
            updateFlowRateDisplay(data.flow_rates);

            renderBarChart('flowDistributionChart', {
                labels: ['Deep Well', 'Soft 1', 'Soft 2', 'RO Water', 'Fire Tank'],
                datasets: [{
                    label: 'Total Accumulation (m³)',
                    data: [
                        data.flow_totals.deep_well?.slice(-1)[0]?.m3 || 0,
                        data.flow_totals.soft_water_1?.slice(-1)[0]?.m3 || 0,
                        data.flow_totals.soft_water_2?.slice(-1)[0]?.m3 || 0,
                        data.flow_totals.ro_water?.slice(-1)[0]?.m3 || 0,
                        data.flow_totals.fire_water?.slice(-1)[0]?.m3 || 0
                    ],
                    backgroundColor: ['#1e293b', '#3b82f6', '#60a5fa', '#10b981', '#ef4444'],
                    borderRadius: 6
                }]
            });

            await updatePressureStatus();
            await updateChlorineStatus();
            await fetchPressure(presStart?.value, presEnd?.value, true);
            await fetchChlorine(clStart?.value, clEnd?.value, true);

        } catch (err) {
            console.error("🔥 WTP load error:", err);
        }
    }

    async function updateChlorineStatus() {
        try {
            const [roRes, sw1Res, sw2Res] = await Promise.all([
                fetch(`/api/wtp/chlorine?date=${today}&source=ro`),
                fetch(`/api/wtp/chlorine?date=${today}&source=softwater1`),
                fetch(`/api/wtp/chlorine?date=${today}&source=softwater2`)
            ]);
            const roData  = await roRes.json();
            const sw1Data = await sw1Res.json();
            const sw2Data = await sw2Res.json();

            const setStatus = (id, statusId, data) => {
                if (data.length > 0) {
                    const val = data[data.length - 1].mg;
                    document.getElementById(id).textContent = val.toFixed(2);
                    applyKpiStatus(document.getElementById(statusId), classifyCombinedChlorine(val));
                } else {
                    document.getElementById(id).textContent = "--";
                    applyKpiStatus(document.getElementById(statusId), "UNAVAILABLE");
                }
            };
            setStatus("kpi-ro-chlorine",   "kpi-ro-status",   roData);
            setStatus("kpi-soft1-chlorine","kpi-soft1-status", sw1Data);
            setStatus("kpi-soft2-chlorine","kpi-soft2-status", sw2Data);
        } catch (err) { console.error("Chlorine status error:", err); }
    }

    async function updatePressureStatus() {
        try {
            const [roRes, sw1Res, sw2Res] = await Promise.all([
                fetch(`/api/wtp/pressure?date=${today}&source=ro`),
                fetch(`/api/wtp/pressure?date=${today}&source=softwater1`),
                fetch(`/api/wtp/pressure?date=${today}&source=softwater2`)
            ]);
            const roData  = await roRes.json();
            const sw1Data = await sw1Res.json();
            const sw2Data = await sw2Res.json();

            const setPres = (valId, statusId, data) => {
                if (data.length > 0) {
                    document.getElementById(valId).textContent = data[data.length - 1].bar.toFixed(1);
                    applyKpiStatus(document.getElementById(statusId), classifyPressureDeviation(data));
                } else {
                    document.getElementById(valId).textContent = "--";
                    applyKpiStatus(document.getElementById(statusId), "UNAVAILABLE");
                }
            };
            setPres("kpi-ro-pressure",    "kpi-ro-pres-status",    roData);
            setPres("kpi-soft1-pressure", "kpi-soft1-pres-status", sw1Data);
            setPres("kpi-soft2-pressure", "kpi-soft2-pres-status", sw2Data);
        } catch (err) { console.error("Pressure status error:", err); }
    }

    async function fetchPressure(start, end, isAutomatic = false) {
        try {
            let [roData, sw1Data, sw2Data] = await Promise.all([
                fetchJson(buildUrl('pressure', 'ro',         start, end)),
                fetchJson(buildUrl('pressure', 'softwater1', start, end)),
                fetchJson(buildUrl('pressure', 'softwater2', start, end))
            ]);

            if (roData.length === 0 && sw1Data.length === 0 && isAutomatic) {
                [roData, sw1Data, sw2Data] = await Promise.all([
                    fetchJson('/api/wtp/pressure?source=ro'),
                    fetchJson('/api/wtp/pressure?source=softwater1'),
                    fetchJson('/api/wtp/pressure?source=softwater2')
                ]);
            }

            const base = roData.length > 0 ? roData : sw1Data.length > 0 ? sw1Data : sw2Data;
            renderChart('pressureChart', 'line', {
                labels: base.map(d => d.time),
                datasets: [
                    { label: 'RO Water',    data: roData.map(d => d.bar),  borderColor: '#10b981', backgroundColor: 'rgba(16,185,129,0.08)', fill: false, tension: 0.3, borderWidth: 2 },
                    { label: 'Softwater 1', data: sw1Data.map(d => d.bar), borderColor: '#3b82f6', backgroundColor: 'rgba(59,130,246,0.08)', fill: false, tension: 0.3, borderWidth: 2 },
                    { label: 'Softwater 2', data: sw2Data.map(d => d.bar), borderColor: '#f59e0b', backgroundColor: 'rgba(245,158,11,0.08)', fill: false, tension: 0.3, borderWidth: 2 }
                ]
            });
        } catch (err) { console.error("Pressure fetch error:", err); }
    }

    async function fetchChlorine(start, end, isAutomatic = false) {
        try {
            let [roData, sw1Data, sw2Data] = await Promise.all([
                fetchJson(buildUrl('chlorine', 'ro',         start, end)),
                fetchJson(buildUrl('chlorine', 'softwater1', start, end)),
                fetchJson(buildUrl('chlorine', 'softwater2', start, end))
            ]);

            if (roData.length === 0 && sw1Data.length === 0 && isAutomatic) {
                [roData, sw1Data, sw2Data] = await Promise.all([
                    fetchJson('/api/wtp/chlorine?source=ro'),
                    fetchJson('/api/wtp/chlorine?source=softwater1'),
                    fetchJson('/api/wtp/chlorine?source=softwater2')
                ]);
            }

            const base = roData.length > 0 ? roData : sw1Data.length > 0 ? sw1Data : sw2Data;
            renderChart('chlorineChart', 'line', {
                labels: base.map(d => d.time),
                datasets: [
                    { label: 'RO Water',    data: roData.map(d => d.mg),  borderColor: '#10b981', backgroundColor: 'rgba(16,185,129,0.1)', fill: false, tension: 0.3, borderWidth: 2 },
                    { label: 'Softwater 1', data: sw1Data.map(d => d.mg), borderColor: '#3b82f6', backgroundColor: 'rgba(59,130,246,0.1)', fill: false, tension: 0.3, borderWidth: 2 },
                    { label: 'Softwater 2', data: sw2Data.map(d => d.mg), borderColor: '#f59e0b', backgroundColor: 'rgba(245,158,11,0.1)', fill: false, tension: 0.3, borderWidth: 2 }
                ]
            });
        } catch (err) { console.error("Chlorine fetch error:", err); }
    }

    // ── ZOOM MODAL ────────────────────────────────────────────────────────────

    async function openZoom(type) {
        activeZoom = type;
        zoomStartInput.value = (type === 'pressure' ? presStart : clStart)?.value || today;
        zoomEndInput.value   = (type === 'pressure' ? presEnd   : clEnd)?.value   || today;
        zoomTitleEl.textContent = type === 'pressure' ? 'System Pressure Trends (bar)' : 'Chlorine Monitoring (mg)';
        zoomModal.classList.add('active');
        document.body.style.overflow = 'hidden';
        await renderZoomChart(type, zoomStartInput.value, zoomEndInput.value);
    }

    function closeZoom() {
        zoomModal.classList.remove('active');
        document.body.style.overflow = '';
        if (zoomedChart) { zoomedChart.destroy(); zoomedChart = null; }
        activeZoom = null;
    }

    async function renderZoomChart(type, start, end) {
        if (zoomedChart) { zoomedChart.destroy(); zoomedChart = null; }
        const ctx = document.getElementById('zoomedChart');
        if (!ctx) return;

        const endpoint = type === 'pressure' ? 'pressure' : 'chlorine';
        const valueKey = type === 'pressure' ? 'bar' : 'mg';

        let [roData, sw1Data, sw2Data] = await Promise.all([
            fetchJson(buildUrl(endpoint, 'ro',         start, end)),
            fetchJson(buildUrl(endpoint, 'softwater1', start, end)),
            fetchJson(buildUrl(endpoint, 'softwater2', start, end))
        ]);

        if (roData.length === 0 && sw1Data.length === 0) {
            [roData, sw1Data, sw2Data] = await Promise.all([
                fetchJson(`/api/wtp/${endpoint}?source=ro`),
                fetchJson(`/api/wtp/${endpoint}?source=softwater1`),
                fetchJson(`/api/wtp/${endpoint}?source=softwater2`)
            ]);
        }

        const base = roData.length > 0 ? roData : sw1Data.length > 0 ? sw1Data : sw2Data;

        zoomedChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: base.map(d => d.time),
                datasets: [
                    { label: 'RO Water',    data: roData.map(d => d[valueKey]),  borderColor: '#10b981', backgroundColor: 'rgba(16,185,129,0.08)', fill: false, tension: 0.3, borderWidth: 2 },
                    { label: 'Softwater 1', data: sw1Data.map(d => d[valueKey]), borderColor: '#3b82f6', backgroundColor: 'rgba(59,130,246,0.08)', fill: false, tension: 0.3, borderWidth: 2 },
                    { label: 'Softwater 2', data: sw2Data.map(d => d[valueKey]), borderColor: '#f59e0b', backgroundColor: 'rgba(245,158,11,0.08)', fill: false, tension: 0.3, borderWidth: 2 }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { position: 'bottom' },
                    tooltip: {
                        mode: 'index', intersect: false,
                        titleFont: { size: 24, weight: 'bold' },
                        bodyFont: { size: 22 },
                        padding: 27,
                        boxPadding: 12
                    }
                },
                scales: {
                    x: { grid: { display: false } },
                    y: { grid: { color: '#f1f5f9' }, title: { display: true, text: type === 'pressure' ? 'bar' : 'mg' } }
                }
            }
        });
    }

    // ── CHART HELPERS ─────────────────────────────────────────────────────────

    function renderChart(id, type, data) {
        const ctx = document.getElementById(id);
        if (!ctx) return;
        if (charts[id]) charts[id].destroy();
        charts[id] = new Chart(ctx, {
            type,
            data,
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { position: 'bottom' }, tooltip: { mode: 'index', intersect: false } },
                scales: {
                    x: { grid: { display: false } },
                    y: { grid: { color: '#f1f5f9' }, title: { display: true, text: 'Value' } }
                }
            }
        });
    }

    function renderBarChart(id, chartData) {
        const ctx = document.getElementById(id);
        if (!ctx || !window.ChartDataLabels) return;
        if (charts[id]) charts[id].destroy();
        charts[id] = new Chart(ctx, {
            type: 'bar',
            data: chartData,
            plugins: [ChartDataLabels],
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { datalabels: { anchor: 'end', align: 'top', color: '#475569' } }
            }
        });
    }

    // ── UI UPDATERS ───────────────────────────────────────────────────────────

    function updateFlowRateDisplay(rates) {
        document.getElementById('rate-well').textContent  = (rates.deep_well   || 0).toFixed(2);
        document.getElementById('rate-soft1').textContent = (rates.soft_water_1 || 0).toFixed(2);
        document.getElementById('rate-soft2').textContent = (rates.soft_water_2 || 0).toFixed(2);
        document.getElementById('rate-ro').textContent    = (rates.ro_water    || 0).toFixed(2);
        document.getElementById('rate-fire').textContent  = (rates.fire_water  || 0).toFixed(2);
    }

    function updateKPIs(data) {
        const roTotal = data.flow_totals.ro_water?.slice(-1)[0]?.m3 || 0;
        const soft1Total = data.flow_totals.soft_water_1?.slice(-1)[0]?.m3 || 0;
        const soft2Total = data.flow_totals.soft_water_2?.slice(-1)[0]?.m3 || 0;
        const treatedTotal = roTotal + soft1Total + soft2Total;

        document.getElementById("kpi-ro-total").textContent = roTotal.toLocaleString();
        document.getElementById("kpi-soft1-total").textContent = soft1Total.toLocaleString();
        document.getElementById("kpi-soft2-total").textContent = soft2Total.toLocaleString();

        document.getElementById("treated-water-total").textContent = `${treatedTotal.toLocaleString()} m³`;
        document.getElementById("treated-water-ro").textContent = `${roTotal.toLocaleString()} m³`;
        document.getElementById("treated-water-soft1").textContent = `${soft1Total.toLocaleString()} m³`;
        document.getElementById("treated-water-soft2").textContent = `${soft2Total.toLocaleString()} m³`;
    }

    // ── LISTENERS ─────────────────────────────────────────────────────────────

    document.getElementById('pressure-apply')?.addEventListener('click', () => fetchPressure(presStart.value, presEnd.value));
    document.getElementById('chlorine-apply')?.addEventListener('click', () => fetchChlorine(clStart.value, clEnd.value));

    document.getElementById('zoom-pressure-btn')?.addEventListener('click', () => openZoom('pressure'));
    document.getElementById('zoom-chlorine-btn')?.addEventListener('click', () => openZoom('chlorine'));
    document.getElementById('zoomClose')?.addEventListener('click', closeZoom);
    document.getElementById('zoomBackdrop')?.addEventListener('click', closeZoom);
    document.getElementById('zoom-apply')?.addEventListener('click', () => {
        if (activeZoom) renderZoomChart(activeZoom, zoomStartInput.value, zoomEndInput.value);
    });

    loadWTPData();
    setInterval(loadWTPData, 60000);
});
