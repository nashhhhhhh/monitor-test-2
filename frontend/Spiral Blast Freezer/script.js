async function initDashboard() {
    try {
        const res = await fetch('/api/spiral_blast_freezer');
        const data = await res.json();

        const spiralsObj = data.status_data || {};
        const spirals = Object.entries(spiralsObj);

        let activeCount = 0;
        let tempSum = 0;
        let tempCount = 0;
        let runtimeTotal = 0;

        const tableBody = document.getElementById('summary-table-body');
        if (tableBody) tableBody.innerHTML = "";

        spirals.forEach(([key, spiral], index) => {
            if (!spiral.data || !spiral.data.length) return;

            const latest = spiral.data[spiral.data.length - 1];

            const temp = isFinite(latest.tef01) ? Number(latest.tef01) : null;
            const runtime = isFinite(latest.runtime) ? Number(latest.runtime) : 0;

            const running = runtime > 0;
            if (running) activeCount++;

            if (temp !== null) {
                tempSum += temp;
                tempCount++;
            }

            runtimeTotal += runtime;

            // ===== STATUS CARD =====
            const unitId = index + 1;

            setText(`sf0${unitId}-temp`, temp !== null ? temp.toFixed(1) : "--");
            setText(`sf0${unitId}-runtime`, runtime.toFixed(1));

            const statusEl = document.getElementById(`status-sf0${unitId}`);
            if (statusEl) {
                statusEl.innerText = running ? "RUNNING" : "STOPPED";
                statusEl.className = "status-pill " + (running ? "ok" : "warning");
            }

            // ===== TABLE ROW =====
            if (tableBody) {
                const tr = document.createElement("tr");
                tr.innerHTML = `
                    <td>Spiral ${unitId}</td>
                    <td>${temp !== null ? temp.toFixed(1) : "--"}</td>
                    <td>${runtime.toFixed(1)}</td>
                    <td>${running ? "RUNNING" : "STOPPED"}</td>
                `;
                tableBody.appendChild(tr);
            }
        });

        // ===== KPI UPDATES =====
        setText(
            "val-active-freezers",
            `${activeCount} / ${spirals.length}`
        );

        const avgTemp = tempCount ? (tempSum / tempCount).toFixed(1) : "--";
        setText("val-temp-avg", avgTemp + " °C");

        setText("val-runtime-total", runtimeTotal.toFixed(1));

        const energyArr = data.energy?.monthly_energy || [];
        const latestEnergy = energyArr.length
            ? Number(energyArr[energyArr.length - 1].kwh || 0)
            : 0;

        setText(
            "val-energy-total",
            latestEnergy.toLocaleString()
        );

        renderPerformanceChart(spirals);

    } catch (err) {
        console.error("Spiral Dashboard Error:", err);
    }
}

/* ================= CHART ================= */

function renderPerformanceChart(spirals) {
    const ctx = document.getElementById('performanceChart');
    if (!ctx) return;

    const first = spirals.find(([_, s]) => s.data && s.data.length);
    const labels = first
        ? first[1].data.map((d, i) => d.time ?? `T${i + 1}`)
        : [];

    const datasets = spirals.map(([key, spiral], index) => ({
        label: `Spiral ${index + 1} TEF01`,
        data: spiral.data.map(d =>
            isFinite(d.tef01) ? Number(d.tef01) : null
        ),
        borderWidth: 2,
        tension: 0.3,
        spanGaps: true
    }));

    new Chart(ctx, {
        type: 'line',
        data: { labels, datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    title: {
                        display: true,
                        text: 'Temperature (°C)'
                    }
                }
            }
        }
    });
}

/* ================= HELPERS ================= */

function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.innerText = value;
}

document.addEventListener('DOMContentLoaded', initDashboard);
