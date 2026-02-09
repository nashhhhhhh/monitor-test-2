let tempChart;

/* ================= FETCH + PARSE ================= */

async function fetchSpiralData() {
  try {
    const res = await fetch("/api/spiral_blast_freezer", { cache: "no-store" });
    if (!res.ok) throw new Error(`API Error ${res.status}`);

    // ---- FIX: Read as text first ----
    let rawText = await res.text();

    // Replace invalid JSON values
    rawText = rawText
      .replace(/\bNaN\b/g, "null")
      .replace(/\bInfinity\b/g, "null")
      .replace(/\b-Infinity\b/g, "null");

    const apiData = JSON.parse(rawText);

    console.log("SANITIZED API:", apiData);

    return parseSpiralAPI(apiData);

  } catch (err) {
    console.error("Fetch error:", err);
    return null;
  }
}


/* ================= DATA NORMALIZATION ================= */

function parseSpiralAPI(apiData) {

  const spirals =
    apiData?.status_data ||
    apiData?.data ||
    apiData ||
    {};

  return {
    s1: normalizeSpiralData(
      spirals.spiral_01?.data || spirals.spiral_01 || []
    ),
    s2: normalizeSpiralData(
      spirals.spiral_02?.data || spirals.spiral_02 || []
    ),
    s3: normalizeSpiralData(
      spirals.spiral_03?.data || spirals.spiral_03 || []
    )
  };
}


function normalizeSpiralData(rows) {
  if (!Array.isArray(rows)) return [];

  return rows.map(r => ({
    time: r.energy_time || r.time || r.timestamp || "",
    freezing_time: Number(r.freezing_time) || 0,
    runtime: Number(r.runtime) || 0,
    main_drive: Number(r.main_drive) || 0,
    sub_drive: Number(r.sub_drive) || 0,
    pt01: Number(r.pt01) || 0,
    pt02: Number(r.pt02) || 0,
    tef01: Number(r.tef01) || 0,
    tef02: Number(r.tef02) || 0,
    pcs_min: Number(r.pcs_min_total) || 0,
    pcs_day: Number(r.pcs_day_total) || 0
  }));
}


/* ================= UI UPDATE ================= */

function updateDashboard(data) {
  if (!data) return;

  const s1 = getLast(data.s1);
  const s2 = getLast(data.s2);
  const s3 = getLast(data.s3);

  updateKPIs(data);
  updateDiagnostics(s1, s2, s3);
  updateSummaryTable(s1, s2, s3);
  updateChart(data.s1, data.s2, data.s3);
}


function getLast(arr) {
  return arr.length ? arr[arr.length - 1] : {};
}


/* ================= KPI ================= */

function averageRuntime(dataset) {
  if (!dataset.length) return 0;
  return dataset.reduce((sum, r) => sum + r.runtime, 0) / dataset.length / 60;
}


function updateKPIs(data) {
  const active = [data.s1, data.s2, data.s3]
    .map(getLast)
    .filter(s => s.runtime > 0).length;

  setText("val-active-freezers", `${active} / 3`);
  setText("val-runtime-s1", averageRuntime(data.s1).toFixed(2));
  setText("val-runtime-s2", averageRuntime(data.s2).toFixed(2));
  setText("val-runtime-s3", averageRuntime(data.s3).toFixed(2));
}


/* ================= DIAGNOSTICS ================= */

function updateDiagnostics(s1, s2, s3) {
  updateSpiralCard("sf01", s1);
  updateSpiralCard("sf02", s2);
  updateSpiralCard("sf03", s3);
}


function updateSpiralCard(prefix, s) {
  const safe = v => Number.isFinite(v) ? v : 0;

  setText(`${prefix}-temp`,
    `${safe(s.tef01).toFixed(1)} / ${safe(s.tef02).toFixed(1)}`);

  setText(`${prefix}-pressure`, safe(s.pt01).toFixed(2));
  setText(`${prefix}-runtime`, (safe(s.runtime) / 60).toFixed(2));

  const status = safe(s.runtime) > 0 ? "RUNNING" : "STOPPED";
  const pill = document.getElementById(`status-${prefix}`);

  if (pill) {
    pill.textContent = status;
    pill.className = `status-pill ${status === "RUNNING" ? "good" : "warning"}`;
  }
}


/* ================= SUMMARY TABLE ================= */

function updateSummaryTable(s1, s2, s3) {
  const tbody = document.getElementById("summary-table-body");
  if (!tbody) return;

  tbody.innerHTML = "";

  [
    ["Spiral 01", s1],
    ["Spiral 02", s2],
    ["Spiral 03", s3]
  ].forEach(([name, s]) => {
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
  if (!d1.length && !d2.length && !d3.length) return;

  const labels = (d1.length ? d1 : d2.length ? d2 : d3)
    .map(d => d.time);

  const ctx = document.getElementById("performanceChart");
  if (!ctx) return;

  if (!tempChart) {
    tempChart = new Chart(ctx, {
      type: "line",
      data: {
        labels,
        datasets: [
          buildDataset("Spiral 01", d1),
          buildDataset("Spiral 02", d2),
          buildDataset("Spiral 03", d3)
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


function buildDataset(label, data) {
  return {
    label,
    data: data.map(d => d.tef01),
    borderWidth: 2,
    tension: 0.4,
    pointRadius: 0
  };
}


/* ================= UTIL ================= */

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}


/* ================= LIVE REFRESH ================= */

async function refreshDashboard() {
  const data = await fetchSpiralData();
  if (data) updateDashboard(data);
}

refreshDashboard();
setInterval(refreshDashboard, 60000);
