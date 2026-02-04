async function loadTemperatureSummary() {
  try {
    const res = await fetch('/api/temperature/rooms');
    const data = await res.json();

    let ok = 0, warning = 0, critical = 0;

    data.forEach(room => {
      if (room.status === 'OK') ok++;
      else if (room.status === 'WARNING') warning++;
      else critical++;
    });

    document.getElementById('temp-ok').textContent = ok;
    document.getElementById('temp-warning').textContent = warning;
    document.getElementById('temp-critical').textContent = critical;

  } catch (err) {
    console.error('Overview API error:', err);
  }
}
/* =========================
   FIT TO WIDTH
========================= */
function fitToWidth() {
  scale = 1;
  panX = 0;
  panY = 0;
}

loadTemperatureSummary();
