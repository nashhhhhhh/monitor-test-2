
// Boiler/script.js
new Chart(document.getElementById('boilerEfficiencyGauge'), {
    type: 'doughnut',
    data: {
        labels: ['Efficiency', 'Loss'],
        datasets: [{ data: [88, 12], backgroundColor: ['#10b981', '#e5e7eb'] }]
    },
    options: { circumference: 180, rotation: 270 }
});

new Chart(document.getElementById('boilerCorrelation'), {
    type: 'line',
    data: {
        labels: ['Mon', 'Tue', 'Wed'],
        datasets: [{ label: 'Steam Output', data: [85, 88, 90], borderColor: '#3b82f6' }]
    }
});


