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
        
        // Forced "Normal" state for the global header
        statusLight.className = "status-light ok";
        statusText.textContent = "All systems operational";
        alertBox.classList.add("hidden");
    }

    /**
     * HEALTH ENGINE - RESET TO NORMAL
     * Reports NORMAL as long as the system is reachable.
     */
    function evaluateHealth(sys) {
        // If the API is down or file is missing, we still show OFFLINE to help you debug paths
        if (sys.error || !sys.data) {
            return { status: 'OFFLINE', message: 'System Unreachable', value: 'Check Data Source' };
        }

        // All systems return NORMAL regardless of values for now
        let displayValue = 'Online';

        // We still extract the values just so you can see the data is flowing
        try {
            const d = sys.data;
            if (sys.id === 'wtp') {
                const cl2 = d.quality?.ro_chlorine?.slice(-1)[0]?.mg || 0;
                displayValue = cl2.toFixed(2) + ' mg';
            } else if (sys.id === 'mdb') {
                const load = d.energy?.emdb_1?.slice(-1)[0]?.kwh || 0;
                displayValue = load.toLocaleString() + ' kWh';
            } else if (sys.id === 'temp') {
                displayValue = d.length + ' Rooms Monitored';
            } else if (sys.id === 'wwtp') {
                const temp = d.rawTemp?.slice(-1)[0]?.value || 0;
                displayValue = temp.toFixed(1) + ' °C';
            }
        } catch (e) {
            displayValue = 'Connected';
        }

        return { 
            status: 'NORMAL', 
            message: 'System Operational', 
            value: displayValue 
        };
    }

    updateHeartbeat();
    setInterval(updateHeartbeat, 30000); // Sync every 30 seconds
});