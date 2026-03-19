document.addEventListener('DOMContentLoaded', () => {
    const dataset = window.lightingMonitoringMockData;
    const utils = window.lightingMonitoringUtils;

    if (!dataset || !utils) {
        console.error('Lighting monitoring dataset/helpers are unavailable.');
        return;
    }

    const summary = utils.summarizePortfolio(dataset);
    const charts = {};

    const roomTableBody = document.getElementById('room-health-tbody');
    const statsList = document.getElementById('lighting-stats-list');

    function formatNumber(value, digits = 1) {
        return utils.round(value, digits).toLocaleString();
    }

    function setText(id, value) {
        const node = document.getElementById(id);
        if (node) node.textContent = value;
    }

    function statusClass(status) {
        return status.toLowerCase();
    }

    function fixtureStatusLabel(fixture) {
        if (!fixture.isOperational || fixture.status === 'faulty') return 'Critical';
        return utils.classifyStatus(fixture.healthScore);
    }

    function renderSummaryCards() {
        setText('summary-total-fixtures', summary.totals.totalFixtures.toLocaleString());
        setText('summary-healthy-fixtures', summary.totals.healthyFixtures.toLocaleString());
        setText('summary-active-meta', `${summary.totals.activeFixtures} operational`);
        setText('summary-faulty-fixtures', summary.totals.faultyFixtures.toLocaleString());
        setText('summary-fault-meta', `${summary.faultPercentage}% fault rate`);
        setText('summary-availability', `${summary.operatingAvailability}%`);
        setText('summary-health-score', `${summary.averageHealthScore}%`);
        setText('summary-critical-rooms', summary.criticalRoomsCount.toLocaleString());

        setText('hero-availability', `${summary.operatingAvailability}%`);
        setText('hero-fixture-summary', `${summary.totals.activeFixtures}/${summary.totals.totalFixtures} fixtures operating`);
        setText(
            'hero-sync-time',
            `Snapshot ${new Date(dataset.generatedAt).toLocaleString('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}`
        );
    }

    function renderRoomTable() {
        roomTableBody.innerHTML = summary.rooms.map((room) => `
            <tr class="room-row" data-room-id="${room.roomId}">
                <td class="room-name-cell">
                    <strong>${room.roomName}</strong>
                    <span>${room.zone}</span>
                </td>
                <td>${room.totalFixtures}</td>
                <td>${room.healthyFixtures}</td>
                <td>${room.faultyFixtures}</td>
                <td>${room.operatingAvailability}%</td>
                <td>${room.avgHealthScore}%</td>
                <td><span class="status-pill ${statusClass(room.status)}">${room.status}</span></td>
            </tr>
        `).join('');
    }

    function renderStats() {
        const statCards = [
            {
                label: 'Best Performing Room',
                value: summary.bestRoom ? summary.bestRoom.roomName : '--',
                caption: summary.bestRoom ? `${summary.bestRoom.avgHealthScore}% health score` : 'No data'
            },
            {
                label: 'Worst Performing Room',
                value: summary.worstRoom ? summary.worstRoom.roomName : '--',
                caption: summary.worstRoom ? `${summary.worstRoom.avgHealthScore}% health score` : 'No data'
            },
            {
                label: 'Median Room Health',
                value: `${summary.medianRoomHealthScore}%`,
                caption: 'Middle room health score across monitored rooms'
            },
            {
                label: 'Mean Availability',
                value: `${summary.meanAvailability}%`,
                caption: 'Operational fixtures vs total fixtures'
            },
            {
                label: 'Total Fault %',
                value: `${summary.faultPercentage}%`,
                caption: `${summary.totals.faultyFixtures} faulty fixtures across the portfolio`
            }
        ];

        statsList.innerHTML = statCards.map((item) => `
            <div class="stat-item">
                <div class="stat-item-label">${item.label}</div>
                <div class="stat-item-value">${item.value}</div>
                <div class="stat-item-caption">${item.caption}</div>
            </div>
        `).join('');
    }

    function createChart(id, config) {
        const canvas = document.getElementById(id);
        if (!canvas) return;
        if (charts[id]) charts[id].destroy();
        charts[id] = new Chart(canvas, config);
    }

    function baseBarOptions(horizontal = false, suggestedMax) {
        return {
            responsive: true,
            maintainAspectRatio: false,
            indexAxis: horizontal ? 'y' : 'x',
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        boxWidth: 10,
                        usePointStyle: true,
                        font: { family: 'Inter', size: 11 }
                    }
                }
            },
            scales: {
                x: {
                    beginAtZero: true,
                    suggestedMax,
                    grid: { color: 'rgba(148, 163, 184, 0.12)' },
                    ticks: { color: '#64748b' }
                },
                y: {
                    beginAtZero: true,
                    suggestedMax,
                    grid: { display: horizontal ? false : true, color: 'rgba(148, 163, 184, 0.12)' },
                    ticks: { color: '#64748b' }
                }
            }
        };
    }

    function renderCharts() {
        const labels = summary.rooms.map((room) => room.roomName);

        createChart('roomHealthChart', {
            type: 'bar',
            data: {
                labels,
                datasets: [{
                    label: 'Health Score (%)',
                    data: summary.rooms.map((room) => room.avgHealthScore),
                    backgroundColor: '#2563eb',
                    borderRadius: 10
                }]
            },
            options: baseBarOptions(true, 100)
        });

        createChart('roomAvailabilityChart', {
            type: 'bar',
            data: {
                labels,
                datasets: [{
                    label: 'Availability (%)',
                    data: summary.rooms.map((room) => room.operatingAvailability),
                    backgroundColor: '#0891b2',
                    borderRadius: 10
                }]
            },
            options: baseBarOptions(true, 100)
        });

        createChart('roomFaultChart', {
            type: 'bar',
            data: {
                labels,
                datasets: [{
                    label: 'Faulty Fixtures',
                    data: summary.rooms.map((room) => room.faultyFixtures),
                    backgroundColor: '#dc2626',
                    borderRadius: 10
                }]
            },
            options: baseBarOptions(false)
        });

        createChart('fixtureStatusChart', {
            type: 'doughnut',
            data: {
                labels: ['Healthy', 'Faulty'],
                datasets: [{
                    data: [summary.totals.healthyFixtures, summary.totals.faultyFixtures],
                    backgroundColor: ['#15803d', '#dc2626'],
                    borderWidth: 0
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: '66%',
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            usePointStyle: true,
                            boxWidth: 10,
                            font: { family: 'Inter', size: 11 }
                        }
                    }
                }
            }
        });
    }

    renderSummaryCards();
    renderRoomTable();
    renderStats();
    renderCharts();
});
