document.addEventListener('DOMContentLoaded', () => {
    const container = document.getElementById('camera-container');
    const totalCountEl = document.getElementById('total-devices');
    const filterButtons = document.querySelectorAll('.filter-btn');
    const searchInput = document.getElementById('camera-search');

    let allDevices = [];
    let currentFilter = 'all';
    let searchQuery = '';

    /* ===============================
       Fetch CCTV Data
    =============================== */
    async function fetchCCTVStatus() {
        try {
            const response = await fetch('/api/cctv/log');
            if (!response.ok) throw new Error(`HTTP error ${response.status}`);

            allDevices = await response.json();

            // Sort: offline first, then alphabetical by name
            allDevices.sort((a, b) => {
                const aOff = a.status.toLowerCase() === 'offline';
                const bOff = b.status.toLowerCase() === 'offline';
                if (aOff !== bOff) return aOff ? -1 : 1;
                return a.name.localeCompare(b.name);
            });

            updateTotals(allDevices);
            totalCountEl.textContent = allDevices.length;
            renderDevices();

        } catch (error) {
            console.error('CCTV fetch error:', error);
            container.innerHTML = `<div class="status-msg error">Failed to load CCTV data</div>`;
        }
    }

    /* ===============================
       Render Device Cards
    =============================== */
    function renderDevices() {
        let devices = allDevices;

        if (currentFilter === 'online') {
            devices = devices.filter(d => d.status.toLowerCase() === 'online');
        } else if (currentFilter === 'offline') {
            devices = devices.filter(d => d.status.toLowerCase() === 'offline');
        }

        if (searchQuery) {
            const q = searchQuery.toLowerCase();
            devices = devices.filter(d =>
                d.name.toLowerCase().includes(q) ||
                (d.area && d.area.toLowerCase().includes(q))
            );
        }

        if (devices.length === 0) {
            container.innerHTML = `<div class="status-msg">No cameras found</div>`;
            return;
        }

        container.innerHTML = devices.map(dev => {
            const isOnline = dev.status.toLowerCase() === 'online';
            const area = dev.area && dev.area !== 'nan' ? escapeHTML(dev.area) : null;
            const address = dev.address && dev.address !== 'nan' ? escapeHTML(dev.address) : null;

            return `
                <div class="cam-card">
                    <div class="cam-header">
                        <span class="status-indicator ${isOnline ? 'online' : 'offline'}"></span>
                        <h3>${escapeHTML(dev.name)}</h3>
                    </div>
                    <div class="cam-body">
                        ${area ? `<div class="area-badge">${area}</div>` : ''}
                        <div class="status-label ${isOnline ? 'status-online' : 'status-offline'}">
                            ${dev.status.toUpperCase()}
                        </div>
                        ${address ? `<p class="cam-address">${address}</p>` : ''}
                        <p class="timestamp">Last Offline: ${dev.lastOffline && dev.lastOffline !== 'nan' ? dev.lastOffline : '—'}</p>
                        <p class="timestamp">Offline Count: ${dev.offlineCount && dev.offlineCount !== 'nan' ? dev.offlineCount : '0'}</p>
                        <p class="timestamp">Offline Duration: ${dev.offlineDuration && dev.offlineDuration !== 'nan' ? dev.offlineDuration : '—'}</p>
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
       Search Handling
    =============================== */
    searchInput.addEventListener('input', () => {
        searchQuery = searchInput.value.trim();
        renderDevices();
    });

    /* ===============================
       Helpers
    =============================== */
    function escapeHTML(str) {
        return String(str).replace(/[&<>"']/g, match => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
        })[match]);
    }

    function updateTotals(data) {
        let online = 0, offline = 0;
        data.forEach(dev => {
            if (dev.status.toLowerCase() === 'online') online++;
            else if (dev.status.toLowerCase() === 'offline') offline++;
        });
        document.getElementById('onlineCount').textContent = online;
        document.getElementById('offlineCount').textContent = offline;
    }

    /* ===============================
       Init
    =============================== */
    fetchCCTVStatus();
    setInterval(fetchCCTVStatus, 30000);
});
