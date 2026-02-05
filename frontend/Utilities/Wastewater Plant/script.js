document.addEventListener("DOMContentLoaded", () => {
  let charts = {};

  async function loadWWTPData() {
    try {
      console.log("🚰 Syncing WWTP Data...");
      const [effluent, rawPump, rawTemp, pmgEnergy, ctrlEnergy] = await Promise.all([
        fetch("/api/wwtp/effluent_pump").then(r => r.json()),
        fetch("/api/wwtp/raw_pump").then(r => r.json()),
        fetch("/api/wwtp/raw_temp").then(r => r.json()),
        fetch("/api/wwtp/pmg_energy").then(r => r.json()),
        fetch("/api/wwtp/control_energy").then(r => r.json())
      ]);

      // 1. Update KPIs & Efficiency
      updateKPIs({ effluent, rawPump, rawTemp, pmgEnergy, ctrlEnergy });
      
      // 2. Update Status Time
      const now = new Date();
      document.getElementById('last-sync').textContent = now.toLocaleTimeString();

      // 3. Render/Update Charts
      renderChart('energyChart', 'line', {
        labels: pmgEnergy.map(d => d.time).slice(-20),
        datasets: [
          { label: 'Plant Energy', data: pmgEnergy.map(d => d.value).slice(-20), borderColor: '#3b82f6', tension: 0.3 },
          { label: 'Control Panel', data: ctrlEnergy.map(d => d.value).slice(-20), borderColor: '#10b981', tension: 0.3 }
        ]
      });

      renderChart('flowChart', 'bar', {
        labels: effluent.map(d => d.time).slice(-15),
        datasets: [
          { label: 'Effluent Out', data: effluent.map(d => d.value).slice(-15), backgroundColor: '#3b82f6' },
          { label: 'Raw Inflow', data: rawPump.map(d => d.value).slice(-15), backgroundColor: '#94a3b8' }
        ]
      });

      renderChart('tempChart', 'line', {
        labels: rawTemp.map(d => d.time).slice(-20),
        datasets: [{ 
            label: 'Temp °C', 
            data: rawTemp.map(d => d.value).slice(-20), 
            borderColor: '#f59e0b', 
            backgroundColor: 'rgba(245, 158, 11, 0.1)',
            fill: true,
            tension: 0.3
        }]
      });

    } catch (err) {
      console.error("🔥 WWTP load error:", err);
      document.getElementById('status-text').textContent = "ERROR";
      document.getElementById('status-text').style.color = "var(--danger)";
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
        plugins: { 
            legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 11, family: 'Inter' } } } 
        },
        scales: {
          x: { grid: { display: false } },
          y: { beginAtZero: false }
        }
      }
    });
  }

  function updateKPIs(data) {
    const lastPmg = data.pmgEnergy.slice(-1)[0]?.value || 0;
    const lastCtrl = data.ctrlEnergy.slice(-1)[0]?.value || 0;
    const lastTemp = data.rawTemp.slice(-1)[0]?.value || 0;
    const lastRaw = data.rawPump.slice(-1)[0]?.value || 0;
    const lastEffluent = data.effluent.slice(-1)[0]?.value || 0;
    
    document.getElementById("kpi-energy").textContent = (lastPmg + lastCtrl).toLocaleString();
    document.getElementById("kpi-temp").textContent = `${lastTemp.toFixed(1)}°C`;
    
    const active = (lastEffluent > 0 ? 1 : 0) + (lastRaw > 0 ? 1 : 0);
    document.getElementById("kpi-pumps").textContent = active;

    let efficiency = 0;
    if (lastRaw > 0) {
      efficiency = ((lastRaw - lastEffluent) / lastRaw) * 100;
    }
    document.getElementById("kpi-efficiency").textContent = `${efficiency.toFixed(1)}%`;
  }

  loadWWTPData();
  setInterval(loadWWTPData, 60000);
});