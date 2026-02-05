document.addEventListener('DOMContentLoaded', () => {
    const container = document.getElementById('camera-container');
    const totalCountEl = document.getElementById('total-devices');
    const filterButtons = document.querySelectorAll('.filter-btn');

    let allDevices = [];
    let currentFilter = 'all';

    /* ===============================
       Fetch CCTV Data
    =============================== */
    async function fetchCCTVStatus() {
        try {
            console.log('Fetching CCTV data...');
            const response = await fetch('/api/cctv/log');

            if (!response.ok) {
                throw new Error(`HTTP error ${response.status}`);
            }

            allDevices = await response.json();
            updateTotals(allDevices);
            console.log('Devices received:', allDevices);

            totalCountEl.textContent = allDevices.length;
            renderDevices();

        } catch (error) {
            console.error('CCTV fetch error:', error);
            container.innerHTML = `
                <div class="status-msg error">
                    Failed to load CCTV data
                </div>
            `;
        }
    }

    /* ===============================
       Render Device Cards
    =============================== */
    function renderDevices() {
        let devicesToRender = allDevices;

        if (currentFilter === 'online') {
            devicesToRender = allDevices.filter(d =>
                d.status && d.status.toLowerCase() === 'online'
            );
        }

        if (currentFilter === 'offline') {
            devicesToRender = allDevices.filter(d =>
                d.status && d.status.toLowerCase() === 'offline'
            );
        }

        if (devicesToRender.length === 0) {
            container.innerHTML = `
                <div class="status-msg">
                    No cameras found for this filter
                </div>
            `;
            return;
        }

        container.innerHTML = devicesToRender.map(dev => {
            const isOnline = dev.status.toLowerCase() === 'online';

            return `
                <div class="cam-card">
                    <div class="cam-header">
                        <span class="status-indicator ${isOnline ? 'online' : 'offline'}"></span>
                        <h3>${escapeHTML(dev.name)}</h3>
                    </div>

                    <div class="cam-body">
                        <div class="status-label ${isOnline ? 'status-online' : 'status-offline'}">
                            ${dev.status.toUpperCase()}
                        </div>

                        <p class="timestamp">
                            Last Offline: ${dev.lastOffline || '-'}
                        </p>

                        <p class="timestamp">
                            Offline Count: ${dev.offlineCount || '0'}
                        </p>

                        <p class="timestamp">
                            Offline Duration: ${dev.offlineDuration || '-'}
                        </p>
                    </div>
                </div>
            `;
        }).join('');
    }

    /* ===============================
       Filter Button Handling
    =============================== */
    filterButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            filterButtons.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            currentFilter = btn.dataset.filter;
            renderDevices();
        });
    });

    /* ===============================
       Helpers
    =============================== */
    function escapeHTML(str) {
        return String(str).replace(/[&<>"']/g, match => ({
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#39;'
        })[match]);
    }

    function updateTotals(data) {
    let online = 0;
    let offline = 0;

    data.forEach(dev => {
        if (dev.status && dev.status.toLowerCase() === 'online') {
            online++;
        } else if (dev.status && dev.status.toLowerCase() === 'offline') {
            offline++;
        }
    });

    document.getElementById("onlineCount").textContent = online;
    document.getElementById("offlineCount").textContent = offline;
}


    /* ===============================
       Init
    =============================== */
    fetchCCTVStatus();
    setInterval(fetchCCTVStatus, 30000); // auto refresh every 30s
   

});
