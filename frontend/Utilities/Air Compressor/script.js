document.addEventListener('DOMContentLoaded', () => {

  const efficiencyChart = new Chart(
    document.getElementById('efficiencyChart'),
    {
      type: 'line',
      data: {
        labels: [],
        datasets: [
          {
            label: 'Flow (m³)',
            data: [],
            borderWidth: 2,
            tension: 0.35
          },
          {
            label: 'Energy (kWh)',
            data: [],
            borderWidth: 2,
            tension: 0.35
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false
      }
    }
  );

  const dewpointChart = new Chart(
    document.getElementById('dewpointChart'),
    {
      type: 'line',
      data: {
        labels: [],
        datasets: [{
          label: 'Dewpoint (°C)',
          data: [],
          fill: true,
          tension: 0.35
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false
      }
    }
  );

  async function loadCSV(path) {
    const res = await fetch(path);
    if (!res.ok) throw new Error(`Failed to load ${path}`);
    const text = await res.text();

    return Papa.parse(
      text.split('\n').slice(2).join('\n'),
      { header: true, dynamicTyping: true }
    ).data.filter(r => r.Timestamp && r.Value != null);
  }

  async function loadData() {
    try {
      const [energy, flow, dew] = await Promise.all([
        loadCSV('/data/aircompressor_energy.csv'),
        loadCSV('/data/airmeter_flow.csv'),
        loadCSV('/data/air_dewpoint.csv')
      ]);

      const flowMap = Object.fromEntries(flow.map(d => [d.Timestamp, d.Value]));
      const dewMap  = Object.fromEntries(dew.map(d => [d.Timestamp, d.Value]));

      const merged = energy
        .filter(e => flowMap[e.Timestamp] && dewMap[e.Timestamp])
        .slice(-24)
        .map(e => ({
          time: e.Timestamp.split(' ')[1],
          energy: e.Value,
          flow: flowMap[e.Timestamp],
          dew: dewMap[e.Timestamp]
        }));

      if (!merged.length) return;

      updateUI(merged);

    } catch (err) {
      console.error('Air Compressor data error:', err);
    }
  }

  function updateUI(data) {
    efficiencyChart.data.labels = data.map(d => d.time);
    efficiencyChart.data.datasets[0].data = data.map(d => d.flow);
    efficiencyChart.data.datasets[1].data = data.map(d => d.energy);
    efficiencyChart.update();

    dewpointChart.data.labels = data.map(d => d.time);
    dewpointChart.data.datasets[0].data = data.map(d => d.dew);
    dewpointChart.update();

    const last = data[data.length - 1];

    document.getElementById('val-flow').innerText = `${last.flow} m³`;
    document.getElementById('val-energy').innerText = `${last.energy} kWh`;
    document.getElementById('val-dewpoint').innerText = `${last.dew} °C`;

    const efficiency = (last.energy / last.flow).toFixed(3);
    document.getElementById('val-efficiency').innerText = `${efficiency} kWh/m³`;
  }

  loadData();
});
