document.addEventListener('DOMContentLoaded', () => {

    // MOCK DATA — hourly kWh readings per zone over 24 hours
    const mockData = [
        {
            zone: 'Main Hall', id: 'L-101', status: 'Active', life: 98,
            hourly_kwh: [1.2, 1.1, 1.0, 1.0, 1.1, 1.3, 3.8, 5.2, 5.4, 5.3, 5.1, 5.4,
                         5.5, 5.3, 5.2, 5.4, 5.6, 5.0, 4.2, 3.1, 2.5, 2.0, 1.6, 1.3]
        },
        {
            zone: 'Loading Bay', id: 'L-204', status: 'Warning', life: 12,
            hourly_kwh: [0.8, 0.7, 0.7, 0.7, 0.8, 1.0, 2.5, 3.4, 3.5, 3.4, 3.3, 3.5,
                         3.6, 3.4, 3.3, 3.5, 3.6, 3.2, 2.8, 2.0, 1.6, 1.2, 1.0, 0.9]
        },
        {
            zone: 'Office A', id: 'L-055', status: 'Active', life: 85,
            hourly_kwh: [0.3, 0.2, 0.2, 0.2, 0.2, 0.3, 1.2, 2.1, 2.2, 2.2, 2.1, 2.2,
                         2.3, 2.2, 2.1, 2.2, 2.3, 2.0, 1.4, 0.8, 0.5, 0.4, 0.3, 0.3]
        }
    ];

    const hours = Array.from({ length: 24 }, (_, i) => `${String(i).padStart(2, '0')}:00`);

    // Compute total kWh per hour across all zones
    const totalPerHour = hours.map((_, i) =>
        mockData.reduce((sum, z) => sum + z.hourly_kwh[i], 0)
    );

    // Compute grand total for the KPI header
    const grandTotal = totalPerHour.reduce((a, b) => a + b, 0).toFixed(1);
    document.getElementById('total-lighting-kwh').innerHTML = `${grandTotal} <small>kWh</small>`;

    // Zone colours
    const palette = ['#3b82f6', '#10b981', '#f59e0b'];

    // Build datasets: one line per zone + one total line
    const datasets = mockData.map((z, i) => ({
        label: `${z.zone} (${z.id})`,
        data: z.hourly_kwh,
        borderColor: palette[i],
        backgroundColor: 'transparent',
        fill: false,
        tension: 0.4,
        pointRadius: 2
    }));

    datasets.push({
        label: 'Total Consumption',
        data: totalPerHour,
        borderColor: '#6366f1',
        backgroundColor: 'rgba(99,102,241,0.04)',
        fill: false,
        tension: 0.4,
        borderWidth: 2.5,
        borderDash: [6, 3],
        pointRadius: 0
    });

    // Render chart
    const ctx = document.getElementById('lightingTrendChart').getContext('2d');
    new Chart(ctx, {
        type: 'line',
        data: { labels: hours, datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 10 } } },
                tooltip: {
                    callbacks: {
                        label: ctx => ` ${ctx.dataset.label}: ${ctx.parsed.y.toFixed(2)} kWh`
                    }
                }
            },
            scales: {
                x: { title: { display: true, text: 'Hour of Day' } },
                y: { title: { display: true, text: 'Energy (kWh)' }, beginAtZero: true }
            }
        }
    });
});
