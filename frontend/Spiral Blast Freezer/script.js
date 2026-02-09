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

  return {
    s1: normalizeSpiralData(spirals.spiral_01?.data || []),
    s2: normalizeSpiralData(spirals.spiral_02?.data || []),
    s3: normalizeSpiralData(spirals.spiral_03?.data || [])
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
    tef02: +r.tef02 || 0,
    pcs_min: +r.pcs_min_total || 0,
    pcs_day: +r.pcs_day_total || 0
  }));
}

/* ================= UI UPDATE ================= */

function updateDashboard(data) {
  if (!data) return;

  const s1 = data.s1.length ? data.s1[data.s1.length - 1] : {};
  const s2 = data.s2.length ? data.s2[data.s2.length - 1] : {};
  const s3 = data.s3.length ? data.s3[data.s3.length - 1] : {};

  updateKPIs(data);
  updateDiagnostics(s1, s2, s3);
  updateSummaryTable(s1, s2, s3);
  updateChart(data.s1, data.s2, data.s3);
}

/* ================= KPI ================= */

function averageRuntime(dataset) {
  if (!dataset.length) return 0;
  return dataset.reduce((sum, r) => sum + r.runtime, 0) / dataset.length / 60;
}

function updateKPIs(data) {
  const active =
    [data.s1, data.s2, data.s3]
      .map(d => d.length ? d[d.length - 1] : null)
      .filter(s => s && s.runtime > 0).length;

  document.getElementById("val-active-freezers").textContent = `${active} / 3`;

  document.getElementById("val-runtime-s1").textContent =
    averageRuntime(data.s1).toFixed(2);

  document.getElementById("val-runtime-s2").textContent =
    averageRuntime(data.s2).toFixed(2);

  document.getElementById("val-runtime-s3").textContent =
    averageRuntime(data.s3).toFixed(2);
}

/* ================= DIAGNOSTICS ================= */

function updateDiagnostics(s1, s2, s3) {
  updateSpiralCard("sf01", s1);
  updateSpiralCard("sf02", s2);
  updateSpiralCard("sf03", s3);
}

function updateSpiralCard(prefix, s = {}) {
  const safe = v => (Number.isFinite(v) ? v : 0);

  document.getElementById(`${prefix}-temp`).textContent =
    `${safe(s.tef01).toFixed(1)} / ${safe(s.tef02).toFixed(1)}`;

  document.getElementById(`${prefix}-pressure`).textContent =
    safe(s.pt01).toFixed(2);

  document.getElementById(`${prefix}-runtime`).textContent =
    (safe(s.runtime) / 60).toFixed(2);

  if (document.getElementById(`${prefix}-pcsmin`)) {
    document.getElementById(`${prefix}-pcsmin`).textContent =
      safe(s.pcs_min).toFixed(1);
  }

  if (document.getElementById(`${prefix}-pcsday`)) {
    document.getElementById(`${prefix}-pcsday`).textContent =
      safe(s.pcs_day).toFixed(0);
  }

  const statusEl = document.getElementById(`status-${prefix}`);
  const status = safe(s.runtime) > 0 ? "RUNNING" : "STOPPED";

  statusEl.textContent = status;
  statusEl.className = `status-pill ${status === "RUNNING" ? "active" : "warning"}`;
}

/* ================= SUMMARY TABLE ================= */

function updateSummaryTable(s1, s2, s3) {
  const tbody = document.getElementById("summary-table-body");
  tbody.innerHTML = "";

  [
    ["Spiral 01", s1],
    ["Spiral 02", s2],
    ["Spiral 03", s3]
  ].forEach(([name, s = {}]) => {
    const tr = document.createElement("tr");

    tr.innerHTML = `
      <td>${name}</td>
      <td>${(s.tef01 || 0).toFixed(1)} / ${(s.tef02 || 0).toFixed(1)}</td>
      <td>${(s.pt01 || 0).toFixed(2)} / ${(s.pt02 || 0).toFixed(2)}</td>
      <td>${s.freezing_time || 0} min</td>
      <td>${((s.runtime || 0) / 60).toFixed(2)} hrs</td>
      <td>${(s.runtime || 0) > 0 ? "RUNNING" : "STOPPED"}</td>
    `;

    tbody.appendChild(tr);
  });
}

/* ================= CHART ================= */

function updateChart(d1, d2, d3) {
  if (!d1.length) return;

  const labels = d1.map(d => d.time);

  const ctx = document.getElementById("performanceChart").getContext("2d");

  if (!tempChart) {
    tempChart = new Chart(ctx, {
      type: "line",
      data: {
        labels,
        datasets: [
          { label: "Spiral 01", data: d1.map(d => d.tef01), borderWidth: 2, tension: 0.4, pointRadius: 0 },
          { label: "Spiral 02", data: d2.map(d => d.tef01), borderWidth: 2, tension: 0.4, pointRadius: 0 },
          { label: "Spiral 03", data: d3.map(d => d.tef01), borderWidth: 2, tension: 0.4, pointRadius: 0 }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        interaction: { mode: "index", intersect: false },
        scales: {
          y: {
            title: { display: true, text: "Temperature (°C)" }
          }
        }
      }
    });
  } else {
    tempChart.data.labels = labels;
    tempChart.data.datasets[0].data = d1.map(d => d.tef01);
    tempChart.data.datasets[1].data = d2.map(d => d.tef01);
    tempChart.data.datasets[2].data = d3.map(d => d.tef01);
    tempChart.update("none");
  }
}

/* ================= LIVE REFRESH ================= */

async function refreshDashboard() {
  const data = await fetchSpiralData();
  if (data) updateDashboard(data);
}

refreshDashboard();
setInterval(refreshDashboard, 60000);
