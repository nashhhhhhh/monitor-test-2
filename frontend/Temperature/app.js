// =========================
// ROOM ID MAPPING
// =========================
const ROOM_ID_MAP = {};
console.log("ROOM_ID_MAP initialised");

const container = document.getElementById('floorplan-container');

let isLocked = false;
let scale = 1;
let panX = 0;
let panY = 0;

const MIN_SCALE = 1;
const MAX_SCALE = 6;
const ZOOM_SPEED = 0.001;

let latestData = [];

function toNumber(value, fallback = null) {
  const num = Number(value);
  return Number.isFinite(num) ? num : fallback;
}

function formatNumber(value, digits = 2, fallback = "N/A") {
  const num = toNumber(value);
  return num === null ? fallback : num.toFixed(digits);
}

function buildExpectedRangeText(range) {
  if (!range || !range.configured) return null;
  if (range.label) {
    return `Configured Threshold: ${range.label}`;
  }
  if (range.min_normal === null || range.min_normal === undefined) {
    return `Configured Threshold: <= ${formatNumber(range.max_normal)} deg C`;
  }
  if (range.max_normal === null || range.max_normal === undefined) {
    return `Configured Threshold: >= ${formatNumber(range.min_normal)} deg C`;
  }
  const min = formatNumber(range.min_normal);
  const max = formatNumber(range.max_normal);
  return min === max
    ? `Configured Threshold: ${min} deg C`
    : `Configured Threshold: ${min} to ${max} deg C`;
}

function buildThresholdDeviationText(room) {
  const range = room?.expected_range;
  const actual = toNumber(room?.["Actual Temp"]);
  if (!range?.configured || actual === null) return null;

  const min = toNumber(range.min_normal);
  const max = toNumber(range.max_normal);

  if (min !== null && actual < min) {
    return `Deviation vs Threshold: -${formatNumber(min - actual)} deg C`;
  }
  if (max !== null && actual > max) {
    return `Deviation vs Threshold: +${formatNumber(actual - max)} deg C`;
  }
  return `Deviation vs Threshold: 0.00 deg C`;
}

function buildEnergyTooltipLines(energy, insight) {
  if (!energy || !energy.mapped) return [];
  if (!energy.available) {
    return [
      `Energy: ${energy.label || energy.source_key || "Mapped source"} unavailable`,
      `Energy Status: ${energy.status || "UNAVAILABLE"}`
    ];
  }

  const lines = [
    `Energy: ${formatNumber(energy.latest_value, 3)} ${energy.unit || "kWh"}`,
    `Energy Status: ${energy.status || "NORMAL"}`
  ];
  if (energy.baseline !== null && energy.baseline !== undefined) {
    lines.push(`Energy Baseline: ${formatNumber(energy.baseline, 3)} ${energy.unit || "kWh"}`);
  }
  if (insight) lines.push(`Insight: ${insight}`);
  return lines;
}

/* =========================
   LOAD SVG (INLINE)
========================= */
fetch('/Temperature/assets/floorplan.svg')
  .then(res => res.text())
  .then(svg => {
    container.innerHTML = svg;
    initControls();
    initPanZoom();
    syncRoomData();
    fitToWidth();
  })
  .catch(err => {
    console.error('Floorplan load error:', err);
  });

/* =========================
   FETCH DATA FROM API
========================= */
async function syncRoomData() {
  try {
    const res = await fetch('/api/temperature/rooms');
    latestData = await res.json();

    updateSummary(latestData);
    applyDataToSVG(latestData);
  } catch (err) {
    console.error('API Sync Error:', err);
  }
}

/* =========================
   APPLY DATA TO SVG
========================= */
function applyDataToSVG(data) {
  data.forEach(room => {
    if (!room.base_room) {
      console.error('Missing base_room in API payload:', room);
      return;
    }

    const svgId = ROOM_ID_MAP[room.base_room] || room.base_room;

    const el = document.getElementById(svgId);
    if (!el) {
      console.warn('SVG element not found:', svgId);
      return;
    }

    let target = el;

    if (!el.getAttribute('d')) {
      let sibling = el.nextElementSibling;
      while (sibling && !sibling.getAttribute('d')) {
        sibling = sibling.nextElementSibling;
      }
      if (sibling) target = sibling;
    }

    let colour = '#94a3b8';
    if (room.status === 'CRITICAL') colour = '#ef4444';
    else if (room.status === 'WARNING') colour = '#f59e0b';
    else if (room.status === 'OK') colour = '#22c55e';

    target.removeAttribute('style');
    target.setAttribute('fill', colour);
    target.setAttribute('fill-opacity', '0.45');
    target.setAttribute('stroke', colour);
    target.setAttribute('stroke-width', '2.5');
    target.setAttribute('stroke-opacity', '1');

    let title = el.querySelector('title');
    if (!title) {
      title = document.createElementNS(
        'http://www.w3.org/2000/svg',
        'title'
      );
      el.appendChild(title);
    }

    const tooltipLines = [
      room.room_name ? `${room.room_name} (${room.base_room})` : room.base_room,
      `Actual: ${formatNumber(room["Actual Temp"])} deg C`,
      `Status: ${room.status || 'UNKNOWN'}`
    ];
    const expectedRangeText = buildExpectedRangeText(room.expected_range);
    if (expectedRangeText) tooltipLines.push(expectedRangeText);
    const thresholdDeviationText = buildThresholdDeviationText(room);
    if (thresholdDeviationText) tooltipLines.push(thresholdDeviationText);
    if (room.expected_range?.area_group) tooltipLines.push(`Area: ${room.expected_range.area_group}`);
    tooltipLines.push(...buildEnergyTooltipLines(room.energy, room.combined_insight));
    title.textContent = tooltipLines.join('\n');

    el.classList.add('room');
    target.classList.add('room');
    target.dataset.status = room.status || 'UNKNOWN';
  });
}

/* =========================
   SUMMARY COUNTERS
========================= */
function updateSummary(data) {
  let req = 0;
  let out = 0;

  data.forEach(room => {
    if (room.status === 'OK') req++;
    else out++;
  });

  document.getElementById('count-req').textContent = req;
  document.getElementById('count-out').textContent = out;
}

/* =========================
   FILTER ROOMS
========================= */
function filterRooms(type) {
  document.querySelectorAll('.room').forEach(room => {
    const status = room.dataset.status;

    if (type === 'all') room.style.display = '';
    else if (type === 'req' && status === 'OK') room.style.display = '';
    else if (type === 'tol' && status === 'WARNING') room.style.display = '';
    else if (type === 'out' && status === 'CRITICAL') room.style.display = '';
    else room.style.display = 'none';
  });
}

/* =========================
   UI CONTROLS
========================= */
function initControls() {
  const lockBtn = document.getElementById('lockBtn');
  lockBtn.onclick = () => {
    isLocked = !isLocked;
    lockBtn.textContent = isLocked ? ' Layout Locked' : ' Unlock Layout';
  };
}

/* =========================
   PAN & ZOOM
========================= */
function initPanZoom() {
  const svg = document.querySelector('#floorplan-container svg');
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
    updateTransform();
  }, { passive: false });

  let dragging = false;
  let startX;
  let startY;

  svg.onmousedown = e => {
    if (isLocked) return;
    dragging = true;
    startX = e.clientX - panX;
    startY = e.clientY - panY;
  };

  window.onmousemove = e => {
    if (!dragging || isLocked) return;
    panX = e.clientX - startX;
    panY = e.clientY - startY;
    updateTransform();
  };

  window.onmouseup = () => {
    dragging = false;
  };

  function updateTransform() {
    viewport.setAttribute(
      'transform',
      `translate(${panX},${panY}) scale(${scale})`
    );
  }
}

/* =========================
   FIT SVG TO CONTAINER
========================= */
function fitToWidth() {
  const svg = document.querySelector('#floorplan-container svg');
  if (!svg) return;

  const viewBox = svg.viewBox.baseVal;
  if (!viewBox || viewBox.width === 0) return;

  const containerWidth = document.getElementById('floorplan-container').clientWidth;
  scale = containerWidth / viewBox.width;
  panX = 0;
  panY = 0;

  const viewport = document.getElementById('viewport');
  if (viewport) {
    viewport.setAttribute(
      'transform',
      `translate(${panX},${panY}) scale(${scale})`
    );
  }
}
