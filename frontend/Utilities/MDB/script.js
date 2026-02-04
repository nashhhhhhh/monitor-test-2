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

function updateClock() {
    const clockElement = document.getElementById('clock');
    if (!clockElement) return;

    const now = new Date();
    const options = { 
        weekday: 'short', 
        day: '2-digit', 
        month: 'short', 
        hour: '2-digit', 
        minute: '2-digit', 
        second: '2-digit', 
        hour12: false 
    };
    
    // Formats to: WED, 04 FEB, 08:49:03
    clockElement.innerText = now.toLocaleString('en-GB', options).toUpperCase();
}

// Start clock and update every second
setInterval(updateClock, 1000);
updateClock();