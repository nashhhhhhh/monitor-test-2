// =========================
// ROOM ID MAPPING
// =========================
const ROOM_ID_MAP = {};
console.log("✅ ROOM_ID_MAP initialised");

const container = document.getElementById('floorplan-container');

let isLocked = false;
let scale = 1;
let panX = 0;
let panY = 0;

const MIN_SCALE = 1;
const MAX_SCALE = 6;
const ZOOM_SPEED = 0.001;

let latestData = [];

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
  });

/* =========================
   FETCH DATA FROM API
========================= */
async function syncRoomData() {
  try {
    const res = await fetch('/api/temperature/rooms');// relative path
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
      console.error("❌ Missing base_room in API payload:", room);
      return;
    }

    const svgId = ROOM_ID_MAP[room.base_room] || room.base_room;

    let el = document.getElementById(svgId);
    if (!el) {
      console.warn('SVG element not found:', svgId);
      return;
    }

    // 🔥 NEW FIX: find drawable target
    let target = el;

    // If this path has no geometry, colour its next sibling
    if (!el.getAttribute('d')) {
      let sibling = el.nextElementSibling;
      while (sibling && !sibling.getAttribute('d')) {
        sibling = sibling.nextElementSibling;
      }
      if (sibling) target = sibling;
    }

    // Decide colour
    let colour;
    if (room.status === 'CRITICAL') colour = '#ef4444';
    else colour = '#22c55e';

    // Force override ALL styling
    target.removeAttribute('style');
    target.setAttribute('fill', colour);
    target.setAttribute('fill-opacity', '0.45');
    target.setAttribute('stroke', colour);
    target.setAttribute('stroke-width', '2.5');
    target.setAttribute('stroke-opacity', '1');

    // Attach tooltip to label path
    let title = el.querySelector('title');
    if (!title) {
      title = document.createElementNS(
        'http://www.w3.org/2000/svg',
        'title'
      );
      el.appendChild(title);
    }

    title.textContent =
    `${room.room_name ? room.room_name + " (" + room.base_room + ")" : room.base_room}
    Actual: ${room["Actual Temp"].toFixed(2)} °C
    Required: ${room.Requirement.toFixed(2)} °C
    Diff: ${room.temp_diff.toFixed(2)} °C
    Status: ${room.status}`;

    // Mark both elements for filtering
    el.classList.add('room');
    target.classList.add('room');
    target.dataset.status = room.status;
  });
}



/* =========================
   SUMMARY COUNTERS
========================= */
function updateSummary(data) {
  let req = 0, tol = 0, out = 0;

  data.forEach(room => {
    if (room.status === 'OK') req++;
    else if (room.status === 'WARNING') tol++;
    else out++;
  });

  document.getElementById('count-req').textContent = req;
  document.getElementById('count-tol').textContent = tol;
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
  let startX, startY;

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

  window.onmouseup = () => dragging = false;

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

