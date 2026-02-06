async function initDashboard() {
    try {
        const res = await fetch('/api/spiral_blast_freezer');
        const data = await res.json();

        const spirals = Object.values(data.spirals);

        let running = 0;
        let tempSum = 0;
        let tempCount = 0;
        let runtimeSum = 0;

        spirals.forEach(s => {
            const latest = s.data[s.data.length - 1];
            if (!latest) return;

            if (latest.runtime > 0) running++;
            if (latest.tef01 !== undefined) {
                tempSum += latest.tef01;
                tempCount++;
            }
            runtimeSum += latest.runtime || 0;
        });

        // KPI updates
        document.getElementById('kpi-running').innerText = `${running} / ${spirals.length}`;
        document.getElementById('kpi-temp').innerText =
            tempCount ? (tempSum / tempCount).toFixed(1) + " °C" : "-- °C";
        document.getElementById('kpi-runtime').innerText = runtimeSum.toFixed(1) + " hrs";

        const energyLatest = data.energy.monthly.at(-1)?.kwh || 0;
        document.getElementById('kpi-energy').innerText =
            energyLatest.toLocaleString() + " kWh";

        renderTempChart(spirals);

    } catch (err) {
        console.error("Dashboard error:", err);
    }
}

function renderTempChart(spirals) {
    const ctx = document.getElementById('tempChart');
    if (!ctx) return;

    const labels = spirals[0]?.data.map(d => d.time) || [];

    const datasets = spirals.map((s, i) => ({
        label: `Spiral ${i + 1}`,
        data: s.data.map(d => d.tef01),
        borderWidth: 2,
        tension: 0.3
    }));

    new Chart(ctx, {
        type: 'line',
        data: { labels, datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    title: { display: true, text: 'Temperature (°C)' }
                }
            }
        }
    });
}

document.addEventListener('DOMContentLoaded', initDashboard);
