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
    { key: 'entry',    label: 'Stock Intake & Entry',      color: '#ca8a04', keywords: ['entry','reception','lobby','gate','main','door','entrance','guard','intake','loading bay','change','toilet'] },
    { key: 'prep',     label: 'Preparation (Low-Risk)',    color: '#16a34a', keywords: ['prep','low risk','low-risk','preparation'] },
    { key: 'highrisk', label: 'Cooking (High-Risk)',       color: '#e11d48', keywords: ['cook','high risk','high-risk','kitchen','hot','steam','oven'] },
    { key: 'chilling', label: 'Blast Chilling',            color: '#3b82f6', keywords: ['chill','blast chill','cool','refriger'] },
    { key: 'assembly', label: 'Assembly & Portioning',     color: '#f59e0b', keywords: ['assembl','portion','pack','label','tray','line'] },
    { key: 'utility',  label: 'Utilities & Freezing',      color: '#6366f1', keywords: ['util','freez','spiral','boiler','compressor','pump','electrical','mdb','wwtp','wtp','mechanical','plant room'] },
    { key: 'storage',  label: 'Cold Storage & Dispatch',   color: '#0284c7', keywords: ['storage','cold store','dispatch','ship','warehouse','store'] },
    { key: 'external', label: 'External & Car Park',       color: '#059669', keywords: ['external','perim','car park','carpark','parking','loading','dock','road','roof','outdoor','outside','fence'] },
    { key: 'other',    label: 'Other Areas',               color: '#475569', keywords: [] },
];

function assignZone(device) {
    const text = `${device.area || ''} ${device.name || ''}`.toLowerCase();
    for (const zone of ZONES.slice(0, -1)) {
        if (zone.keywords.some(kw => text.includes(kw))) return zone.key;
    }
    return 'other';
}

// ── State ─────────────────────────────────────────────────────────
let allDevices = [];
let activeFilter = 'all';
let searchQuery  = '';

// ── Pan/zoom (mirrors Temperature page) ───────────────────────────
let scale = 1, panX = 0, panY = 0;
let isLocked = false;
const MIN_SCALE = 0.3, MAX_SCALE = 8, ZOOM_SPEED = 0.001;

// ── Init ──────────────────────────────────────────────────────────
const container = document.getElementById('floorplan-container');

document.getElementById('camera-search').addEventListener('input', e => {
    searchQuery = e.target.value.trim().toLowerCase();
    render();
});

document.getElementById('lockBtn').addEventListener('click', () => {
    isLocked = !isLocked;
    document.getElementById('lockBtn').textContent = isLocked ? 'Unlock Layout' : 'Lock Layout';
    document.getElementById('floorplan-container').style.cursor = isLocked ? 'default' : 'grab';
});

// Load SVG exactly like Temperature page
fetch('/Temperature/assets/floorplan.svg')
    .then(res => res.text())
    .then(svg => {
        container.innerHTML = svg;
        initPanZoom();
        fitToWidth();
        fetchData();
        setInterval(fetchData, 30000);
    })
    .catch(() => {
        container.innerHTML = '<div class="fp-loading" style="color:#ef4444">Floor plan failed to load</div>';
    });

// ── Fetch camera data ─────────────────────────────────────────────
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

// ── Apply colours to SVG rooms (mirrors Temperature applyDataToSVG) ──
function applyZonesToSVG() {
    // Build zone health stats
    const health = {};
    ZONES.forEach(z => health[z.key] = { total: 0, online: 0 });
    allDevices.forEach(d => {
        const zk = assignZone(d);
        if (health[zk]) {
            health[zk].total++;
            if (d.status.toLowerCase() === 'online') health[zk].online++;
        }
    });

    Object.entries(SVG_ZONE_MAP).forEach(([svgId, zoneKey]) => {
        const el = document.getElementById(svgId);
        if (!el) return;

        // Find the drawable path element (same logic as Temperature)
        let target = el;
        if (!el.getAttribute('d')) {
            const child = el.querySelector('path');
            if (child) target = child;
        }

        const g   = health[zoneKey] || { total: 0, online: 0 };
        let colour = '#475569'; // grey = no camera data
        let roomStatus = 'none';
        if (g.total > 0) {
            const pct = g.online / g.total;
            if (pct >= 1)   { colour = '#22c55e'; roomStatus = 'online';  }
            else if (pct >= 0.8) { colour = '#f59e0b'; roomStatus = 'offline'; }
            else            { colour = '#ef4444'; roomStatus = 'offline'; }
        }

        target.removeAttribute('style');
        target.setAttribute('fill',          colour);
        target.setAttribute('fill-opacity',  '0.45');
        target.setAttribute('stroke',        colour);
        target.setAttribute('stroke-width',  '2.5');
        target.setAttribute('stroke-opacity','1');
        target.classList.add('room');
        target.dataset.status = roomStatus;

        el.classList.add('room');

        // Tooltip
        let title = el.querySelector('title');
        if (!title) {
            title = document.createElementNS('http://www.w3.org/2000/svg', 'title');
            el.appendChild(title);
        }
        const zoneName = ZONES.find(z => z.key === zoneKey)?.label || zoneKey;
        const pctStr   = g.total > 0 ? `${Math.round((g.online / g.total) * 100)}% online` : 'No camera data';
        title.textContent = `${zoneName}\n${g.online}/${g.total} cameras (${pctStr})`;
    });
}

// ── Filter rooms on SVG (mirrors Temperature filterRooms) ─────────
function filterRooms(type) {
    activeFilter = type;

    // Update button active state
    ['all', 'online', 'offline'].forEach(t => {
        document.getElementById(`btn-${t}`)?.classList.toggle('active', t === type);
    });

    document.querySelectorAll('#floorplan-container .room').forEach(room => {
        const status = room.dataset.status;
        if (type === 'all') {
            room.style.opacity = '';
        } else if (type === 'online' && status === 'online') {
            room.style.opacity = '';
        } else if (type === 'offline' && status === 'offline') {
            room.style.opacity = '';
        } else if (type !== 'all') {
            room.style.opacity = '0.12';
        }
    });

    render();
}

// ── Pan & zoom (mirrors Temperature initPanZoom) ───────────────────
function initPanZoom() {
    const svg = container.querySelector('svg');
    if (!svg) return;

    let viewport = document.getElementById('viewport');
    if (!viewport) {
        svg.innerHTML = `<g id="viewport">${svg.innerHTML}</g>`;
        viewport = document.getElementById('viewport');
    }

    svg.addEventListener('wheel', e => {
        if (isLocked) return;
        e.preventDefault();
        const delta = -e.deltaY * ZOOM_SPEED;
        scale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, scale + delta));
        updateTransform(viewport);
    }, { passive: false });

    let dragging = false, startX, startY;

    svg.addEventListener('mousedown', e => {
        if (isLocked) return;
        dragging = true;
        startX = e.clientX - panX;
        startY = e.clientY - panY;
    });
    window.addEventListener('mousemove', e => {
        if (!dragging || isLocked) return;
        panX = e.clientX - startX;
        panY = e.clientY - startY;
        updateTransform(viewport);
    });
    window.addEventListener('mouseup', () => { dragging = false; });
}

function updateTransform(viewport) {
    if (viewport) viewport.setAttribute('transform', `translate(${panX},${panY}) scale(${scale})`);
}

// ── Fit SVG to container width (mirrors Temperature fitToWidth) ───
function fitToWidth() {
    const svg = container.querySelector('svg');
    if (!svg) return;
    const viewBox = svg.viewBox.baseVal;
    if (!viewBox || viewBox.width === 0) return;

    scale = container.clientWidth / viewBox.width;
    panX  = 0;
    panY  = 0;

    const viewport = document.getElementById('viewport');
    if (viewport) viewport.setAttribute('transform', `translate(0,0) scale(${scale})`);
}

// ── Render camera list grouped by zone ────────────────────────────
function render() {
    let devices = allDevices;
    if (activeFilter === 'online')  devices = devices.filter(d => d.status.toLowerCase() === 'online');
    if (activeFilter === 'offline') devices = devices.filter(d => d.status.toLowerCase() === 'offline');
    if (searchQuery) devices = devices.filter(d =>
        d.name.toLowerCase().includes(searchQuery) ||
        (d.area || '').toLowerCase().includes(searchQuery)
    );

    const grouped = {};
    ZONES.forEach(z => grouped[z.key] = []);
    devices.forEach(d => grouped[assignZone(d)].push(d));

    const sectionsEl = document.getElementById('zone-sections');
    if (devices.length === 0) {
        sectionsEl.innerHTML = '<div class="status-msg">No cameras match the current filters.</div>';
        return;
    }

    sectionsEl.innerHTML = ZONES
        .filter(z => grouped[z.key].length > 0)
        .map(zone => {
            const cams     = grouped[zone.key];
            const onCount  = cams.filter(d => d.status.toLowerCase() === 'online').length;
            const offCount = cams.length - onCount;
            return `
            <div class="zone-section" id="section-${zone.key}">
                <div class="zone-section-header" onclick="toggleSection('${zone.key}')">
                    <div class="zone-header-left">
                        <div class="zone-dot" style="background:${zone.color}"></div>
                        <span class="zone-name">${escapeHTML(zone.label)}</span>
                        <span class="badge-total">${cams.length}</span>
                        ${onCount  > 0 ? `<span class="badge-on">${onCount} online</span>`   : ''}
                        ${offCount > 0 ? `<span class="badge-off">${offCount} offline</span>` : ''}
                    </div>
                    <span class="toggle-icon">▾</span>
                </div>
                <div class="zone-body">
                    <div class="camera-grid">
                        ${cams.map(renderCamCard).join('')}
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
                <span class="status-dot ${online ? 'online' : 'offline'}"></span>
                <h3>${escapeHTML(dev.name)}</h3>
            </div>
            <div class="status-label ${online ? 'status-online' : 'status-offline'}">${dev.status.toUpperCase()}</div>
            ${area    ? `<div class="cam-meta">📍 ${area}</div>` : ''}
            ${address ? `<div class="cam-address">${address}</div>` : ''}
            <div class="cam-meta">Last offline: ${dev.lastOffline && dev.lastOffline !== 'nan' ? escapeHTML(dev.lastOffline) : '—'}</div>
            <div class="cam-meta">Offline count: ${dev.offlineCount && dev.offlineCount !== 'nan' ? escapeHTML(String(dev.offlineCount)) : '0'}</div>
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
