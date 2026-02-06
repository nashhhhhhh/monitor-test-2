let tempChart;

/* ================= FETCH + PARSE ================= */

async function fetchSpiralData() {
  try {
    const res = await fetch("/api/spiral_blast_freezer");
    if (!res.ok) throw new Error("API fetch failed");

    const apiData = await res.json();
    return parseSpiralAPI(apiData);

  } catch (err) {
    console.error("Fetch error:", err);
    return null;
  }
}


function parseSpiralAPI(apiData) {
  const spirals = apiData.status_data || {};
  const monthly = apiData.energy?.monthly_energy || [];

  return {
    s1: normalizeSpiralData(spirals.spiral_01?.data || []),
    s2: normalizeSpiralData(spirals.spiral_02?.data || []),
    s3: normalizeSpiralData(spirals.spiral_03?.data || []),
    energy: extractMonthlyEnergy(monthly)
  };
}


function normalizeSpiralData(rows) {
  return rows.map(r => ({
    time: r.energy_time || r.time || "",
    freezing_time: +r.freezing_time || 0,
    runtime: +r.runtime || 0,
    main_drive: +r.main_drive || 0,
    sub_drive: +r.sub_drive || 0,
    pt01: +r.pt01 || 0,
    pt02: +r.pt02 || 0,
    tef01: +r.tef01 || 0,
    tef02: +r.tef02 || 0
  }));
}


function extractMonthlyEnergy(rows) {
  let total = 0;

  rows.forEach(r => {
    if (r.remark === "TOTAL MONTH (kWh)") {
      total = (+r.screw_compressor || 0) + (+r.spiral_freezer || 0);
    }
  });

  return total;
}


/* ================= UI UPDATE ================= */

function updateDashboard(data) {
  if (!data) return;

  const s1 = data.s1.at(-1) || {};
  const s2 = data.s2.at(-1) || {};
  const s3 = data.s3.at(-1) || {};

  updateKPIs(data, [s1, s2, s3]);
  updateDiagnostics(s1, s2, s3);
  updateSummaryTable(s1, s2, s3);
  updateChart(data.s1);
}


function updateKPIs(data, spirals) {
  const active = spirals.filter(s => s.runtime > 0).length;
  document.getElementById("val-active-freezers").textContent = `${active} / 3`;

  document.getElementById("val-energy-total").textContent =
    data.energy.toLocaleString();

  const avgTemp =
    spirals.reduce((sum, s) => sum + s.tef01, 0) / spirals.length || 0;

  document.getElementById("val-temp-avg").textContent =
    avgTemp.toFixed(1) + " °C";

  const totalRuntime =
    spirals.reduce((sum, s) => sum + s.runtime, 0) / 60;

  document.getElementById("val-runtime-total").textContent =
    totalRuntime.toFixed(2);
}


function updateDiagnostics(s1, s2, s3) {
  updateSpiralCard("sf01", s1);
  updateSpiralCard("sf02", s2);
}


function updateSpiralCard(prefix, s) {
  document.getElementById(`${prefix}-temp`).textContent =
    `${s.tef01.toFixed(1)} / ${s.tef02.toFixed(1)}`;

  document.getElementById(`${prefix}-pressure`).textContent =
    s.pt01.toFixed(2);

  document.getElementById(`${prefix}-runtime`).textContent =
    (s.runtime / 60).toFixed(2);

  const statusEl = document.getElementById(`status-${prefix}`);
  const status = s.runtime > 0 ? "RUNNING" : "STOPPED";

  statusEl.textContent = status;
  statusEl.className = `status-pill ${status === "RUNNING" ? "good" : "warning"}`;
}


function updateSummaryTable(s1, s2, s3) {
  const tbody = document.getElementById("summary-table-body");
  tbody.innerHTML = "";

  [
    ["Spiral 01", s1],
    ["Spiral 02", s2],
    ["Spiral 03", s3]
  ].forEach(([name, s]) => {
    const tr = document.createElement("tr");

    tr.innerHTML = `
      <td>${name}</td>
      <td>${s.tef01.toFixed(1)} / ${s.tef02.toFixed(1)}</td>
      <td>${s.pt01.toFixed(2)} / ${s.pt02.toFixed(2)}</td>
      <td>${s.freezing_time} min</td>
      <td>${(s.runtime / 60).toFixed(2)} hrs</td>
      <td>${s.runtime > 0 ? "RUNNING" : "STOPPED"}</td>
    `;

    tbody.appendChild(tr);
  });
}


/* ================= CHART ================= */

function updateChart(data) {
  const labels = data.map(d => d.time);
  const temps = data.map(d => d.tef01);

  if (!tempChart) {
    const ctx = document.getElementById("performanceChart");

    tempChart = new Chart(ctx, {
      type: "line",
      data: {
        labels: labels,
        datasets: [{
          label: "Spiral 01 TEF01 (°C)",
          data: temps,
          borderWidth: 2,
          tension: 0.4,
          pointRadius: 0
        }]
      },
      options: {
        responsive: true,
        animation: false,
        scales: {
          y: {
            title: { display: true, text: "Temperature (°C)" }
          }
        }
      }
    });

  } else {
    tempChart.data.labels = labels;
    tempChart.data.datasets[0].data = temps;
    tempChart.update("none");
  }
}


/* ================= LIVE REFRESH ================= */

async function refreshDashboard() {
  const data = await fetchSpiralData();
  updateDashboard(data);
}

refreshDashboard();
setInterval(refreshDashboard, 5000);
