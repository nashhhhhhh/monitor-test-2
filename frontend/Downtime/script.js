let downtimePayload = null;
let downtimeCachePayload = null;
const chartRefs = {};
const EXCLUDED_SOURCE_LABEL = 'Energy-derived';

function normalizeEventSource(event) {
    const detectionType = String(event?.detection_type || '').trim().toLowerCase();
    if (detectionType === 'fault / down status') {
        return 'Status-derived';
    }
    return event?.source || '--';
}

function normalizeEvent(event) {
    if (!event) return event;
    return {
        ...event,
        source: normalizeEventSource(event),
    };
}

function ensureCanvas(id) {
    const existing = document.getElementById(id);
    if (existing) return existing;

    const container = document.querySelector(`[data-chart-slot="${id}"]`);
    if (!container) return null;
    container.innerHTML = `<canvas id="${id}"></canvas>`;
    return document.getElementById(id);
}

function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}

function fmtHours(hours) {
    if (hours === null || hours === undefined || Number.isNaN(Number(hours))) return '--';
    const numeric = Number(hours);
    if (numeric <= 0) return '0 min';
    if (numeric < 1) return `${Math.round(numeric * 60)} min`;
    return `${numeric.toFixed(2)} h`;
}

function fmtPercent(value) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return '--';
    return `${Number(value).toFixed(1)}%`;
}

function fmtDateTime(value) {
    if (!value) return '--';
    const dt = new Date(value);
    if (Number.isNaN(dt.getTime())) return '--';
    return dt.toLocaleString('en-GB', {
        day: '2-digit',
        month: 'short',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
    });
}

function destroyChart(id) {
    if (chartRefs[id]) {
        chartRefs[id].destroy();
        delete chartRefs[id];
    }
}

function renderAlertBanner(alerts) {
    void alerts;
}

async function loadDowntimeCacheFile() {
    if (downtimeCachePayload !== null) return downtimeCachePayload;
    try {
        const response = await fetch(`./downtime-cache.json?v=20260408a&_=${Date.now()}`, {
            cache: 'no-store',
        });
        if (!response.ok) {
            downtimeCachePayload = false;
            return null;
        }
        downtimeCachePayload = await response.json();
        return downtimeCachePayload;
    } catch (error) {
        console.warn('Downtime cache load failed:', error);
        downtimeCachePayload = false;
        return null;
    }
}

function getCachedDowntimePayload(period, month) {
    const payloads = downtimeCachePayload?.payloads || {};
    const key = period === 'mtd' && month ? `mtd:${month}` : period;
    return payloads[key] || null;
}

function getChartEvents() {
    return (downtimePayload?.events || [])
        .map(normalizeEvent)
        .filter(event => event.source !== EXCLUDED_SOURCE_LABEL);
}

function sumEventHours(events) {
    return events.reduce((sum, event) => sum + Number(event.duration_hours || 0), 0);
}

function getReferenceEnd() {
    const metaEnd = downtimePayload?.meta?.reference_end ? new Date(downtimePayload.meta.reference_end) : null;
    if (metaEnd && !Number.isNaN(metaEnd.getTime())) return metaEnd;

    const latestEvent = getChartEvents()
        .map(event => new Date(event.end_time || event.start_time))
        .filter(dt => !Number.isNaN(dt.getTime()))
        .sort((a, b) => b - a)[0];

    return latestEvent || new Date();
}

function buildSummaryFromEvents(events) {
    const referenceEnd = getReferenceEnd();
    const weekStart = new Date(referenceEnd);
    weekStart.setDate(referenceEnd.getDate() - 6);
    weekStart.setHours(0, 0, 0, 0);

    const monthStart = new Date(referenceEnd.getFullYear(), referenceEnd.getMonth(), 1);
    const normalizedEvents = events
        .map(event => ({ ...event, _start: new Date(event.start_time || event.end_time) }))
        .filter(event => !Number.isNaN(event._start.getTime()));

    const totalHours = sumEventHours(normalizedEvents);
    const weekHours = sumEventHours(normalizedEvents.filter(event => event._start >= weekStart && event._start <= referenceEnd));
    const monthHours = sumEventHours(normalizedEvents.filter(event => event._start >= monthStart && event._start <= referenceEnd));
    const longestEventHours = normalizedEvents.reduce((max, event) => Math.max(max, Number(event.duration_hours || 0)), 0);

    return {
        total_hours: totalHours,
        this_week_hours: weekHours,
        this_month_hours: monthHours,
        event_count: normalizedEvents.length,
        avg_event_hours: normalizedEvents.length ? totalHours / normalizedEvents.length : null,
        longest_event_hours: normalizedEvents.length ? longestEventHours : null,
    };
}

function buildTrendFromEvents(events) {
    const referenceEnd = getReferenceEnd();
    const period = downtimePayload?.meta?.period || 'ytd';
    const startDate = new Date(referenceEnd);
    startDate.setHours(0, 0, 0, 0);

    if (period === '7d') {
        startDate.setDate(referenceEnd.getDate() - 6);
    } else if (period === '30d') {
        startDate.setDate(referenceEnd.getDate() - 29);
    } else if (period === '90d') {
        startDate.setDate(referenceEnd.getDate() - 89);
    } else if (period === 'mtd') {
        startDate.setDate(1);
    } else if (period === 'ytd') {
        startDate.setMonth(0, 1);
    } else {
        startDate.setDate(referenceEnd.getDate() - 29);
    }

    const totalDays = Math.max(1, Math.floor((referenceEnd - startDate) / 86400000) + 1);

    const labels = [];
    const downtime_hours = [];
    const event_counts = [];

    for (let index = 0; index < totalDays; index += 1) {
        const dayStart = new Date(startDate);
        dayStart.setDate(startDate.getDate() + index);
        const dayEnd = new Date(dayStart);
        dayEnd.setDate(dayStart.getDate() + 1);

        const dayEvents = events.filter(event => {
            const dt = new Date(event.start_time || event.end_time);
            return !Number.isNaN(dt.getTime()) && dt >= dayStart && dt < dayEnd;
        });

        labels.push(dayStart.toLocaleDateString('en-GB', { day: '2-digit', month: 'short' }));
        downtime_hours.push(Number(sumEventHours(dayEvents).toFixed(3)));
        event_counts.push(dayEvents.length);
    }

    return { labels, downtime_hours, event_counts };
}

function buildGroupedRows(events, keyName) {
    const grouped = new Map();
    events.forEach((event) => {
        const label = event[keyName] || 'Unassigned';
        const existing = grouped.get(label) || { label, downtime_hours: 0, event_count: 0 };
        existing.downtime_hours += Number(event.duration_hours || 0);
        existing.event_count += 1;
        grouped.set(label, existing);
    });
    return [...grouped.values()]
        .map(row => ({ ...row, downtime_hours: Number(row.downtime_hours.toFixed(3)) }))
        .sort((a, b) => (b.downtime_hours - a.downtime_hours) || (b.event_count - a.event_count) || a.label.localeCompare(b.label));
}

function buildAssetRows(events) {
    const grouped = new Map();
    events.forEach((event) => {
        const key = event.machine_code || event.machine_name || 'Unknown';
        const existing = grouped.get(key) || {
            machine_code: event.machine_code || '--',
            machine_name: event.machine_name || '--',
            system: event.system || '--',
            area: event.area || '--',
            downtime_hours: 0,
            event_count: 0,
        };
        existing.downtime_hours += Number(event.duration_hours || 0);
        existing.event_count += 1;
        grouped.set(key, existing);
    });
    return [...grouped.values()]
        .map(row => ({ ...row, downtime_hours: Number(row.downtime_hours.toFixed(3)) }))
        .sort((a, b) => (b.downtime_hours - a.downtime_hours) || (b.event_count - a.event_count) || a.machine_name.localeCompare(b.machine_name))
        .slice(0, 8);
}

function buildSourceRows(events) {
    const grouped = new Map();
    events.forEach((event) => {
        const label = event.source || 'Unknown';
        const existing = grouped.get(label) || { label, downtime_hours: 0, available: true, message: '' };
        existing.downtime_hours += Number(event.duration_hours || 0);
        grouped.set(label, existing);
    });

    const rows = [...grouped.values()].map(row => ({ ...row, downtime_hours: Number(row.downtime_hours.toFixed(3)) }));
    if (downtimePayload?.work_order_source && !rows.some(row => row.label === 'Work Order')) {
        rows.push({
            label: 'Work Order',
            downtime_hours: downtimePayload.work_order_source.available ? 0 : null,
            available: downtimePayload.work_order_source.available,
            message: downtimePayload.work_order_source.message || '',
        });
    }
    return rows;
}

function renderKPIs(summary) {
    setText('kpi-total-downtime', fmtHours(summary.total_hours));
    setText('kpi-week-downtime', fmtHours(summary.this_week_hours));
    setText('kpi-month-downtime', fmtHours(summary.this_month_hours));
    setText('kpi-event-count', summary.event_count ?? '--');
    setText('kpi-avg-event', fmtHours(summary.avg_event_hours));
    setText('kpi-longest-event', fmtHours(summary.longest_event_hours));
}

function renderTrendChart(trend) {
    const canvas = ensureCanvas('trendChart');
    if (!canvas) return;
    destroyChart('trendChart');

    if (!trend?.labels?.length) {
        canvas.closest('.chart-container').innerHTML = '<div class="empty-state">No data available</div>';
        return;
    }

    chartRefs.trendChart = new Chart(canvas.getContext('2d'), {
        data: {
            labels: trend.labels,
            datasets: [
                {
                    type: 'bar',
                    label: 'Downtime Duration',
                    data: trend.downtime_hours,
                    backgroundColor: 'rgba(239, 68, 68, 0.65)',
                    borderColor: '#ef4444',
                    borderWidth: 1,
                    borderRadius: 4,
                    yAxisID: 'y',
                },
                {
                    type: 'line',
                    label: 'Event Count',
                    data: trend.event_counts,
                    borderColor: '#3b82f6',
                    backgroundColor: '#3b82f6',
                    tension: 0.35,
                    fill: false,
                    pointRadius: 3,
                    yAxisID: 'y1',
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { position: 'top', labels: { usePointStyle: true } },
            },
            scales: {
                x: {
                    grid: { display: false },
                    ticks: { font: { size: 10 } },
                },
                y: {
                    beginAtZero: true,
                    grid: { color: '#f1f5f9' },
                    title: { display: true, text: 'Hours' },
                },
                y1: {
                    beginAtZero: true,
                    position: 'right',
                    grid: { display: false },
                    title: { display: true, text: 'Events' },
                },
            },
        },
    });
}

function renderSimpleBarChart(id, rows, labelKey, valueKey, color) {
    const canvas = ensureCanvas(id);
    if (!canvas) return;
    destroyChart(id);

    if (!rows || !rows.length) {
        canvas.closest('.chart-container').innerHTML = '<div class="empty-state">No data available</div>';
        return;
    }

    chartRefs[id] = new Chart(canvas.getContext('2d'), {
        type: 'bar',
        data: {
            labels: rows.map(row => row[labelKey]),
            datasets: [
                {
                    label: 'Downtime Duration',
                    data: rows.map(row => row[valueKey]),
                    backgroundColor: color,
                    borderRadius: 4,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            indexAxis: 'y',
            plugins: {
                legend: { display: false },
            },
            scales: {
                x: {
                    beginAtZero: true,
                    grid: { color: '#f1f5f9' },
                    title: { display: true, text: 'Hours' },
                },
                y: {
                    grid: { display: false },
                    ticks: { font: { size: 10 } },
                },
            },
        },
    });
}

function renderSourceChart(rows) {
    const canvas = ensureCanvas('sourceChart');
    const note = document.getElementById('source-note');
    if (!canvas || !note) return;
    destroyChart('sourceChart');

    const availableRows = (rows || []).filter(row => row.available && row.downtime_hours !== null && row.downtime_hours !== undefined);
    note.textContent = rows?.find(row => row.label === 'Work Order')?.message || '';

    const totalAvailableHours = availableRows.reduce((sum, row) => sum + Number(row.downtime_hours || 0), 0);
    if (!availableRows.length || totalAvailableHours <= 0) {
        canvas.closest('.chart-container').innerHTML = '<div class="empty-state">No source downtime data available</div>';
        return;
    }

    chartRefs.sourceChart = new Chart(canvas.getContext('2d'), {
        type: 'doughnut',
        data: {
            labels: availableRows.map(row => row.label),
            datasets: [
                {
                    data: availableRows.map(row => row.downtime_hours),
                    backgroundColor: ['#ef4444', '#3b82f6'],
                    borderWidth: 0,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: 'bottom', labels: { usePointStyle: true } },
            },
        },
    });
}

function renderAreaBreakdown(rows, workOrderSource) {
    const container = document.getElementById('area-breakdown');
    const note = document.getElementById('work-order-note');
    if (!container || !note) return;

    if (!rows || !rows.length) {
        container.innerHTML = '<div class="empty-state compact">No area breakdown available</div>';
    } else {
        container.innerHTML = rows.map(row => `
            <div class="reliability-item">
                <span class="rel-name" title="${row.label}">${row.label}</span>
                <div class="rel-bar-wrap">
                    <div class="rel-bar-fill" style="width:${Math.min(row.downtime_hours * 12, 100)}%; background:#3b82f6;"></div>
                </div>
                <span class="rel-score">${fmtHours(row.downtime_hours)}</span>
            </div>
        `).join('');
    }

    note.textContent = workOrderSource?.message || 'Status-derived timing uses imported fault/down tags when available.';
}

function populateFilterOptions(filters) {
    const normalizedSources = [...new Set(getChartEvents().map(event => event.source).filter(Boolean))];
    const map = [
        { id: 'system-filter', values: filters.systems, defaultLabel: 'All Systems' },
        { id: 'area-filter', values: filters.areas, defaultLabel: 'All Areas' },
        { id: 'source-filter', values: normalizedSources.length ? normalizedSources : (filters.sources || []).filter(value => value !== EXCLUDED_SOURCE_LABEL), defaultLabel: 'All Sources' },
    ];

    map.forEach(({ id, values, defaultLabel }) => {
        const select = document.getElementById(id);
        if (!select) return;
        const currentValue = select.value;
        select.innerHTML = `<option value="">${defaultLabel}</option>${(values || []).map(value => `<option value="${value}">${value}</option>`).join('')}`;
        if ([...select.options].some(option => option.value === currentValue)) {
            select.value = currentValue;
        }
    });
}

function populateMonthOptions(months, selectedValue) {
    const select = document.getElementById('month-select');
    if (!select) return;
    const availableMonths = months || [];
    const currentValue = selectedValue || select.value || availableMonths[0]?.value || '';
    select.innerHTML = availableMonths.map(month => `<option value="${month.value}">${month.label}</option>`).join('');
    if ([...select.options].some(option => option.value === currentValue)) {
        select.value = currentValue;
    } else if (select.options.length) {
        select.value = select.options[0].value;
    }
}

function toggleMonthFilter(periodValue) {
    const wrap = document.getElementById('month-filter-wrap');
    if (!wrap) return;
    wrap.style.display = periodValue === 'mtd' ? 'flex' : 'none';
}

function buildMonthOptionsFromDataYear(referenceEndValue) {
    const referenceEnd = referenceEndValue ? new Date(referenceEndValue) : new Date();
    if (Number.isNaN(referenceEnd.getTime())) return [];
    const year = referenceEnd.getFullYear();
    const currentMonth = referenceEnd.getMonth() + 1;
    const values = [];
    for (let month = currentMonth; month >= 1; month -= 1) {
        values.push(`${year}-${String(month).padStart(2, '0')}`);
    }

    return values.map((value) => {
        const dt = new Date(`${value}-01T00:00:00`);
        return {
            value,
            label: dt.toLocaleDateString('en-GB', { month: 'short', year: 'numeric' }),
        };
    });
}

function getFilteredEvents() {
    const events = getChartEvents();
    const systemValue = document.getElementById('system-filter')?.value || '';
    const areaValue = document.getElementById('area-filter')?.value || '';
    const sourceValue = document.getElementById('source-filter')?.value || '';
    const searchValue = (document.getElementById('search-filter')?.value || '').trim().toLowerCase();

    return events.filter(event => {
        if (systemValue && event.system !== systemValue) return false;
        if (areaValue && event.area !== areaValue) return false;
        if (sourceValue && event.source !== sourceValue) return false;
        if (searchValue) {
            const haystack = `${event.machine_code} ${event.machine_name}`.toLowerCase();
            if (!haystack.includes(searchValue)) return false;
        }
        return true;
    });
}

function renderTable() {
    const tbody = document.getElementById('downtime-tbody');
    if (!tbody) return;

    const rows = getFilteredEvents();
    if (!rows.length) {
        const message = 'No status-derived or work-order downtime events match the current filters.';
        tbody.innerHTML = `<tr><td colspan="8" class="empty-cell">${message}</td></tr>`;
        return;
    }

    tbody.innerHTML = rows.map(event => {
        const rowClass = event.is_critical ? 'critical-row' : '';
        return `
            <tr class="${rowClass}">
                <td>${event.system || '--'}</td>
                <td>${event.machine_name || '--'}</td>
                <td>${event.area || '--'}</td>
                <td>${fmtDateTime(event.start_time)}</td>
                <td>${fmtDateTime(event.end_time)}</td>
                <td>${fmtHours(event.duration_hours)}</td>
                <td>${event.source || '--'}</td>
                <td><span class="status-pill ${event.source === 'Work Order' ? 'warning' : 'offline'}">${event.detection_type || '--'}</span></td>
            </tr>
        `;
    }).join('');
}

function wireFilters() {
    ['system-filter', 'area-filter', 'source-filter', 'search-filter'].forEach(id => {
        const el = document.getElementById(id);
        if (!el || el.dataset.bound === 'true') return;
        el.addEventListener(id === 'search-filter' ? 'input' : 'change', renderTable);
        el.dataset.bound = 'true';
    });

    const periodSelect = document.getElementById('period-select');
    if (periodSelect && periodSelect.dataset.bound !== 'true') {
        periodSelect.addEventListener('change', () => {
            toggleMonthFilter(periodSelect.value);
            const monthValue = periodSelect.value === 'mtd' ? (document.getElementById('month-select')?.value || '') : '';
            loadDowntimeData(periodSelect.value, monthValue);
        });
        periodSelect.dataset.bound = 'true';
    }

    const monthSelect = document.getElementById('month-select');
    if (monthSelect && monthSelect.dataset.bound !== 'true') {
        monthSelect.addEventListener('change', () => loadDowntimeData(document.getElementById('period-select')?.value || 'ytd', monthSelect.value));
        monthSelect.dataset.bound = 'true';
    }
}

async function loadDowntimeData(period = 'ytd', month = '') {
    renderAlertBanner([]);
    setText('last-synced', 'Loading downtime data...');
    const requestedMonth = month || '';
    toggleMonthFilter(period);

    await loadDowntimeCacheFile();

    const cachedPayload = getCachedDowntimePayload(period, requestedMonth);
    if (cachedPayload) {
        downtimePayload = cachedPayload;
    } else {
        const query = new URLSearchParams({
            period,
            _: String(Date.now()),
        });
        if (period === 'mtd' && month) query.set('month', month);

        const response = await fetch(`/api/downtime?${query.toString()}`, {
            cache: 'no-store',
        });
        if (!response.ok) throw new Error(`Downtime API failed: ${response.status}`);
        downtimePayload = await response.json();
    }

    const meta = downtimePayload.meta || {};
    const monthOptions = (downtimePayload.months && downtimePayload.months.length)
        ? downtimePayload.months
        : buildMonthOptionsFromDataYear(meta.reference_end || meta.last_synced);
    const fallbackMonth = monthOptions[0]?.value || '';
    const effectiveMonth = meta.month || requestedMonth || fallbackMonth;

    if (period === 'mtd' && !requestedMonth && fallbackMonth) {
        populateMonthOptions(monthOptions, fallbackMonth);
        await loadDowntimeData(period, fallbackMonth);
        return;
    }

    const selectedMonthOption = monthOptions.find(option => option.value === effectiveMonth);
    const periodLabel = selectedMonthOption?.label || (meta.period_label || 'Selected period');
    setText('last-synced', meta.last_synced ? `Last synced ${fmtDateTime(meta.last_synced)}` : 'Last synced unavailable');

    const chartEvents = getChartEvents();
    const summary = buildSummaryFromEvents(chartEvents);
    const trend = buildTrendFromEvents(chartEvents);
    const systemBreakdown = buildGroupedRows(chartEvents, 'system');
    const sourceBreakdown = buildSourceRows(chartEvents).filter(row => row.label !== EXCLUDED_SOURCE_LABEL);
    const assetBreakdown = buildAssetRows(chartEvents);
    const areaBreakdown = buildGroupedRows(chartEvents, 'area');
    const filters = {
        systems: [...new Set(chartEvents.map(event => event.system).filter(Boolean))].sort(),
        areas: [...new Set(chartEvents.map(event => event.area).filter(Boolean))].sort(),
        sources: [...new Set(chartEvents.map(event => event.source).filter(Boolean))].sort(),
    };

    renderAlertBanner(downtimePayload.alerts || []);
    renderKPIs(summary || {});
    setText('kpi-downtime-sub', periodLabel);
    renderTrendChart(trend || {});
    renderSimpleBarChart('systemChart', systemBreakdown || [], 'label', 'downtime_hours', 'rgba(59, 130, 246, 0.75)');
    renderSourceChart(sourceBreakdown || []);
    renderSimpleBarChart('assetChart', assetBreakdown || [], 'machine_name', 'downtime_hours', 'rgba(245, 158, 11, 0.75)');
    renderAreaBreakdown(areaBreakdown || [], downtimePayload.work_order_source || {});
    populateFilterOptions(filters);
    populateMonthOptions(monthOptions, effectiveMonth);
    renderTable();
}

async function init() {
    wireFilters();
    const period = document.getElementById('period-select')?.value || 'ytd';
    toggleMonthFilter(period);
    const month = period === 'mtd' ? (document.getElementById('month-select')?.value || '') : '';
    try {
        await loadDowntimeData(period, month);
    } catch (error) {
        console.error('Downtime page load error:', error);
        setText('last-synced', 'Unable to load downtime data');
        renderAlertBanner([{ level: 'critical', message: 'Downtime data could not be loaded from the current imported sources.' }]);
        renderKPIs({});
    }
}

document.addEventListener('DOMContentLoaded', init);
