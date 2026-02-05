document.addEventListener("DOMContentLoaded", () => {
  // Store chart instances globally within this scope to prevent "Canvas in use" errors
  let charts = {};

  async function loadWWTPData() {
    try {
      const [effluent, rawPump, rawTemp, pmgEnergy, ctrlEnergy, wgData] = await Promise.all([
        fetch("/api/wwtp/effluent_pump").then(r => r.json()),
        fetch("/api/wwtp/raw_pump").then(r => r.json()),
        fetch("/api/wwtp/raw_temp").then(r => r.json()),
        fetch("/api/wwtp/pmg_energy").then(r => r.json()),
        fetch("/api/wwtp/control_energy").then(r => r.json()),
        fetch("/api/wwtp/wg").then(r => r.json())
      ]);

      updateKPIs({ effluent, rawPump, rawTemp, pmgEnergy, ctrlEnergy });
      
      // Update or Create Charts
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
            fill: true 
        }]
      });

    } catch (err) {
      console.error("🔥 WWTP load error:", err);
    }
  }

  function renderChart(id, type, data) {
    const ctx = document.getElementById(id);
    if (!ctx) return;

    // If chart exists, destroy it before creating a new one to fix the Canvas error
    if (charts[id]) {
        charts[id].destroy();
    }

    charts[id] = new Chart(ctx, {
      type: type,
      data: data,
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { 
            legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 11 } } } 
        },
        scales: {
          x: { grid: { display: false } },
          y: { beginAtZero: false }
        }
      }
    });
  }

  function updateKPIs(data) {
    const latestPmg = data.pmgEnergy.slice(-1)[0]?.value || 0;
    const latestCtrl = data.ctrlEnergy.slice(-1)[0]?.value || 0;
    const latestTemp = data.rawTemp.slice(-1)[0]?.value || 0;
    
    document.getElementById("kpi-energy").textContent = `${(latestPmg + latestCtrl).toLocaleString()}`;
    document.getElementById("kpi-temp").textContent = `${latestTemp.toFixed(1)}°C`;
    
    const active = (data.effluent.slice(-1)[0]?.value > 0 ? 1 : 0) + 
                   (data.rawPump.slice(-1)[0]?.value > 0 ? 1 : 0);
    document.getElementById("kpi-pumps").textContent = active;
  }

  loadWWTPData();
  setInterval(loadWWTPData, 60000);
});