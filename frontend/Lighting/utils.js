(function () {
    const MAX_LAMP_LIFE = 20000;
    const HEALTHY_MIN = 70;
    const WARNING_MIN = 40;
    const HIGH_USAGE_MULTIPLIER = 1.35;
    const HIGH_ENERGY_MULTIPLIER = 1.35;

    function round(value, digits = 1) {
        const factor = Math.pow(10, digits);
        return Math.round((Number(value || 0) + Number.EPSILON) * factor) / factor;
    }

    function clamp(value, min, max) {
        return Math.min(max, Math.max(min, value));
    }

    function percentage(numerator, denominator) {
        if (!denominator) return 0;
        return round((numerator / denominator) * 100, 1);
    }

    function average(values, digits = 1) {
        const valid = values.filter((value) => Number.isFinite(value));
        if (!valid.length) return 0;
        return round(valid.reduce((sum, value) => sum + value, 0) / valid.length, digits);
    }

    function sanitizeText(value, fallback = "Unknown") {
        if (value == null) return fallback;
        const text = String(value).trim();
        if (!text || text.toLowerCase() === "nan") return fallback;
        return text;
    }

    function toNumber(value) {
        if (value == null || value === "") return null;
        if (typeof value === "number") return Number.isFinite(value) ? value : null;

        const cleaned = String(value)
            .trim()
            .replace(/,/g, "")
            .replace(/^no data$/i, "");

        if (!cleaned) return null;

        const parsed = Number(cleaned);
        return Number.isFinite(parsed) ? parsed : null;
    }

    function classifyStatus(healthScore) {
        if (healthScore >= HEALTHY_MIN) return "Healthy";
        if (healthScore >= WARNING_MIN) return "Warning";
        return "Critical";
    }

    function computeFixtureHealth(lampLifeRemaining) {
        const lampLife = toNumber(lampLifeRemaining);
        if (lampLife == null) return null;
        return round(clamp((lampLife / MAX_LAMP_LIFE) * 100, 0, 100), 1);
    }

    function buildFixtureId(fixture, index) {
        const parts = [
            fixture["Area Name"],
            fixture["Circuit Name"],
            fixture["Fixture Name"],
            index + 1
        ];
        return parts
            .map((part) => sanitizeText(part, "x").toLowerCase().replace(/[^a-z0-9]+/g, "-"))
            .join("-");
    }

    function getGroupAverage(valuesMap, key) {
        return valuesMap.has(key) ? valuesMap.get(key) : null;
    }

    function normalizeDataset(dataset) {
        return Array.isArray(dataset?.fixtures) ? dataset.fixtures : [];
    }

    function summarizePortfolio(dataset) {
        const rawFixtures = normalizeDataset(dataset);
        const baseFixtures = rawFixtures.map((fixture, index) => {
            const notionalEnergy = toNumber(fixture["Notional Energy"]) ?? 0;
            const hoursOnInPeriod = toNumber(fixture["Hours On In Period"]);
            const hoursOnRunning = toNumber(fixture["Hours On Running"]);
            const lampLifeRemaining = toNumber(fixture["Lamp Life Remaining"]);
            const fixtureHealthPct = computeFixtureHealth(lampLifeRemaining);
            const status = classifyStatus(fixtureHealthPct ?? 0);

            return {
                id: buildFixtureId(fixture, index),
                "Fixture Name": sanitizeText(fixture["Fixture Name"]),
                "Area Name": sanitizeText(fixture["Area Name"]),
                "Circuit Name": sanitizeText(fixture["Circuit Name"], "Unassigned"),
                "Hours On In Period": hoursOnInPeriod,
                "Notional Energy": round(notionalEnergy, 3),
                "Hours On Running": hoursOnRunning,
                "Lamp Life Remaining": lampLifeRemaining,
                fixtureHealthPct,
                status,
                alerts: []
            };
        });

        const datasetAvgUsage = average(baseFixtures.map((fixture) => fixture["Hours On In Period"]));
        const areaEnergyAverages = new Map();
        const circuitEnergyAverages = new Map();

        const areaGroups = new Map();
        const circuitGroups = new Map();

        baseFixtures.forEach((fixture) => {
            const area = fixture["Area Name"];
            const circuit = fixture["Circuit Name"];

            if (!areaGroups.has(area)) areaGroups.set(area, []);
            if (!circuitGroups.has(circuit)) circuitGroups.set(circuit, []);

            areaGroups.get(area).push(fixture["Notional Energy"]);
            circuitGroups.get(circuit).push(fixture["Notional Energy"]);
        });

        areaGroups.forEach((values, key) => areaEnergyAverages.set(key, average(values, 3)));
        circuitGroups.forEach((values, key) => circuitEnergyAverages.set(key, average(values, 3)));

        const fixtures = baseFixtures.map((fixture) => {
            const alerts = [];
            const lampLife = fixture["Lamp Life Remaining"];
            const hoursRunning = fixture["Hours On Running"];
            const hoursInPeriod = fixture["Hours On In Period"];
            const areaAverageEnergy = getGroupAverage(areaEnergyAverages, fixture["Area Name"]);
            const circuitAverageEnergy = getGroupAverage(circuitEnergyAverages, fixture["Circuit Name"]);

            if (lampLife == null) {
                alerts.push({ label: "Lamp Life Data Missing", severity: "warning" });
            } else if (lampLife < 8000) {
                alerts.push({ label: "Lamp Life Critical", severity: "critical" });
            } else if (lampLife <= 12000) {
                alerts.push({ label: "Replacement Due Soon", severity: "warning" });
            }

            if (hoursRunning != null && hoursRunning > 16000) {
                alerts.push({ label: "Excessive Running Hours", severity: "critical" });
            }

            if (hoursInPeriod != null && datasetAvgUsage > 0 && hoursInPeriod > datasetAvgUsage * HIGH_USAGE_MULTIPLIER) {
                alerts.push({ label: "High Usage This Period", severity: "warning" });
            }

            const areaEnergyOutlier = areaAverageEnergy && fixture["Notional Energy"] > areaAverageEnergy * HIGH_ENERGY_MULTIPLIER;
            const circuitEnergyOutlier = circuitAverageEnergy && fixture["Notional Energy"] > circuitAverageEnergy * HIGH_ENERGY_MULTIPLIER;
            if (areaEnergyOutlier || circuitEnergyOutlier) {
                alerts.push({ label: "Abnormal Energy Flag", severity: "warning" });
            }

            if (fixture.status === "Critical") {
                alerts.push({ label: "Critical Fixture Health", severity: "critical" });
            }

            return {
                ...fixture,
                alerts
            };
        });

        const areas = Array.from(
            fixtures.reduce((map, fixture) => {
                const areaName = fixture["Area Name"];
                if (!map.has(areaName)) {
                    map.set(areaName, []);
                }
                map.get(areaName).push(fixture);
                return map;
            }, new Map())
        )
            .map(([areaName, areaFixtures]) => {
                const healthyFixtures = areaFixtures.filter((fixture) => fixture.status === "Healthy").length;
                const warningFixtures = areaFixtures.filter((fixture) => fixture.status === "Warning").length;
                const criticalFixtures = areaFixtures.filter((fixture) => fixture.status === "Critical").length;
                const totalNotionalEnergy = round(areaFixtures.reduce((sum, fixture) => sum + fixture["Notional Energy"], 0), 3);
                const averageFixtureHealth = average(areaFixtures.map((fixture) => fixture.fixtureHealthPct), 1);

                return {
                    areaName,
                    fixtures: areaFixtures.sort((a, b) => a["Fixture Name"].localeCompare(b["Fixture Name"])),
                    totalFixtures: areaFixtures.length,
                    healthyFixtures,
                    warningFixtures,
                    criticalFixtures,
                    totalNotionalEnergy,
                    averageFixtureHealth,
                    status: classifyStatus(averageFixtureHealth),
                    roomName: areaName,
                    zone: "Lighting",
                    avgHealthScore: averageFixtureHealth,
                    faultyFixtures: criticalFixtures,
                    totalEnergyConsumption: totalNotionalEnergy
                };
            })
            .sort((a, b) => b.totalNotionalEnergy - a.totalNotionalEnergy);

        const circuits = Array.from(
            fixtures.reduce((map, fixture) => {
                const circuitName = fixture["Circuit Name"];
                map.set(circuitName, (map.get(circuitName) || 0) + fixture["Notional Energy"]);
                return map;
            }, new Map())
        )
            .map(([circuitName, totalNotionalEnergy]) => ({
                circuitName,
                totalNotionalEnergy: round(totalNotionalEnergy, 3)
            }))
            .sort((a, b) => b.totalNotionalEnergy - a.totalNotionalEnergy);

        const totals = {
            totalFixtures: fixtures.length,
            healthyFixtures: fixtures.filter((fixture) => fixture.status === "Healthy").length,
            warningFixtures: fixtures.filter((fixture) => fixture.status === "Warning").length,
            criticalFixtures: fixtures.filter((fixture) => fixture.status === "Critical").length,
            totalEnergyConsumption: round(fixtures.reduce((sum, fixture) => sum + fixture["Notional Energy"], 0), 3)
        };

        const averageHealthScore = average(fixtures.map((fixture) => fixture.fixtureHealthPct), 1);
        const operatingAvailability = percentage(totals.healthyFixtures + totals.warningFixtures, totals.totalFixtures);
        const allAlerts = fixtures
            .flatMap((fixture) => fixture.alerts.map((alert) => ({
                fixtureId: fixture.id,
                fixtureName: fixture["Fixture Name"],
                areaName: fixture["Area Name"],
                circuitName: fixture["Circuit Name"],
                label: alert.label,
                severity: alert.severity,
                status: fixture.status
            })))
            .sort((a, b) => {
                const severityScore = { critical: 0, warning: 1 };
                return (severityScore[a.severity] ?? 2) - (severityScore[b.severity] ?? 2);
            });

        const criticalAlerts = allAlerts.filter((alert) => alert.severity === "critical");

        const charts = {
            statusDistribution: {
                labels: ["Healthy", "Warning", "Critical"],
                values: [totals.healthyFixtures, totals.warningFixtures, totals.criticalFixtures]
            },
            areaEnergy: {
                labels: areas.map((area) => area.areaName),
                values: areas.map((area) => area.totalNotionalEnergy)
            },
            areaHealth: {
                labels: areas.map((area) => area.areaName),
                values: areas.map((area) => area.averageFixtureHealth)
            },
            lowestHealthFixtures: {
                labels: [...fixtures]
                    .sort((a, b) => (a.fixtureHealthPct ?? 0) - (b.fixtureHealthPct ?? 0))
                    .slice(0, 8)
                    .map((fixture) => fixture["Fixture Name"]),
                values: [...fixtures]
                    .sort((a, b) => (a.fixtureHealthPct ?? 0) - (b.fixtureHealthPct ?? 0))
                    .slice(0, 8)
                    .map((fixture) => fixture.fixtureHealthPct ?? 0)
            }
        };

        return {
            generatedAt: dataset?.generatedAt || null,
            meta: dataset?.meta || {},
            fixtures,
            areas,
            circuits,
            charts,
            totals,
            totalFixtures: totals.totalFixtures,
            averageHealthScore,
            operatingAvailability,
            criticalRoomsCount: areas.filter((area) => area.criticalFixtures > 0).length,
            recentAlerts: allAlerts,
            criticalAlerts,
            highestConsumingRoom: areas[0]
                ? {
                    roomName: areas[0].areaName,
                    totalEnergyConsumption: areas[0].totalNotionalEnergy
                }
                : null,
            rooms: areas
        };
    }

    window.lightingMonitoringUtils = {
        MAX_LAMP_LIFE,
        HEALTHY_MIN,
        WARNING_MIN,
        classifyStatus,
        clamp,
        computeFixtureHealth,
        percentage,
        round,
        summarizePortfolio,
        toNumber
    };
})();
