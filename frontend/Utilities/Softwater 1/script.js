document.addEventListener("DOMContentLoaded", () => {
    let charts = {};
    let zoomedChart = null;
    let activeZoom = null;
    const SOURCE = 'softwater1';

    const today = new Date().toISOString().split('T')[0];

    const presStart = document.getElementById('pressure-start');
    const presEnd   = document.getElementById('pressure-end');
    const clStart   = document.getElementById('chlorine-start');
    const clEnd     = document.getElementById('chlorine-end');
    [presStart, presEnd, clStart, clEnd].forEach(el => { if (el) el.value = today; });

    const zoomModal      = document.getElementById('zoomModal');
    const zoomStartInput = document.getElementById('zoom-start-date');
    const zoomEndInput   = document.getElementById('zoom-end-date');
    const zoomTitleEl    = document.getElementById('zoomTitle');

    // ── HELPERS ──────────────────────────────────────────────────────────────

    function buildUrl(endpoint, start, end) {
        if (start && end) return `/api/wtp/${endpoint}?start_date=${start}&end_date=${end}&source=${SOURCE}`;
        return `/api/wtp/${endpoint}?source=${SOURCE}`;
    }

    async function fetchJson(url) { return (await fetch(url)).json(); }

    // ── DATA LOADERS ─────────────────────────────────────────────────────────

    async function loadWTPData() {
        try {
            const response = await fetch("/api/wtp");
            const data = await response.json();
            updateKPIs(data);
            await updateChlorineStatus();
            await updatePressureStatus();
            await fetchPressureByDate(presStart.value, presEnd.value, true);
            await fetchChlorineByDate(clStart.value, clEnd.value, true);
        } catch (err) { console.error("🔥 WTP load error:", err); }
    }

    async function updateChlorineStatus() {
        try {
            const data = await fetchJson(`/api/wtp/chlorine?date=${today}&source=${SOURCE}`);
            const statusEl   = document.getElementById("kpi-wtp-status");
            const clStatusEl = document.getElementById("kpi-chlorine-status");
            if (data.length > 0) {
                const val = data[data.length - 1].mg;
                const isAttention = val < 0.5 || val > 1.0;
                if (statusEl) {
                    statusEl.textContent = isAttention ? "ATTENTION" : "NORMAL";
                    statusEl.className   = isAttention ? "kpi-value neg" : "kpi-value pos";
                }
                if (clStatusEl) {
                    clStatusEl.textContent = isAttention ? "ATTENTION" : "NORMAL";
                    clStatusEl.className   = isAttention ? "kpi-status neg" : "kpi-status pos";
                }
            } else {
                if (statusEl)   { statusEl.textContent = "UNAVAILABLE";   statusEl.className   = "kpi-value unavailable"; }
                if (clStatusEl) { clStatusEl.textContent = "UNAVAILABLE"; clStatusEl.className = "kpi-status unavailable"; }
            }
        } catch (err) { console.error("Chlorine status error:", err); }
    }

    async function updatePressureStatus() {
        try {
            const data = await fetchJson(`/api/wtp/pressure?date=${today}&source=${SOURCE}`);
            const statusEl = document.getElementById("kpi-pressure-status");
            if (data.length > 0) {
                document.getElementById("kpi-ro-pres").textContent = data[data.length - 1].bar.toFixed(1);
                if (statusEl) { statusEl.textContent = "NORMAL"; statusEl.className = "kpi-status pos"; }
            } else {
                document.getElementById("kpi-ro-pres").textContent = "--";
                if (statusEl) { statusEl.textContent = "UNAVAILABLE"; statusEl.className = "kpi-status unavailable"; }
            }
        } catch (err) { console.error("Pressure status error:", err); }
    }

    async function fetchPressureByDate(start, end, isAutomatic = false) {
        try {
            let data = await fetchJson(buildUrl('pressure', start, end));
            if (data.length === 0 && isAutomatic) data = await fetchJson(`/api/wtp/pressure?source=${SOURCE}`);

            if (data.length === 0) {
                document.getElementById("kpi-ro-pres").textContent = "--";
                renderChart('pressureChart', 'line', { labels: [], datasets: [{ label: 'Softwater 1', data: [], borderColor: '#3b82f6', tension: 0.3 }] });
                return;
            }
            document.getElementById("kpi-ro-pres").textContent = data[data.length - 1].bar.toFixed(1);
            renderChart('pressureChart', 'line', {
                labels: data.map(d => d.time),
                datasets: [{ label: 'Softwater 1 (bar)', data: data.map(d => d.bar), borderColor: '#3b82f6', backgroundColor: 'rgba(59,130,246,0.1)', fill: false, tension: 0.3, borderWidth: 2 }]
            });
        } catch (err) { console.error("Pressure fetch error:", err); }
    }

    async function fetchChlorineByDate(start, end, isAutomatic = false) {
        try {
            let data = await fetchJson(buildUrl('chlorine', start, end));
            if (data.length === 0 && isAutomatic) data = await fetchJson(`/api/wtp/chlorine?source=${SOURCE}`);

            if (data.length === 0) {
                ['kpi-chlorine','kpi-chlorine-avg','kpi-chlorine-max','kpi-chlorine-min'].forEach(id => {
                    document.getElementById(id).textContent = "--";
                });
                renderChart('chlorineChart', 'line', { labels: [], datasets: [{ label: 'Residual Cl2', data: [], borderColor: '#f59e0b', tension: 0.3 }] });
                return;
            }

            const vals = data.map(d => d.mg);
            document.getElementById("kpi-chlorine").textContent     = vals[vals.length - 1].toFixed(2);
            document.getElementById("kpi-chlorine-avg").textContent  = (vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(2);
            document.getElementById("kpi-chlorine-max").textContent  = Math.max(...vals).toFixed(2);
            document.getElementById("kpi-chlorine-min").textContent  = Math.min(...vals).toFixed(2);

            renderChart('chlorineChart', 'line', {
                labels: data.map(d => d.time),
                datasets: [{ label: 'Residual Cl2 (mg)', data: data.map(d => d.mg), borderColor: '#f59e0b', backgroundColor: 'rgba(245,158,11,0.1)', fill: true, tension: 0.3 }]
            });
        } catch (err) { console.error("Chlorine fetch error:", err); }
    }

    // ── ZOOM MODAL ────────────────────────────────────────────────────────────

    async function openZoom(type) {
        activeZoom = type;
        zoomStartInput.value = (type === 'pressure' ? presStart : clStart)?.value || today;
        zoomEndInput.value   = (type === 'pressure' ? presEnd   : clEnd)?.value   || today;
        zoomTitleEl.textContent = type === 'pressure' ? 'Softwater 1 Pressure (bar)' : 'Chlorine Monitoring (mg)';
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
        const color    = type === 'pressure' ? '#3b82f6' : '#f59e0b';
        const label    = type === 'pressure' ? 'Softwater 1 (bar)' : 'Residual Cl2 (mg)';

        let data = await fetchJson(buildUrl(endpoint, start, end));
        if (data.length === 0) data = await fetchJson(`/api/wtp/${endpoint}?source=${SOURCE}`);

        zoomedChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: data.map(d => d.time),
                datasets: [{ label, data: data.map(d => d[valueKey]), borderColor: color, backgroundColor: color + '1a', fill: type === 'chlorine', tension: 0.3, borderWidth: 2 }]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
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
            type, data,
            options: {
                responsive: true, maintainAspectRatio: false,
                plugins: { legend: { position: 'bottom' }, tooltip: { mode: 'index', intersect: false } },
                scales: {
                    x: { grid: { display: false } },
                    y: { grid: { color: '#f1f5f9' }, title: { display: true, text: 'Value' } }
                }
            }
        });
    }

    // ── UI UPDATERS ───────────────────────────────────────────────────────────

    function updateKPIs(data) {
        document.getElementById("kpi-ro-total").textContent = (data.flow_totals.soft_water_1?.slice(-1)[0]?.m3 || 0).toLocaleString();
    }

    // ── LISTENERS ─────────────────────────────────────────────────────────────

    document.getElementById('pressure-apply')?.addEventListener('click', () => fetchPressureByDate(presStart.value, presEnd.value));
    document.getElementById('chlorine-apply')?.addEventListener('click', () => fetchChlorineByDate(clStart.value, clEnd.value));
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
