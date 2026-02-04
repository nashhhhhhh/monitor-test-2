document.addEventListener('DOMContentLoaded', () => {
    // 1. Live Clock
    const updateClock = () => {
        const now = new Date();
        document.getElementById('clock').innerText = now.toLocaleString('en-GB', {
            weekday: 'short', day: '2-digit', month: 'short', 
            hour: '2-digit', minute: '2-digit', second: '2-digit'
        }).toUpperCase();
    };
    setInterval(updateClock, 1000);
    updateClock();

    // 2. Utility Distribution Chart
    const ctxOverview = document.getElementById('overviewChart').getContext('2d');
    new Chart(ctxOverview, {
        type: 'bar',
        data: {
            labels: ['Electricity', 'Water', 'Air', 'Gas'],
            datasets: [{
                label: 'Usage Index',
                data: [82, 45, 63, 28],
                backgroundColor: '#3b82f6',
                borderRadius: 8
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                y: { beginAtZero: true, grid: { color: '#f1f5f9' } },
                x: { grid: { display: false } }
            }
        }
    });

    // 3. Thermal Stability Chart
    const ctxThermal = document.getElementById('thermalChart').getContext('2d');
    new Chart(ctxThermal, {
        type: 'line',
        data: {
            labels: ['06:00', '09:00', '12:00', '15:00', '18:00', '21:00'],
            datasets: [{
                label: 'Avg Temperature (°C)',
                data: [2.2, 2.1, 2.5, 2.3, 2.1, 2.2],
                borderColor: '#10b981',
                backgroundColor: 'rgba(16, 185, 129, 0.05)',
                fill: true,
                tension: 0.4,
                borderWidth: 3,
                pointRadius: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                y: { min: 0, max: 5, grid: { color: '#f1f5f9' } },
                x: { grid: { display: false } }
            }
        }
    });
});