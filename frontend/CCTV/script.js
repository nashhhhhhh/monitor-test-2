// ── SVG Room → Zone mapping ───────────────────────────────────────
const SVG_ZONE_MAP = {
    // Entry, Corridors, Staff Areas (O: prefix)
    'O:01':'entry','O:02':'entry','O:03':'entry','O:04':'entry','O:05':'entry',
    'O:06':'entry','O:07':'entry','O:08':'entry','O:09':'entry','O:10':'entry','O:11':'entry',

    // Incoming Warehouses & General Storage → storage
    'L:01':'storage','L:02':'storage','L:03':'storage','L:07':'storage',
    'L:08':'storage','L:09':'storage','L:10':'storage','L:11':'storage',
    'L:12':'storage','L:13':'storage','L:34':'storage','L:36':'storage',
    'L:41':'storage','L:49':'storage',

    // Preparation, Defrost, Weigh, Process rooms → prep
    'L:04':'prep','L:05':'prep','L:06':'prep','L:14':'prep','L:20':'prep','L:21':'prep',
    'L:22':'prep','L:23':'prep','L:24':'prep','L:25':'prep','L:26':'prep','L:27':'prep',
    'L:28':'prep','L:29':'prep','L:30':'prep','L:31':'prep','L:32':'prep','L:33':'prep',
    'L:35':'prep','L:37':'prep','L:38':'prep','L:39':'prep','L:40':'prep','L:42':'prep',
    'L:43':'prep','L:44':'prep','L:45':'prep','L:46':'prep','L:47':'prep','L:48':'prep',
    'L:50':'prep','L:51':'prep','L:52':'prep','L:53':'prep','L:54':'prep',

    // Freezers in L: block → utility
    'L:15':'utility','L:16':'utility','L:17':'utility','L:18':'utility','L:19':'utility',

    // High-Risk Kitchen
    'H:01':'highrisk','H:02':'highrisk','H:03':'highrisk',
    'H:11':'highrisk','H:12':'highrisk','H:15':'highrisk',

    // Blast Chillers & Holding Chillers → chilling
    'H:04':'chilling','H:05':'chilling','H:06':'chilling','H:07':'chilling',
    'H:08':'chilling','H:09':'chilling','H:10':'chilling','H:19':'chilling',

    // Assembly, Packing, Label → assembly
    'H:13':'assembly','H:16':'assembly','H:17':'assembly','H:18':'assembly',

    // Air Blast Freezer → utility
    'H:14':'utility',

    // Dispatch / Outgoing (M: prefix) → storage
    'M:01':'storage','M:02':'storage','M:03':'storage','M:04':'storage',
    'M:05':'storage','M:06':'highrisk','M:07':'storage','M:08':'storage',
    'M:09':'storage','M:10':'storage',

    // Utility corridors, EE rooms (U: prefix)
    'U:01':'utility','U:02':'utility','U:03':'utility','U:04':'utility','U:05':'utility',
    'U:06':'utility','U:07':'utility','U:08':'utility','U:09':'utility','U:10':'utility',
    'U:11':'utility','U:12':'utility','U:13':'utility','U:14':'utility','U:15':'utility',
    'U:16':'utility','U:17':'utility','U:18':'utility','U:19':'utility','U:20':'utility',
    'U:21':'utility','U:22':'utility',
};

// ── Zone definitions ──────────────────────────────────────────────
const ZONES = [
    { key: 'storage',  label: 'Cold Storage & Dispatch',  shortLabel: 'Storage',     color: '#0284c7', keywords: ['storage','cold store','dispatch','ship','warehouse','store'] },
    { key: 'prep',     label: 'Preparation (Low-Risk)',   shortLabel: 'Preparation', color: '#16a34a', keywords: ['prep','low risk','low-risk','preparation'] },
    { key: 'highrisk', label: 'Cooking (High-Risk)',      shortLabel: 'High-Risk',   color: '#e11d48', keywords: ['cook','high risk','high-risk','kitchen','hot','steam','oven'] },
    { key: 'utility',  label: 'Utilities & Freezing',     shortLabel: 'Utilities',   color: '#6366f1', keywords: ['util','freez','spiral','boiler','compressor','pump','electrical','mdb','wwtp','wtp','mechanical','plant room'] },
    { key: 'chilling', label: 'Blast Chilling',           shortLabel: 'Chilling',    color: '#3b82f6', keywords: ['chill','blast chill','cool','refriger'] },
    { key: 'assembly', label: 'Assembly & Portioning',    shortLabel: 'Assembly',    color: '#f59e0b', keywords: ['assembl','portion','pack','label','tray','line'] },
    { key: 'entry',    label: 'Stock Intake & Entry',     shortLabel: 'Entry',       color: '#ca8a04', keywords: ['entry','reception','lobby','gate','main','door','entrance','guard','intake','loading bay','change','toilet'] },
    { key: 'external', label: 'External & Car Park',      shortLabel: 'External',    color: '#059669', keywords: ['external','perim','car park','carpark','parking','loading','dock','road','roof','outdoor','outside','fence'] },
    { key: 'other',    label: 'Other Areas',              shortLabel: 'Other',       color: '#475569', keywords: [] },
];

function assignZone(device) {
    const text = `${device.area || ''} ${device.name || ''}`.toLowerCase();
    for (const zone of ZONES.slice(0, -1)) {
        if (zone.keywords.some(kw => text.includes(kw))) return zone.key;
    }
    return 'other';
}

// ── State ─────────────────────────────────────────────────────────
let allDevices   = [];
let activeZone   = null;
let statusFilter = 'all';
let searchQuery  = '';

// ── Floorplan pan/zoom state ──────────────────────────────────────
let fpScale = 1, fpPanX = 0, fpPanY = 0, fpDragging = false, fpSX = 0, fpSY = 0;
let floorplanLoaded = false;
let fpViewport = null;

// ── Init ──────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.filter-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            statusFilter = btn.dataset.filter;
            render();
        });
    });

    document.getElementById('camera-search').addEventListener('input', e => {
        searchQuery = e.target.value.trim().toLowerCase();
        render();
    });

    document.getElementById('active-zone-tag').addEventListener('click', () => {
        clearActiveZone();
    });

    loadFloorplan();
    fetchData();
    setInterval(fetchData, 30000);
});

// ── Fetch ─────────────────────────────────────────────────────────
async function fetchData() {
    try {
        const res = await fetch('/api/cctv/log');
        if (!res.ok) throw new Error(res.status);
        allDevices = await res.json();

        allDevices.sort((a, b) => {
            const aOff = a.status.toLowerCase() === 'offline';
            const bOff = b.status.toLowerCase() === 'offline';
            if (aOff !== bOff) return aOff ? -1 : 1;
            return a.name.localeCompare(b.name);
        });

        updateKPIs();
        applyZonesToSVG();
        render();
    } catch (err) {
        console.error('CCTV fetch error:', err);
    }
}

// ── KPIs ──────────────────────────────────────────────────────────
function updateKPIs() {
    let online = 0, offline = 0;
    allDevices.forEach(d => { if (d.status.toLowerCase() === 'online') online++; else offline++; });
    document.getElementById('onlineCount').textContent  = online;
    document.getElementById('offlineCount').textContent = offline;
    document.getElementById('totalCount').textContent   = allDevices.length;
}

// ── Floorplan ─────────────────────────────────────────────────────
function loadFloorplan() {
    if (floorplanLoaded) return;
    const wrap = document.getElementById('floorplan-container');

    fetch('/Temperature/assets/floorplan.svg')
        .then(r => r.text())
        .then(svgText => {
            wrap.innerHTML = svgText;
            const svgEl = wrap.querySelector('svg');
            if (!svgEl) return;

            // Remove hard-coded pixel dimensions so CSS width:100%/height:auto applies
            svgEl.removeAttribute('width');
            svgEl.removeAttribute('height');

            // Wrap all content in a single group for pan/zoom transforms
            const inner = svgEl.innerHTML;
            svgEl.innerHTML = `<g id="fp-viewport">${inner}</g>`;
            fpViewport = document.getElementById('fp-viewport');

            // CSS width:100%/height:auto already fits the SVG — no JS scaling needed
            fpScale = 1;
            fpPanX  = 0;
            fpPanY  = 0;
            updateFpTransform();

            floorplanLoaded = true;

            // Helper: convert CSS-pixel position (relative to SVG element) → SVG-unit coords
            function toSvgCoords(cssX, cssY) {
                const r  = svgEl.getBoundingClientRect();
                const vb = svgEl.viewBox.baseVal;
                return {
                    x: cssX * (vb.width  / r.width),
                    y: cssY * (vb.height / r.height),
                };
            }

            // ── Zoom toward cursor ──
            svgEl.addEventListener('wheel', e => {
                e.preventDefault();
                const rect  = svgEl.getBoundingClientRect();
                const { x: mx, y: my } = toSvgCoords(e.clientX - rect.left, e.clientY - rect.top);
                const prev  = fpScale;
                fpScale     = Math.min(12, Math.max(0.25, fpScale * (1 - e.deltaY * 0.001)));
                const ratio = fpScale / prev;
                fpPanX = mx - ratio * (mx - fpPanX);
                fpPanY = my - ratio * (my - fpPanY);
                updateFpTransform();
            }, { passive: false });

            // ── Drag to pan ──
            svgEl.addEventListener('mousedown', e => {
                fpDragging = true;
                const { x, y } = toSvgCoords(e.clientX, e.clientY);
                fpSX = x - fpPanX;
                fpSY = y - fpPanY;
                e.preventDefault();
            });
            window.addEventListener('mousemove', e => {
                if (!fpDragging) return;
                const { x, y } = toSvgCoords(e.clientX, e.clientY);
                fpPanX = x - fpSX;
                fpPanY = y - fpSY;
                updateFpTransform();
            });
            window.addEventListener('mouseup', () => { fpDragging = false; });

            // ── Room click → zone filter ──
            Object.keys(SVG_ZONE_MAP).forEach(svgId => {
                const el = document.getElementById(svgId);
                if (!el) return;
                el.style.cursor = 'pointer';
                el.addEventListener('click', e => {
                    e.stopPropagation();
                    const zone = SVG_ZONE_MAP[svgId];
                    activeZone = activeZone === zone ? null : zone;
                    updateActiveZoneTag();
                    applyZonesToSVG();
                    render();
                });
            });

            // Click background → clear filter
            svgEl.addEventListener('click', () => { if (activeZone) clearActiveZone(); });

            if (allDevices.length > 0) applyZonesToSVG();
        })
        .catch(err => {
            document.getElementById('floorplan-container').innerHTML =
                `<div class="fp-loading" style="color:#ef4444">Floor plan failed to load</div>`;
            console.error('Floorplan error:', err);
        });
}

function updateFpTransform() {
    if (fpViewport) fpViewport.setAttribute('transform', `translate(${fpPanX},${fpPanY}) scale(${fpScale})`);
}

// ── Apply zone colours to SVG ─────────────────────────────────────
function applyZonesToSVG() {
    if (!floorplanLoaded) return;

    // Build zone health stats
    const health = {};
    ZONES.forEach(z => health[z.key] = { total: 0, online: 0 });
    allDevices.forEach(d => {
        const zk = assignZone(d);
        if (health[zk]) { health[zk].total++; if (d.status.toLowerCase() === 'online') health[zk].online++; }
    });

    // Colour each room by ZONE IDENTITY (not health), collect bounding boxes
    const zoneBounds = {};
    ZONES.forEach(z => zoneBounds[z.key] = { minX: Infinity, maxX: -Infinity, minY: Infinity, maxY: -Infinity });

    Object.entries(SVG_ZONE_MAP).forEach(([svgId, zoneKey]) => {
        const el = document.getElementById(svgId);
        if (!el) return;

        let target = el;
        if (!el.getAttribute('d')) {
            const child = el.querySelector('path');
            if (child) target = child;
        }

        const zone     = ZONES.find(z => z.key === zoneKey);
        const zoneColor = zone?.color || '#475569';
        const isActive  = activeZone === zoneKey;
        // Zone identity fill — dimmed when another zone is active
        const opacity   = activeZone && !isActive ? 0.12 : isActive ? 0.65 : 0.42;
        const strokeW   = isActive ? 2.5 : 1;
        const strokeOp  = activeZone && !isActive ? 0.2 : isActive ? 1 : 0.6;

        target.removeAttribute('style');
        target.setAttribute('fill',          zoneColor);
        target.setAttribute('fill-opacity',  String(opacity));
        target.setAttribute('stroke',        isActive ? '#ffffff' : zoneColor);
        target.setAttribute('stroke-width',  String(strokeW));
        target.setAttribute('stroke-opacity',String(strokeOp));
        target.classList.add('fp-room');

        // Tooltip
        let title = el.querySelector('title');
        if (!title) { title = document.createElementNS('http://www.w3.org/2000/svg', 'title'); el.appendChild(title); }
        const g      = health[zoneKey] || { total: 0, online: 0 };
        const pctStr = g.total > 0 ? `${Math.round((g.online / g.total) * 100)}% online` : 'No camera data';
        title.textContent = `${zone?.label || zoneKey}\n${g.online}/${g.total} cameras (${pctStr})\nClick to filter`;

        // Accumulate bounding box for label placement
        try {
            const bbox = el.getBBox();
            const b = zoneBounds[zoneKey];
            b.minX = Math.min(b.minX, bbox.x);
            b.maxX = Math.max(b.maxX, bbox.x + bbox.width);
            b.minY = Math.min(b.minY, bbox.y);
            b.maxY = Math.max(b.maxY, bbox.y + bbox.height);
        } catch (_) {}
    });

    injectZoneLabels(health, zoneBounds);
}

// Zone step numbers (matching production process flow)
const ZONE_STEPS = {
    entry: 'Stage 01', prep: 'Stage 02', highrisk: 'Stage 03 CCP',
    chilling: 'Stage 04', assembly: 'Stage 05 CCP', utility: 'Stage 06',
    storage: 'Stage 07', external: 'Perimeter', other: '',
};

// ── Inject zone labels into the SVG ──────────────────────────────
function injectZoneLabels(health, zoneBounds) {
    const viewport = fpViewport || document.getElementById('fp-viewport');
    if (!viewport) return;

    const old = viewport.querySelector('#cctv-zone-labels');
    if (old) old.remove();

    const labelGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    labelGroup.id = 'cctv-zone-labels';

    const svgEl = document.querySelector('#floorplan-container svg');
    const vb    = svgEl?.viewBox?.baseVal;
    const unit  = vb && vb.width > 0 ? vb.width / 120 : 10;

    ZONES.forEach(zone => {
        const b = zoneBounds[zone.key];
        if (!b || b.minX === Infinity) return;

        const g        = health[zone.key] || { total: 0, online: 0 };
        const cx       = (b.minX + b.maxX) / 2;
        const cy       = (b.minY + b.maxY) / 2;
        const isActive = activeZone === zone.key;
        const dimmed   = activeZone && !isActive;
        if (dimmed) return; // hide labels for non-active zones when one is selected

        const pct = g.total > 0 ? Math.round((g.online / g.total) * 100) : null;
        if (pct === null) return; // skip zones with no cameras assigned yet

        const healthColor = pct >= 95 ? '#22c55e' : pct >= 80 ? '#f59e0b' : '#ef4444';
        const step        = ZONE_STEPS[zone.key] || '';
        const countLine   = `${g.online}/${g.total} · ${pct}%`;

        const rectW = unit * 16;
        const rectH = unit * (step ? 8.5 : 6.5);
        const g_el  = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        g_el.style.pointerEvents = 'none';

        // Drop shadow rect
        const shadow = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        shadow.setAttribute('x',            cx - rectW / 2 + unit * 0.4);
        shadow.setAttribute('y',            cy - rectH / 2 + unit * 0.4);
        shadow.setAttribute('width',        rectW);
        shadow.setAttribute('height',       rectH);
        shadow.setAttribute('rx',           unit * 1.5);
        shadow.setAttribute('fill',         '#000000');
        shadow.setAttribute('fill-opacity', '0.35');
        g_el.appendChild(shadow);

        // Main background
        const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        rect.setAttribute('x',            cx - rectW / 2);
        rect.setAttribute('y',            cy - rectH / 2);
        rect.setAttribute('width',        rectW);
        rect.setAttribute('height',       rectH);
        rect.setAttribute('rx',           unit * 1.5);
        rect.setAttribute('fill',         isActive ? '#0f2744' : '#0b1527');
        rect.setAttribute('fill-opacity', '0.92');
        rect.setAttribute('stroke',       isActive ? '#ffffff' : zone.color);
        rect.setAttribute('stroke-width', unit * (isActive ? 0.55 : 0.3));
        g_el.appendChild(rect);

        // Left colour bar
        const bar = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        bar.setAttribute('x',            cx - rectW / 2);
        bar.setAttribute('y',            cy - rectH / 2);
        bar.setAttribute('width',        unit * 1.2);
        bar.setAttribute('height',       rectH);
        bar.setAttribute('rx',           unit * 1.5);
        bar.setAttribute('fill',         zone.color);
        bar.setAttribute('fill-opacity', '0.9');
        g_el.appendChild(bar);

        const textX = cx - rectW / 2 + unit * 2.4;
        let yOffset = cy - rectH / 2 + unit * 2.8;

        // Step label (e.g. "Stage 03 CCP")
        if (step) {
            const tStep = document.createElementNS('http://www.w3.org/2000/svg', 'text');
            tStep.setAttribute('x',           textX);
            tStep.setAttribute('y',           yOffset);
            tStep.setAttribute('fill',        zone.color);
            tStep.setAttribute('font-size',   unit * 1.7);
            tStep.setAttribute('font-weight', '700');
            tStep.setAttribute('letter-spacing', unit * 0.15);
            tStep.textContent = step.toUpperCase();
            g_el.appendChild(tStep);
            yOffset += unit * 2.5;
        }

        // Zone short label
        const tName = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        tName.setAttribute('x',           textX);
        tName.setAttribute('y',           yOffset);
        tName.setAttribute('fill',        '#f1f5f9');
        tName.setAttribute('font-size',   unit * 2.2);
        tName.setAttribute('font-weight', '700');
        tName.textContent = zone.shortLabel;
        g_el.appendChild(tName);
        yOffset += unit * 2.5;

        // Health dot + count
        const dotR = unit * 0.85;
        const dotCy = yOffset - unit * 0.9;
        const dot = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        dot.setAttribute('cx',   textX + dotR);
        dot.setAttribute('cy',   dotCy);
        dot.setAttribute('r',    dotR);
        dot.setAttribute('fill', healthColor);
        g_el.appendChild(dot);

        const tCount = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        tCount.setAttribute('x',           textX + dotR * 2 + unit * 0.6);
        tCount.setAttribute('y',           yOffset);
        tCount.setAttribute('fill',        healthColor);
        tCount.setAttribute('font-size',   unit * 1.9);
        tCount.setAttribute('font-weight', '600');
        tCount.textContent = countLine;
        g_el.appendChild(tCount);

        labelGroup.appendChild(g_el);
    });

    viewport.appendChild(labelGroup);
}

// ── Active zone helpers ───────────────────────────────────────────
function clearActiveZone() {
    activeZone = null;
    updateActiveZoneTag();
    applyZonesToSVG();
    render();
}

function updateActiveZoneTag() {
    const tag = document.getElementById('active-zone-tag');
    if (activeZone) {
        const zone = ZONES.find(z => z.key === activeZone);
        tag.textContent = `📍 ${zone?.label || activeZone}  ✕`;
        tag.style.display = 'inline-flex';
    } else {
        tag.style.display = 'none';
    }
}

// ── Render camera sections ────────────────────────────────────────
function render() {
    let devices = allDevices;
    if (activeZone)             devices = devices.filter(d => assignZone(d) === activeZone);
    if (statusFilter !== 'all') devices = devices.filter(d => d.status.toLowerCase() === statusFilter);
    if (searchQuery)            devices = devices.filter(d =>
        d.name.toLowerCase().includes(searchQuery) ||
        (d.area || '').toLowerCase().includes(searchQuery)
    );

    const grouped = {};
    ZONES.forEach(z => grouped[z.key] = []);
    devices.forEach(d => grouped[assignZone(d)].push(d));

    const container = document.getElementById('zone-sections');
    if (devices.length === 0) {
        container.innerHTML = '<div class="status-msg">No cameras match the current filters.</div>';
        return;
    }

    container.innerHTML = ZONES
        .filter(z => grouped[z.key].length > 0)
        .map(zone => {
            const cams    = grouped[zone.key];
            const onCount  = cams.filter(d => d.status.toLowerCase() === 'online').length;
            const offCount = cams.length - onCount;
            return `
            <div class="zone-section" id="section-${zone.key}">
                <div class="zone-section-header" onclick="toggleSection('${zone.key}')">
                    <div class="zone-section-header-left">
                        <div class="zone-dot-lg" style="background:${zone.color}"></div>
                        <span class="zone-section-name">${escapeHTML(zone.label)}</span>
                        <span class="badge-total">${cams.length}</span>
                        ${onCount  > 0 ? `<span class="badge-on">${onCount} online</span>`   : ''}
                        ${offCount > 0 ? `<span class="badge-off">${offCount} offline</span>` : ''}
                    </div>
                    <span class="section-toggle">▾</span>
                </div>
                <div class="zone-section-body">
                    <div class="camera-grid">
                        ${cams.map(d => renderCamCard(d)).join('')}
                    </div>
                </div>
            </div>`;
        }).join('');
}

function renderCamCard(dev) {
    const online  = dev.status.toLowerCase() === 'online';
    const area    = dev.area    && dev.area    !== 'nan' ? escapeHTML(dev.area)    : null;
    const address = dev.address && dev.address !== 'nan' ? escapeHTML(dev.address) : null;
    return `
        <div class="cam-card ${online ? '' : 'offline-card'}">
            <div class="cam-header">
                <span class="status-indicator ${online ? 'online' : 'offline'}"></span>
                <h3>${escapeHTML(dev.name)}</h3>
            </div>
            <div class="status-label ${online ? 'status-online' : 'status-offline'}">${dev.status.toUpperCase()}</div>
            ${area    ? `<div class="cam-meta">📍 ${area}</div>` : ''}
            ${address ? `<div class="cam-address">${address}</div>` : ''}
            <div class="cam-meta">Last offline: ${dev.lastOffline && dev.lastOffline !== 'nan' ? escapeHTML(dev.lastOffline) : '—'}</div>
            <div class="cam-meta">Offline count: ${dev.offlineCount && dev.offlineCount !== 'nan' ? escapeHTML(dev.offlineCount) : '0'}</div>
            <div class="cam-meta">Duration: ${dev.offlineDuration && dev.offlineDuration !== 'nan' ? escapeHTML(dev.offlineDuration) : '—'}</div>
        </div>`;
}

// ── Helpers ───────────────────────────────────────────────────────
function toggleSection(key) {
    document.getElementById(`section-${key}`)?.classList.toggle('collapsed');
}

function escapeHTML(str) {
    return String(str).replace(/[&<>"']/g, m =>
        ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[m]);
}
