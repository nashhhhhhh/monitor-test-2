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

        // For WTP, also fetch chlorine status for all 3 plants
        const wtpEntry = processedData.find(s => s.id === 'wtp');
        if (wtpEntry && !wtpEntry.error) {
            try {
                const today = new Date().toISOString().split('T')[0];
                const [clRo, clSw1, clSw2] = await Promise.all([
                    fetch(`/api/wtp/chlorine?date=${today}&source=ro`).then(r => r.json()),
                    fetch(`/api/wtp/chlorine?date=${today}&source=softwater1`).then(r => r.json()),
                    fetch(`/api/wtp/chlorine?date=${today}&source=softwater2`).then(r => r.json())
                ]);
                wtpEntry.chlorineData = { ro: clRo, softwater1: clSw1, softwater2: clSw2 };
            } catch (e) {
                wtpEntry.chlorineData = null;
            }
        }

        // Fetch kitchen equipment statuses in parallel
        const kitchenApis = [
            { name: 'Hobart',     api: '/api/hobart' },
            { name: 'Steambox',   api: '/api/steambox' },
            { name: 'X-Ray',      api: '/api/xray' },
            { name: 'Checkweigh', api: '/api/checkweigher' }
        ];
        const kitchenResults = await Promise.all(kitchenApis.map(async (k) => {
            try {
                const res = await fetch(k.api);
                const text = await res.text();
                JSON.parse(text.replace(/: NaN/g, ': null'));
                return true;
            } catch (e) { return false; }
        }));
        const onlineCount = kitchenResults.filter(Boolean).length;
        const kitchenStatus = onlineCount === 4 ? 'normal' : onlineCount === 0 ? 'offline' : 'warning';
        const kitchenBadge = onlineCount === 4 ? 'NORMAL' : onlineCount === 0 ? 'OFFLINE' : 'WARNING';
        const kitchenMsg = onlineCount === 4 ? 'All Units Operational' : onlineCount === 0 ? 'All Units Offline' : 'Some Units Offline';

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

        // Append Kitchen Equipment tile
        const kitchenTile = document.createElement("div");
        kitchenTile.className = `status-card ${kitchenStatus}`;
        kitchenTile.onclick = () => window.location.href = '/Kitchen%20Equipment/index.html';
        kitchenTile.innerHTML = `
            <div class="card-header">
                <h3>Kitchen Equipment</h3>
                <span class="badge">${kitchenBadge}</span>
            </div>
            <div class="card-body">
                <p class="status-msg">${kitchenMsg}</p>
                <p class="metric-val">${onlineCount} <small>/ 4 Online</small></p>
            </div>
            <div class="card-footer">Investigate Details →</div>
        `;
        container.appendChild(kitchenTile);

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
                const cl = sys.chlorineData;
                const plants = [
                    { name: 'RO',          data: cl?.ro },
                    { name: 'Softwater 1', data: cl?.softwater1 },
                    { name: 'Softwater 2', data: cl?.softwater2 },
                ];
                const attention = plants.filter(p => {
                    if (!p.data || p.data.length === 0) return false;
                    const mg = p.data[p.data.length - 1].mg;
                    return mg < 0.5 || mg > 1.0;
                });
                if (attention.length > 0) {
                    return {
                        status: 'ATTENTION',
                        message: 'Low Cl₂: ' + attention.map(p => p.name).join(', '),
                        value: attention.map(p => {
                            const val = p.data[p.data.length - 1].mg.toFixed(2);
                            return `${p.name}: ${val} mg`;
                        }).join(' | ')
                    };
                }
                // All OK — show latest chlorine readings
                const readings = plants
                    .filter(p => p.data && p.data.length > 0)
                    .map(p => `${p.name}: ${p.data[p.data.length - 1].mg.toFixed(2)} mg`)
                    .join(' | ');
                displayValue = readings || '--';
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