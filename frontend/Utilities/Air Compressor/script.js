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
        const text = await res.text();
        return Papa.parse(text.split('\n').slice(2).join('\n'), {
            header: true,
            dynamicTyping: true
        }).data;
    }

    async function loadData() {
        const [energy, flow, dew] = await Promise.all([
            loadCSV('/data/aircompressor_energy.csv'),
            loadCSV('/data/airmeter_flow.csv'),
            loadCSV('/data/air_dewpoint.csv')
        ]);

        const mapFlow = Object.fromEntries(flow.map(d => [d.Timestamp, d.Value]));
        const mapDew = Object.fromEntries(dew.map(d => [d.Timestamp, d.Value]));

        const merged = energy
            .filter(e => mapFlow[e.Timestamp] && mapDew[e.Timestamp])
            .slice(-24)
            .map(e => ({
                time: e.Timestamp.split(' ')[1],
                energy: e.Value,
                flow: mapFlow[e.Timestamp],
                dew: mapDew[e.Timestamp]
            }));

        updateUI(merged);
    }

    function updateUI(data) {
        efficiencyChart.data.labels = data.map(d => d.time);
        efficiencyChart.data.datasets[0].data = data.map(d => d.flow);
        efficiencyChart.data.datasets[1].data = data.map(d => d.energy);
        efficiencyChart.update();

        dewpointChart.data.labels = data.map(d => d.time);
        dewpointChart.data.datasets[0].data = data.map(d => d.dew);
        dewpointChart.update();

        const latest = data[data.length - 1];
        document.getElementById('val-flow').innerText = `${latest.flow} m³`;
        document.getElementById('val-dewpoint').innerText = `${latest.dew} °C`;

        const efficiency = (latest.energy / latest.flow).toFixed(3);
        document.getElementById('val-efficiency').innerText = `${efficiency} kWh/m³`;

        const cost = (latest.energy * 0.12).toFixed(2);
        document.getElementById('val-cost').innerText = `$${cost}`;
    }

    loadData();
});
