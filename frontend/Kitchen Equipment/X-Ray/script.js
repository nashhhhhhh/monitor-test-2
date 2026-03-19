const mockXrayData = {
    summary: {
        inspectedToday: 18420,
        rejectedUnits: 133,
        uptime: 99.4,
        avgSpeed: 31.5,
        avgTubeTemp: 61.8,
        bestSensitivityMm: 1.2,
        falseRejects: 19,
        metalEvents: 7,
        densityEvents: 11,
        verificationCompletion: 96
    },
    lanes: [
        { name: 'XR-01', product: 'Meal Tray Line A', sensitivity: '1.2 mm SS', status: 'Running' },
        { name: 'XR-02', product: 'Packed Rice Bowls', sensitivity: '1.5 mm SS', status: 'Running' },
        { name: 'XR-03', product: 'Sauce Sachets', sensitivity: '1.0 mm SS', status: 'Calibration' }
    ],
    throughput: {
        labels: ['06:00', '08:00', '10:00', '12:00', '14:00', '16:00', '18:00'],
        inspected: [1820, 2440, 2710, 2630, 2860, 3010, 2950],
        rejected: [14, 17, 16, 23, 21, 19, 23]
    },
    rejectReasons: {
        labels: ['Metal', 'Calcified Bone', 'Dense Product', 'Missing Product', 'Seal Fault'],
        values: [7, 22, 11, 38, 55]
    },
    health: {
        labels: ['06:00', '08:00', '10:00', '12:00', '14:00', '16:00', '18:00'],
        tubeTemp: [58, 59, 60, 62, 63, 64, 61],
        doseCurrent: [2.4, 2.5, 2.6, 2.8, 2.7, 2.9, 2.6],
        conveyorSpeed: [30.8, 31.1, 31.4, 31.0, 31.8, 32.0, 32.1]
    },
    events: [
        { time: '17:42', lane: 'XR-03', product: 'Sauce Sachets', reason: 'Calibration deviation', action: 'Auto hold and QA check' },
        { time: '16:18', lane: 'XR-01', product: 'Meal Tray Line A', reason: 'Seal fault reject', action: 'Operator removed pack' },
        { time: '14:56', lane: 'XR-02', product: 'Packed Rice Bowls', reason: 'Dense product alarm', action: 'Review image and release' },
        { time: '12:11', lane: 'XR-01', product: 'Meal Tray Line A', reason: 'Metal contaminant reject', action: 'Bin lock and escalation' }
    ]
};

function updateClock() {
    const clock = document.getElementById('clock');
    if (!clock) return;

    clock.innerText = new Date().toLocaleTimeString('en-GB', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false
    });
}

function populateSummary(data) {
    const rejectRate = (data.summary.rejectedUnits / data.summary.inspectedToday) * 100;

    document.getElementById('val-inspected').innerText = data.summary.inspectedToday.toLocaleString();
    document.getElementById('val-reject-rate').innerText = `${rejectRate.toFixed(2)}%`;
    document.getElementById('val-uptime').innerText = `${data.summary.uptime.toFixed(1)}%`;
    document.getElementById('val-speed').innerText = `${data.summary.avgSpeed.toFixed(1)} m/min`;
    document.getElementById('val-temp').innerText = `${data.summary.avgTubeTemp.toFixed(1)} C`;

    document.getElementById('val-sensitivity').innerText = `${data.summary.bestSensitivityMm.toFixed(1)} mm SS`;
    document.getElementById('val-false-rejects').innerText = data.summary.falseRejects.toString();
    document.getElementById('val-metal-events').innerText = data.summary.metalEvents.toString();
    document.getElementById('val-density-events').innerText = data.summary.densityEvents.toString();
    document.getElementById('val-verification').innerText = `${data.summary.verificationCompletion}%`;
    document.getElementById('bar-verification').style.width = `${data.summary.verificationCompletion}%`;
}

function populateLanes(data) {
    const laneStatusList = document.getElementById('lane-status-list');
    laneStatusList.innerHTML = data.lanes.map((lane) => {
        const statusClass = lane.status === 'Running' ? 'active' : lane.status === 'Calibration' ? 'warning' : 'offline';
        return `
            <div class="status-item">
                <div class="status-meta">
                    <strong>${lane.name}</strong>
                    <span>${lane.product} - Sensitivity ${lane.sensitivity}</span>
                </div>
                <span class="status-pill ${statusClass}">${lane.status}</span>
            </div>
        `;
    }).join('');
}

function populateEvents(data) {
    const body = document.getElementById('event-table-body');
    body.innerHTML = data.events.map((event) => `
        <tr>
            <td>${event.time}</td>
            <td>${event.lane}</td>
            <td>${event.product}</td>
            <td>${event.reason}</td>
            <td>${event.action}</td>
        </tr>
    `).join('');
}

function renderCharts(data) {
    new Chart(document.getElementById('throughputChart'), {
        type: 'bar',
        data: {
            labels: data.throughput.labels,
            datasets: [
                {
                    type: 'bar',
                    label: 'Inspected Packs',
                    data: data.throughput.inspected,
                    backgroundColor: '#2563eb',
                    borderRadius: 8,
                    yAxisID: 'y'
                },
                {
                    type: 'line',
                    label: 'Rejected Packs',
                    data: data.throughput.rejected,
                    borderColor: '#ef4444',
                    backgroundColor: 'rgba(239, 68, 68, 0.18)',
                    fill: true,
                    tension: 0.35,
                    yAxisID: 'y1'
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: 'bottom' }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    title: { display: true, text: 'Inspected Packs' }
                },
                y1: {
                    beginAtZero: true,
                    position: 'right',
                    grid: { drawOnChartArea: false },
                    title: { display: true, text: 'Rejects' }
                }
            }
        }
    });

    new Chart(document.getElementById('rejectReasonChart'), {
        type: 'doughnut',
        data: {
            labels: data.rejectReasons.labels,
            datasets: [{
                data: data.rejectReasons.values,
                backgroundColor: ['#ef4444', '#f59e0b', '#8b5cf6', '#14b8a6', '#3b82f6']
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: 'bottom' }
            }
        }
    });

    new Chart(document.getElementById('healthChart'), {
        type: 'line',
        data: {
            labels: data.health.labels,
            datasets: [
                {
                    label: 'Tube Temp (C)',
                    data: data.health.tubeTemp,
                    borderColor: '#f59e0b',
                    backgroundColor: 'rgba(245, 158, 11, 0.14)',
                    tension: 0.35,
                    yAxisID: 'y'
                },
                {
                    label: 'Dose Current (mA)',
                    data: data.health.doseCurrent,
                    borderColor: '#7c3aed',
                    backgroundColor: 'rgba(124, 58, 237, 0.14)',
                    tension: 0.35,
                    yAxisID: 'y1'
                },
                {
                    label: 'Conveyor Speed (m/min)',
                    data: data.health.conveyorSpeed,
                    borderColor: '#0f766e',
                    backgroundColor: 'rgba(15, 118, 110, 0.14)',
                    tension: 0.35,
                    yAxisID: 'y2'
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: 'bottom' }
            },
            scales: {
                y: {
                    beginAtZero: false,
                    position: 'left',
                    title: { display: true, text: 'Tube Temp (C)' }
                },
                y1: {
                    beginAtZero: false,
                    position: 'right',
                    grid: { drawOnChartArea: false },
                    title: { display: true, text: 'Dose Current (mA)' }
                },
                y2: {
                    beginAtZero: false,
                    display: false
                }
            }
        }
    });
}

document.addEventListener('DOMContentLoaded', () => {
    populateSummary(mockXrayData);
    populateLanes(mockXrayData);
    populateEvents(mockXrayData);
    renderCharts(mockXrayData);
    updateClock();
    setInterval(updateClock, 1000);
});
