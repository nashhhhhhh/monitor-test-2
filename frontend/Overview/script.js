document.addEventListener("DOMContentLoaded", () => {
    const alertBox = document.getElementById("global-alert-box");
    const lastSyncEl = document.getElementById("last-sync");

    async function updateUnifiedCommand() {
        console.log("📡 Command Center: Refreshing all subsystems...");
        
        try {
            // 1. Fetch all API data in parallel for maximum performance
            const [mdb, temp, wtp, sbf, cctv, wwtp, utility] = await Promise.all([
                fetch("/api/mdb").then(r => r.json()),
                fetch("/api/temperature/rooms").then(r => r.json()),
                fetch("/api/wtp").then(r => r.json()),
                fetch("/api/spiral_blast_freezer").then(r => r.json()),
                fetch("/api/cctv/log").then(r => r.json()),
                fetch("/api/wwtp/latest").then(r => r.json()),
                fetch("/api/boiler").then(r => r.json()) // Utility covers Boiler & Compressor
            ]);

            // 2. Process each system's health and update the UI
            const statusMDB = processMDB(mdb);
            const statusTemp = processTemp(temp);
            const statusWTP = processWTP(wtp);
            const statusSBF = processSBF(sbf);
            const statusCCTV = processCCTV(cctv);
            const statusWWTP = processWWTP(wwtp);
            const statusUtility = processUtility(utility);

            // 3. Update Global Banner
            const criticals = [statusMDB, statusTemp, statusWTP, statusSBF, statusCCTV, statusWWTP, statusUtility]
                              .filter(s => s === 'CRITICAL').length;
            
            alertBox.classList.toggle("hidden", criticals === 0);
            lastSyncEl.textContent = new Date().toLocaleTimeString();

        } catch (err) {
            console.error("🔥 Command Center Sync Error:", err);
        }
    }

    // --- SYSTEM LOGIC ENGINES ---

    function processMDB(data) {
        const load = data.energy.emdb_1.slice(-1)[0]?.kwh || 0;
        const activeGens = data.generators.gen_1.slice(-1)[0]?.runtime > 0 ? "Active" : "Standby"; 
        updateTile("mdb", load.toLocaleString(), activeGens, load > 250000 ? "WARNING" : "NORMAL");
        return load > 250000 ? "WARNING" : "NORMAL";
    }

    function processTemp(data) {
        const avg = data.reduce((acc, r) => acc + r.temperature, 0) / data.length;
        const criticalRooms = data.filter(r => r.temperature > 5).length;
        const status = criticalRooms > 0 ? "CRITICAL" : "NORMAL";
        updateTile("temp", avg.toFixed(1), criticalRooms, status);
        return status;
    }

    function processWTP(data) {
        const cl2 = data.quality.ro_chlorine.slice(-1)[0]?.mg || 0;
        const pres = data.pressure.ro_supply.slice(-1)[0]?.bar || 0;
        const status = cl2 < 0.2 ? "CRITICAL" : "NORMAL";
        updateTile("wtp", cl2.toFixed(2), pres.toFixed(1), status);
        return status;
    }

    function processSBF(data) {
        const sbfTemp = data.status_data.spiral_01.data.slice(-1)[0]?.tef01 || 0;
        const pcs = data.conveyor_data.conveyor_01.data.slice(-1)[0]?.pcs_min_total || 0;
        const status = sbfTemp > -15 ? "WARNING" : "NORMAL";
        updateTile("sbf", sbfTemp.toFixed(1), pcs.toFixed(0), status);
        return status;
    }

    function processCCTV(data) {
        const offline = data.filter(c => c.status.toLowerCase() !== "online").length;
        const status = offline > 2 ? "CRITICAL" : (offline > 0 ? "WARNING" : "NORMAL");
        updateTile("cctv", offline, data.length, status);
        return status;
    }

    function processWWTP(data) {
        const temp = data.rawTemp.slice(-1)[0]?.value || 0;
        const energy = data.pmgEnergy.slice(-1)[0]?.value || 0;
        const status = temp > 35 ? "CRITICAL" : "NORMAL";
        updateTile("wwtp", temp.toFixed(1), energy.toLocaleString(), status);
        return status;
    }

    function processUtility(boiler) {
        const gas = boiler.consumption.gas_total_kg.slice(-1)[0]?.gas || 0;
        const steam = boiler.consumption.direct_steam_kg.slice(-1)[0]?.steam || 0;
        updateTile("boiler", gas.toLocaleString(), steam.toLocaleString(), "NORMAL");
        // Reuse for air compressor if needed or keep separate
        return "NORMAL";
    }

    /**
     * Helper to update tile UI elements
     */
    function updateTile(id, val, subVal, status) {
        const tile = document.getElementById(`tile-${id}`);
        const statusBadge = document.getElementById(`status-${id}`);
        const valEl = document.getElementById(`val-${id}`);
        
        if (!tile) return;

        // Update Text
        if (valEl) valEl.childNodes[0].textContent = val + " ";
        if (statusBadge) statusBadge.textContent = status;

        // Specific sub-values based on tile ID
        if (id === "temp") document.getElementById("val-temp-crit").textContent = subVal;
        if (id === "wtp") document.getElementById("val-wtp-pres").textContent = subVal;
        if (id === "cctv") document.getElementById("val-cctv-total").textContent = subVal;
        if (id === "mdb") document.getElementById("val-gens").textContent = subVal;

        // Update Colors
        tile.className = `health-tile ${status.toLowerCase()}`;
    }

    // Initial Sync
    updateUnifiedCommand();
    // Refresh every 30 seconds
    setInterval(updateUnifiedCommand, 30000);
});