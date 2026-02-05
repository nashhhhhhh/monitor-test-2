document.addEventListener('DOMContentLoaded', () => {
    const container = document.getElementById('camera-container');
    const totalCountEl = document.getElementById('total-devices');

    async function fetchCCTVStatus() {
        try {
            console.log("Fetching CCTV data from API...");
            const response = await fetch('/api/cctv/log');
            
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            
            const devices = await response.json();
            console.log("Devices received:", devices);

            // 1. Check if data is empty
            if (!devices || devices.length === 0) {
                container.innerHTML = '<div class="status-msg">No camera data found in CSV log.</div>';
                totalCountEl.innerText = '0';
                return;
            }

            // 2. Update Total Count
            totalCountEl.innerText = devices.length;

            // 3. Generate Cards
            container.innerHTML = devices.map(dev => {
                const isOnline = dev.status.toLowerCase().trim() === 'online';
                return `
                    <div class="cam-card">
                        <div class="cam-header">
                            <span class="status-indicator ${isOnline ? 'online' : 'offline'}"></span>
                            <h3>${dev.name}</h3>
                        </div>
                        <div class="cam-body">
                            <div class="status-label ${isOnline ? 'status-online' : 'status-offline'}">
                                ${dev.status.toUpperCase()}
                            </div>
                            <p class="timestamp">Last Activity: ${dev.time}</p>
                        </div>
                    </div>
                `;
            }).join('');

        } catch (error) {
            console.error("CCTV Script Error:", error);
            container.innerHTML = `<div class="status-msg error">Connection Error: ${error.message}</div>`;
        }
    }

    // Initial run
    fetchCCTVStatus();
    // Auto refresh every 30 seconds
    setInterval(fetchCCTVStatus, 30000);
});