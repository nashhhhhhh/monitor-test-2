document.addEventListener('DOMContentLoaded', () => {
    // 1. Initialize Trend Chart
    const ctx = document.getElementById('lightingTrendChart').getContext('2d');
    new Chart(ctx, {
        type: 'line',
        data: {
            labels: ['00:00', '04:00', '08:00', '12:00', '16:00', '20:00'],
            datasets: [{
                label: 'kW Usage',
                data: [4, 3.5, 12, 11.5, 12.4, 8],
                borderColor: '#3b82f6',
                tension: 0.3,
                fill: true,
                backgroundColor: 'rgba(59, 130, 246, 0.1)'
            }]
        },
        options: { responsive: true, maintainAspectRatio: false }
    });

    // 2. Placeholder for Future Dataset Ingestion
    // When you have your dataset in the future, call this function:
    const loadLightingData = (data) => {
        const root = document.getElementById('lighting-dataset-root');
        const tbody = document.getElementById('lighting-data-rows');
        const table = document.getElementById('fixture-table');
        
        // Remove the "Awaiting..." message
        root.querySelector('p').style.display = 'none';
        table.style.display = 'table';

        // Example Mapping
        data.forEach(item => {
            const row = `<tr>
                <td>${item.zone}</td>
                <td><strong>${item.id}</strong></td>
                <td><span class="status-pill ${item.status.toLowerCase()}">${item.status}</span></td>
                <td>${item.life}%</td>
            </tr>`;
            tbody.innerHTML += row;
        });
    };

    // MOCK DATA (Simulating future plugin)
    const mockData = [
        { zone: 'Main Hall', id: 'L-101', status: 'Active', life: 98 },
        { zone: 'Loading Bay', id: 'L-204', status: 'Warning', life: 12 },
        { zone: 'Office A', id: 'L-055', status: 'Active', life: 85 }
    ];

    // Uncomment the line below to test the data injection:
    // loadLightingData(mockData);
});