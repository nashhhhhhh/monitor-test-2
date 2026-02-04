document.addEventListener('DOMContentLoaded', () => {

    // --- 1. INITIALIZE CHARTS ---
    const efficiencyCtx = document.getElementById('efficiencyChart');
    const dewpointCtx = document.getElementById('dewpointChart');

    const efficiencyChart = new Chart(efficiencyCtx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [
                {
                    label: 'Flow (m³)',
                    data: [],
                    borderColor: '#3b82f6',
                    backgroundColor: 'rgba(59, 130, 246, 0.1)',
                    borderWidth: 2,
                    tension: 0.35,
                    yAxisID: 'y'
                },
                {
                    label: 'Energy (kWh)',
                    data: [],
                    borderColor: '#10b981',
                    backgroundColor: 'rgba(16, 185, 129, 0.1)',
                    borderWidth: 2,
                    tension: 0.35,
                    yAxisID: 'y1'
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: { type: 'linear', display: true, position: 'left' },
                y1: { type: 'linear', display: true, position: 'right', grid: { drawOnChartArea: false } }
            }
        }
    });

    const dewpointChart = new Chart(dewpointCtx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'Dewpoint (°C)',
                data: [],
                borderColor: '#f59e0b',
                backgroundColor: 'rgba(245, 158, 11, 0.2)',
                fill: true,
                tension: 0.35
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false
        }
    });

    // --- 2. DATA LOADING LOGIC ---
    async function loadData() {
        try {
            // Fetch consolidated data from your Flask API
            const res = await fetch('/api/aircompressor');
            if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
            
            const apiData = await res.json();

            // Safety check: Ensure arrays exist and aren't empty
            if (!apiData.energy.length || !apiData.flow.length || !apiData.dewpoint.length) {
                console.warn("API returned empty data arrays. Check your CSV files.");
                return;
            }

            // Slice the last 24 entries for the charts
            const recentEnergy = apiData.energy.slice(-24);
            const recentFlow = apiData.flow.slice(-24);
            const recentDew = apiData.dewpoint.slice(-24);

            // Prepare Chart Data
            const labels = recentEnergy.map(d => d.time);
            const energyValues = recentEnergy.map(d => d.energy);
            const flowValues = recentFlow.map(d => d.flow);
            const dewValues = recentDew.map(d => d.dewpoint);

            // Get Latest Values for KPIs (Last item in the full arrays)
            const lastFlow = apiData.flow[apiData.flow.length - 1].flow;
            const lastEnergy = apiData.energy[apiData.energy.length - 1].energy;
            const lastDew = apiData.dewpoint[apiData.dewpoint.length - 1].dewpoint;

            updateUI({
                labels,
                energyValues,
                flowValues,
                dewValues,
                lastFlow,
                lastEnergy,
                lastDew
            });

        } catch (err) {
            console.error('Air Compressor data error:', err);
            // Optional: Update UI to show error status
            document.querySelectorAll('.kpi-value').forEach(el => el.innerText = 'ERR');
        }
    }

    // --- 3. UI UPDATE LOGIC ---
    function updateUI(data) {
        // Update Efficiency Chart
        efficiencyChart.data.labels = data.labels;
        efficiencyChart.data.datasets[0].data = data.flowValues;
        efficiencyChart.data.datasets[1].data = data.energyValues;
        efficiencyChart.update();

        // Update Dewpoint Chart
        dewpointChart.data.labels = data.labels;
        dewpointChart.data.datasets[0].data = data.dewValues;
        dewpointChart.update();

        // Update KPI Cards
        document.getElementById('val-flow').innerText = `${data.lastFlow.toFixed(2)} m³`;
        document.getElementById('val-energy').innerText = `${data.lastEnergy.toFixed(2)} kWh`;
        document.getElementById('val-dewpoint').innerText = `${data.lastDew.toFixed(1)} °C`;

        // Calculate Specific Power (Efficiency)
        if (data.lastFlow > 0) {
            const efficiency = (data.lastEnergy / data.lastFlow).toFixed(3);
            document.getElementById('val-efficiency').innerText = `${efficiency} kWh/m³`;
        } else {
            document.getElementById('val-efficiency').innerText = `0.000`;
        }
    }

    // Initial load
    loadData();

    // Auto-refresh every 30 seconds
    setInterval(loadData, 30000);
});