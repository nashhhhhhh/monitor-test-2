document.addEventListener("DOMContentLoaded", () => {
    const statusLight = document.getElementById("status-indicator-light");
    const statusText = document.getElementById("overall-status-text");
    const lastSyncEl = document.getElementById("last-sync");
    const container = document.getElementById("health-tiles");
    const alertBox = document.getElementById("global-alert-box");

    // Exact mapping to your directory structure and API routes
    const systems = [
        { id: 'mdb', name: 'Power Systems (MDB)', path: '/Utilities/MDB/index.html', api: '/api/mdb' },
        { id: 'wtp', name: 'Water Treatment', path: '/Utilities/Water%20Treatment%20Plant/index.html', api: '/api/wtp' },
        { id: 'wwtp', name: 'Wastewater Plant', path: '/Utilities/Wastewater%20Plant/index.html', api: '/api/wwtp/latest' },
        { id: 'temp', name: 'Room Temperatures', path: '/Temperature/index.html', api: '/api/temperature/rooms' },
        { id: 'sbf', name: 'Spiral Blast Freezer', path: '/Spiral%20Blast%20Freezer/index.html', api: '/api/spiral_blast_freezer' },
        { id: 'cctv', name: 'CCTV Monitoring', path: '/CCTV/index.html', api: '/api/cctv/log' },
        { id: 'boiler', name: 'Boiler Systems', path: '/Utilities/Boiler/index.html', api: '/api/boiler' },
        { id: 'air', name: 'Air Compressor', path: '/Utilities/Air%20Compressor/index.html', api: '/api/aircompressor' }
    ];

    async function updateHeartbeat() {
        let criticalCount = 0;
        let processedData = [];

        // Safe fetch helper to catch NaN errors from Flask
        const fetchSystem = async (sys) => {
            try {
                const res = await fetch(sys.api);
                const text = await res.text();
                // Patch the JSON string to replace raw NaN with null before parsing
                const cleanText = text.replace(/: NaN/g, ': null');
                const data = JSON.parse(cleanText);
                return { ...sys, data, error: false };
            } catch (e) {
                console.warn(`⚠️ ${sys.name} Offline:`, e);
                return { ...sys, data: null, error: true };
            }
        };

        // Fetch all system data in parallel
        processedData = await Promise.all(systems.map(s => fetchSystem(s)));

        container.innerHTML = ""; // Clear loader

        processedData.forEach(sys => {
            const health = evaluateHealth(sys);
            if (health.status === 'CRITICAL') criticalCount++;

            const tile = document.createElement("div");
            tile.className = `status-card ${health.status.toLowerCase()}`;
            
            // Redirect to the correct folder path on click
            tile.onclick = () => window.location.href = sys.path;

            tile.innerHTML = `
                <div class="card-header">
                    <h3>${sys.name}</h3>
                    <span class="badge">${health.status}</span>
                </div>
                <div class="card-body">
                    <p class="status-msg">${health.message}</p>
                    <p class="metric-val">${health.value || '--'}</p>
                </div>
                <div class="card-footer">Investigate Details →</div>
            `;
            container.appendChild(tile);
        });

        // Update Header and Blinking Light
        lastSyncEl.textContent = new Date().toLocaleTimeString();
        if (criticalCount > 0) {
            statusLight.className = "status-light critical";
            statusText.textContent = `${criticalCount} Systems require attention!`;
            alertBox.classList.remove("hidden");
        } else {
            statusLight.className = "status-light ok";
            statusText.textContent = "All systems operational";
            alertBox.classList.add("hidden");
        }
    }

    /**
     * HEALTH ENGINE
     * Analyzes the data from app.py and assigns a status
     */
    function evaluateHealth(sys) {
        if (sys.error || !sys.data) return { status: 'OFFLINE', message: 'System Unreachable', value: '' };

        const d = sys.data;

        // Domain Specific Logic
        switch(sys.id) {
            case 'wtp':
                const cl2 = d.quality?.ro_chlorine?.slice(-1)[0]?.mg || 0;
                return cl2 < 0.2 ? 
                    { status: 'CRITICAL', message: 'Chlorine Level Low', value: cl2.toFixed(2) + ' mg' } : 
                    { status: 'NORMAL', message: 'Stable Quality', value: cl2.toFixed(2) + ' mg' };

            case 'temp':
                const highTemps = d.filter(r => (r.temperature || 0) > 5).length;
                return highTemps > 0 ? 
                    { status: 'CRITICAL', message: `${highTemps} Rooms Over Limit`, value: '' } : 
                    { status: 'NORMAL', message: 'Cooling Stable', value: '' };

            case 'mdb':
                const load = d.energy?.emdb_1?.slice(-1)[0]?.kwh || 0;
                return load > 280000 ? 
                    { status: 'CRITICAL', message: 'Peak Load Warning', value: load.toLocaleString() + ' kWh' } : 
                    { status: 'NORMAL', message: 'Power Nominal', value: load.toLocaleString() + ' kWh' };

            case 'cctv':
                const off = d.filter(c => c.status?.toLowerCase() !== "online").length;
                return off > 0 ? 
                    { status: 'CRITICAL', message: `${off} Cameras Offline`, value: '' } : 
                    { status: 'NORMAL', message: 'Security Active', value: 'All Online' };

            default:
                return { status: 'NORMAL', message: 'System Active', value: '' };
        }
    }

    updateHeartbeat();
    setInterval(updateHeartbeat, 30000); // Sync every 30 seconds
});