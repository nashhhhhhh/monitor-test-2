document.addEventListener("DOMContentLoaded", () => {
  let charts = {};

  async function loadMDBData() {
    try {
      console.log("⚡ Syncing MDB & Gen Data...");
      const response = await fetch("/api/mdb");
      const data = await response.json();

      // 1. Update KPIs
      updateKPIs(data);
      
      // 2. Update Table
      updateGenTable(data.generators);

      // 3. Render Charts
      
      // -- Chart 1: MDB Energy Distribution (Bar) --
      const mdbKeys = ['mdb_6', 'mdb_7', 'mdb_8', 'mdb_9', 'mdb_10'];
      const distributionData = mdbKeys.map(key => {
          const list = data.energy[key];
          return list.length > 0 ? list[list.length - 1].kwh : 0;
      });

      renderChart('distributionChart', 'bar', {
        labels: ['MDB-6', 'MDB-7', 'MDB-8', 'MDB-9', 'MDB-10'],
        datasets: [{
          label: 'Energy (kWh)',
          data: distributionData,
          backgroundColor: '#3b82f6',
          borderRadius: 6
        }]
      });

      // -- Chart 2: EMDB-1 Trend (Line) --
      const emdbData = data.energy.emdb_1;
      renderChart('emdbTrendChart', 'line', {
        labels: emdbData.map(d => d.time).slice(-20),
        datasets: [{
          label: 'EMDB-1 Energy',
          data: emdbData.map(d => d.kwh).slice(-20),
          borderColor: '#10b981',
          backgroundColor: 'rgba(16, 185, 129, 0.1)',
          fill: true,
          tension: 0.3
        }]
      });

      // -- Chart 3: Generator Runtimes (Line/Point) --
      const genTimeLabels = data.generators.gen_1.map(d => d.time).slice(-15);
      renderChart('genRuntimeChart', 'line', {
        labels: genTimeLabels,
        datasets: [
          { label: 'Gen-1', data: data.generators.gen_1.map(d => d.runtime).slice(-15), borderColor: '#f59e0b', tension: 0.1 },
          { label: 'Gen-2', data: data.generators.gen_2.map(d => d.runtime).slice(-15), borderColor: '#ef4444', tension: 0.1 },
          { label: 'Gen-3', data: data.generators.gen_3.map(d => d.runtime).slice(-15), borderColor: '#3b82f6', tension: 0.1 },
          { label: 'Gen-4', data: data.generators.gen_4.map(d => d.runtime).slice(-15), borderColor: '#94a3b8', tension: 0.1 }
        ]
      });

    } catch (err) {
      console.error("🔥 MDB load error:", err);
    }
  }

  function renderChart(id, type, data) {
    const ctx = document.getElementById(id);
    if (!ctx) return;
    if (charts[id]) { charts[id].destroy(); }
    charts[id] = new Chart(ctx, {
      type: type,
      data: data,
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, font: { family: 'Inter', size: 11 } } } },
        scales: { y: { beginAtZero: false }, x: { grid: { display: false } } }
      }
    });
  }

  function updateKPIs(data) {
    const emdbVal = data.energy.emdb_1.slice(-1)[0]?.kwh || 0;
    document.getElementById("kpi-emdb").textContent = emdbVal.toLocaleString();

    let totalMdb = 0;
    ['mdb_6', 'mdb_7', 'mdb_8', 'mdb_9', 'mdb_10'].forEach(key => {
        totalMdb += data.energy[key].slice(-1)[0]?.kwh || 0;
    });
    document.getElementById("kpi-total-mdb").textContent = totalMdb.toLocaleString();

    // Generators active check: compare last 2 values
    let activeGens = 0;
    [1,2,3,4].forEach(n => {
        const list = data.generators[`gen_${n}`];
        if (list.length >= 2) {
            if (list[list.length-1].runtime > list[list.length-2].runtime) activeGens++;
        }
    });
    document.getElementById("kpi-gen-status").textContent = `${activeGens} / 4`;
  }

  function updateGenTable(gens) {
      const tbody = document.getElementById('gen-table-body');
      tbody.innerHTML = '';
      [1,2,3,4].forEach(n => {
          const key = `gen_${n}`;
          const latest = gens[key].slice(-1)[0]?.runtime || 0;
          const prev = gens[key].slice(-2)[0]?.runtime || 0;
          const isRunning = latest > prev && prev !== 0;

          const tr = document.createElement('tr');
          tr.innerHTML = `
            <td>Generator ${n}</td>
            <td>${latest.toFixed(1)} hrs</td>
            <td><span class="status-pill ${isRunning ? 'active' : 'warning'}">${isRunning ? 'RUNNING' : 'STANDBY'}</span></td>
          `;
          tbody.appendChild(tr);
      });
  }

  

  loadMDBData();
  setInterval(loadMDBData, 60000);
});