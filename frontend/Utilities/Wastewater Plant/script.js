document.addEventListener("DOMContentLoaded", () => {

  /* ============================
     KPI ELEMENTS
  ============================ */
  const kpiEnergy = document.getElementById("kpi-energy");
  const kpiPumps = document.getElementById("kpi-pumps");
  const kpiTemp = document.getElementById("kpi-temp");

  /* ============================
     FETCH ALL WWTP DATA
  ============================ */
  async function loadWWTPData() {
    try {
      console.log("🚰 Loading WWTP data...");

      const [
        effluentPump,
        rawPump,
        rawTemp,
        pmgEnergy,
        controlEnergy,
        wgData
      ] = await Promise.all([
        fetch("/api/wwtp/effluent_pump").then(r => r.json()),
        fetch("/api/wwtp/raw_pump").then(r => r.json()),
        fetch("/api/wwtp/raw_temp").then(r => r.json()),
        fetch("/api/wwtp/pmg_energy").then(r => r.json()),
        fetch("/api/wwtp/control_energy").then(r => r.json()),
        fetch("/api/wwtp/wg").then(r => r.json())
      ]);

      console.log("✅ WWTP data loaded");

      updateKPIs({
        effluentPump,
        rawPump,
        rawTemp,
        pmgEnergy,
        controlEnergy,
        wgData
      });

    } catch (err) {
      console.error("🔥 WWTP load error:", err);
      showErrorState();
    }
  }

  /* ============================
     KPI CALCULATIONS
  ============================ */
  function updateKPIs(data) {

    /* ---- TOTAL ENERGY ---- */
    const totalEnergy = [
      ...data.pmgEnergy,
      ...data.controlEnergy,
      ...data.wgData
    ].reduce((sum, r) => sum + (r.energy || 0), 0);

    kpiEnergy.textContent = `${totalEnergy.toFixed(1)} kWh`;

    /* ---- ACTIVE PUMPS ---- */
    const activePumps =
      countRunning(data.effluentPump) +
      countRunning(data.rawPump);

    kpiPumps.textContent = activePumps;

    /* ---- LATEST TEMPERATURE ---- */
    const latestTemp =
      data.rawTemp.length
        ? data.rawTemp[data.rawTemp.length - 1].temp
        : null;

    kpiTemp.textContent = latestTemp !== null
      ? `${latestTemp.toFixed(1)} °C`
      : "-- °C";
  }

  /* ============================
     HELPERS
  ============================ */
  function countRunning(pumpData) {
    return pumpData.filter(p => p.value > 0).length;
  }

  function showErrorState() {
    kpiEnergy.textContent = "—";
    kpiPumps.textContent = "—";
    kpiTemp.textContent = "—";
  }

  /* ============================
     INIT
  ============================ */
  loadWWTPData();
  setInterval(loadWWTPData, 60000); // refresh every 60s

});
