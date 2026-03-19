(function () {
    const HEALTHY_MIN = 90;
    const WARNING_MIN = 70;

    function round(value, digits = 1) {
        const factor = Math.pow(10, digits);
        return Math.round((value + Number.EPSILON) * factor) / factor;
    }

    function percentage(numerator, denominator) {
        if (!denominator) return 0;
        return round((numerator / denominator) * 100, 1);
    }

    function median(values) {
        if (!values.length) return 0;
        const sorted = [...values].sort((a, b) => a - b);
        const middle = Math.floor(sorted.length / 2);
        if (sorted.length % 2 === 0) {
            return round((sorted[middle - 1] + sorted[middle]) / 2, 1);
        }
        return round(sorted[middle], 1);
    }

    function classifyStatus(score) {
        if (score >= HEALTHY_MIN) return "Healthy";
        if (score >= WARNING_MIN) return "Warning";
        return "Critical";
    }

    function normalizeFixtureStatus(fixture) {
        if (!fixture.isOperational || fixture.status === "faulty") return "Faulty";
        if (fixture.healthScore >= HEALTHY_MIN) return "Healthy";
        if (fixture.healthScore >= WARNING_MIN) return "Warning";
        return "Faulty";
    }

    function getRoomMetrics(room) {
        const fixtures = room.fixtures || [];
        const totalFixtures = fixtures.length;
        const healthyFixtures = fixtures.filter((fixture) => normalizeFixtureStatus(fixture) === "Healthy").length;
        const faultyFixtures = fixtures.filter((fixture) => normalizeFixtureStatus(fixture) === "Faulty").length;
        const activeFixtures = fixtures.filter((fixture) => fixture.isOperational).length;
        const avgHealthScore = round(fixtures.reduce((sum, fixture) => sum + fixture.healthScore, 0) / (totalFixtures || 1), 1);
        const operatingAvailability = percentage(activeFixtures, totalFixtures);
        const totalEnergyConsumption = round(fixtures.reduce((sum, fixture) => sum + fixture.energyConsumption, 0), 1);
        const currentLoadKw = round(fixtures.reduce((sum, fixture) => sum + fixture.powerKw, 0), 2);
        const averageOperatingHours = round(fixtures.reduce((sum, fixture) => sum + fixture.operatingHours, 0) / (totalFixtures || 1), 0);
        const statusScore = Math.min(avgHealthScore, operatingAvailability);

        return {
            roomId: room.roomId,
            roomName: room.roomName,
            zone: room.zone,
            totalFixtures,
            healthyFixtures,
            faultyFixtures,
            activeFixtures,
            operatingAvailability,
            avgHealthScore,
            totalEnergyConsumption,
            currentLoadKw,
            averageOperatingHours,
            status: classifyStatus(statusScore),
            fixtures
        };
    }

    function summarizePortfolio(dataset) {
        const rooms = (dataset.rooms || []).map(getRoomMetrics);
        const totals = rooms.reduce((acc, room) => {
            acc.totalFixtures += room.totalFixtures;
            acc.healthyFixtures += room.healthyFixtures;
            acc.faultyFixtures += room.faultyFixtures;
            acc.activeFixtures += room.activeFixtures;
            acc.totalEnergyConsumption += room.totalEnergyConsumption;
            return acc;
        }, { totalFixtures: 0, healthyFixtures: 0, faultyFixtures: 0, activeFixtures: 0, totalEnergyConsumption: 0 });

        const availability = percentage(totals.activeFixtures, totals.totalFixtures);
        const averageHealthScore = round(rooms.reduce((sum, room) => sum + room.avgHealthScore, 0) / (rooms.length || 1), 1);
        const faultPercentage = percentage(totals.faultyFixtures, totals.totalFixtures);
        const healthScores = rooms.map((room) => room.avgHealthScore);
        const criticalRooms = rooms.filter((room) => room.status === "Critical");
        const bestRoom = [...rooms].sort((a, b) => b.avgHealthScore - a.avgHealthScore)[0] || null;
        const worstRoom = [...rooms].sort((a, b) => a.avgHealthScore - b.avgHealthScore)[0] || null;
        const highestConsumingRoom = [...rooms].sort((a, b) => b.totalEnergyConsumption - a.totalEnergyConsumption)[0] || null;
        const lowestConsumingRoom = [...rooms].sort((a, b) => a.totalEnergyConsumption - b.totalEnergyConsumption)[0] || null;
        const trend = dataset.trend || [];
        const latestTrendPoint = trend[trend.length - 1] || { energyKwh: 0 };

        return {
            rooms,
            totals: {
                ...totals,
                totalEnergyConsumption: round(totals.totalEnergyConsumption, 1)
            },
            operatingAvailability: availability,
            averageHealthScore,
            faultPercentage,
            meanAvailability: availability,
            medianRoomHealthScore: median(healthScores),
            criticalRoomsCount: criticalRooms.length,
            bestRoom,
            worstRoom,
            highestConsumingRoom,
            lowestConsumingRoom,
            trend,
            recentAlerts: dataset.recentAlerts || [],
            latestTrendPoint
        };
    }

    window.lightingMonitoringUtils = {
        HEALTHY_MIN,
        WARNING_MIN,
        classifyStatus,
        getRoomMetrics,
        summarizePortfolio,
        percentage,
        round
    };
})();
