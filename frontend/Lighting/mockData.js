window.lightingMonitoringMockData = {
    generatedAt: "2026-03-19T08:30:00+07:00",
    trend: [
        { time: "00:00", energyKwh: 26, healthyFixtures: 47, faultyFixtures: 3, availability: 94 },
        { time: "04:00", energyKwh: 19, healthyFixtures: 46, faultyFixtures: 4, availability: 92 },
        { time: "08:00", energyKwh: 38, healthyFixtures: 48, faultyFixtures: 2, availability: 96 },
        { time: "12:00", energyKwh: 44, healthyFixtures: 47, faultyFixtures: 3, availability: 94 },
        { time: "16:00", energyKwh: 41, healthyFixtures: 45, faultyFixtures: 5, availability: 90 },
        { time: "20:00", energyKwh: 31, healthyFixtures: 46, faultyFixtures: 4, availability: 92 }
    ],
    rooms: [
        {
            roomId: "RM-LH-01",
            roomName: "Main Hall",
            zone: "Production Core",
            fixtures: [
                { fixtureId: "LH-101", fixtureType: "Linear LED", status: "healthy", healthScore: 97, isOperational: true, operatingHours: 4120, energyConsumption: 9.1, powerKw: 0.41, lastInspectionDate: "2026-03-10", lastMaintenanceDate: "2026-02-16", alertFlag: false, remarks: "Stable output" },
                { fixtureId: "LH-102", fixtureType: "High Bay LED", status: "healthy", healthScore: 94, isOperational: true, operatingHours: 4380, energyConsumption: 10.4, powerKw: 0.47, lastInspectionDate: "2026-03-10", lastMaintenanceDate: "2026-02-16", alertFlag: false, remarks: "Normal driver response" },
                { fixtureId: "LH-103", fixtureType: "Linear LED", status: "healthy", healthScore: 92, isOperational: true, operatingHours: 4010, energyConsumption: 8.8, powerKw: 0.39, lastInspectionDate: "2026-03-10", lastMaintenanceDate: "2026-01-29", alertFlag: false, remarks: "No abnormalities" },
                { fixtureId: "LH-104", fixtureType: "Emergency LED", status: "warning", healthScore: 76, isOperational: true, operatingHours: 5280, energyConsumption: 7.1, powerKw: 0.33, lastInspectionDate: "2026-03-09", lastMaintenanceDate: "2025-12-22", alertFlag: true, remarks: "Battery autonomy trending down" },
                { fixtureId: "LH-105", fixtureType: "Linear LED", status: "healthy", healthScore: 95, isOperational: true, operatingHours: 3890, energyConsumption: 9.0, powerKw: 0.4, lastInspectionDate: "2026-03-10", lastMaintenanceDate: "2026-02-03", alertFlag: false, remarks: "Nominal" },
                { fixtureId: "LH-106", fixtureType: "Linear LED", status: "healthy", healthScore: 93, isOperational: true, operatingHours: 3975, energyConsumption: 8.7, powerKw: 0.38, lastInspectionDate: "2026-03-10", lastMaintenanceDate: "2026-02-03", alertFlag: false, remarks: "Nominal" }
            ]
        },
        {
            roomId: "RM-LB-02",
            roomName: "Loading Bay",
            zone: "Logistics",
            fixtures: [
                { fixtureId: "LB-201", fixtureType: "Flood LED", status: "healthy", healthScore: 91, isOperational: true, operatingHours: 4880, energyConsumption: 11.2, powerKw: 0.52, lastInspectionDate: "2026-03-11", lastMaintenanceDate: "2026-01-15", alertFlag: false, remarks: "Good lumen stability" },
                { fixtureId: "LB-202", fixtureType: "Flood LED", status: "faulty", healthScore: 44, isOperational: false, operatingHours: 6120, energyConsumption: 3.2, powerKw: 0.11, lastInspectionDate: "2026-03-11", lastMaintenanceDate: "2025-11-08", alertFlag: true, remarks: "Lamp failure confirmed" },
                { fixtureId: "LB-203", fixtureType: "Linear LED", status: "warning", healthScore: 71, isOperational: true, operatingHours: 5640, energyConsumption: 8.5, powerKw: 0.34, lastInspectionDate: "2026-03-11", lastMaintenanceDate: "2025-12-02", alertFlag: true, remarks: "Abnormal consumption spikes" },
                { fixtureId: "LB-204", fixtureType: "Flood LED", status: "healthy", healthScore: 88, isOperational: true, operatingHours: 4730, energyConsumption: 10.9, powerKw: 0.49, lastInspectionDate: "2026-03-11", lastMaintenanceDate: "2026-01-15", alertFlag: false, remarks: "Normal" },
                { fixtureId: "LB-205", fixtureType: "Emergency LED", status: "faulty", healthScore: 39, isOperational: false, operatingHours: 6010, energyConsumption: 2.5, powerKw: 0.09, lastInspectionDate: "2026-03-11", lastMaintenanceDate: "2025-10-20", alertFlag: true, remarks: "Offline fixture after battery trip" }
            ]
        },
        {
            roomId: "RM-PK-03",
            roomName: "Packing Line A",
            zone: "Packaging",
            fixtures: [
                { fixtureId: "PK-301", fixtureType: "Linear LED", status: "healthy", healthScore: 96, isOperational: true, operatingHours: 3670, energyConsumption: 8.6, powerKw: 0.36, lastInspectionDate: "2026-03-12", lastMaintenanceDate: "2026-02-14", alertFlag: false, remarks: "Normal" },
                { fixtureId: "PK-302", fixtureType: "Linear LED", status: "healthy", healthScore: 95, isOperational: true, operatingHours: 3760, energyConsumption: 8.8, powerKw: 0.37, lastInspectionDate: "2026-03-12", lastMaintenanceDate: "2026-02-14", alertFlag: false, remarks: "Normal" },
                { fixtureId: "PK-303", fixtureType: "Task LED", status: "healthy", healthScore: 93, isOperational: true, operatingHours: 3290, energyConsumption: 6.7, powerKw: 0.29, lastInspectionDate: "2026-03-12", lastMaintenanceDate: "2026-02-07", alertFlag: false, remarks: "Stable beam" },
                { fixtureId: "PK-304", fixtureType: "Task LED", status: "healthy", healthScore: 91, isOperational: true, operatingHours: 3335, energyConsumption: 6.9, powerKw: 0.29, lastInspectionDate: "2026-03-12", lastMaintenanceDate: "2026-02-07", alertFlag: false, remarks: "Stable beam" },
                { fixtureId: "PK-305", fixtureType: "Linear LED", status: "warning", healthScore: 78, isOperational: true, operatingHours: 4570, energyConsumption: 7.4, powerKw: 0.31, lastInspectionDate: "2026-03-12", lastMaintenanceDate: "2025-12-18", alertFlag: true, remarks: "Driver temperature elevated" },
                { fixtureId: "PK-306", fixtureType: "Task LED", status: "healthy", healthScore: 92, isOperational: true, operatingHours: 3480, energyConsumption: 6.5, powerKw: 0.28, lastInspectionDate: "2026-03-12", lastMaintenanceDate: "2026-01-11", alertFlag: false, remarks: "Nominal" }
            ]
        },
        {
            roomId: "RM-CS-04",
            roomName: "Cold Storage",
            zone: "Cold Chain",
            fixtures: [
                { fixtureId: "CS-401", fixtureType: "Cold Room LED", status: "warning", healthScore: 73, isOperational: true, operatingHours: 5890, energyConsumption: 9.3, powerKw: 0.43, lastInspectionDate: "2026-03-12", lastMaintenanceDate: "2025-12-05", alertFlag: true, remarks: "Frequent communication retries" },
                { fixtureId: "CS-402", fixtureType: "Cold Room LED", status: "healthy", healthScore: 89, isOperational: true, operatingHours: 5220, energyConsumption: 8.8, powerKw: 0.4, lastInspectionDate: "2026-03-12", lastMaintenanceDate: "2026-01-08", alertFlag: false, remarks: "Stable" },
                { fixtureId: "CS-403", fixtureType: "Emergency LED", status: "faulty", healthScore: 51, isOperational: false, operatingHours: 6480, energyConsumption: 2.1, powerKw: 0.08, lastInspectionDate: "2026-03-12", lastMaintenanceDate: "2025-09-30", alertFlag: true, remarks: "Battery backup failed" },
                { fixtureId: "CS-404", fixtureType: "Cold Room LED", status: "healthy", healthScore: 86, isOperational: true, operatingHours: 5405, energyConsumption: 8.1, powerKw: 0.38, lastInspectionDate: "2026-03-12", lastMaintenanceDate: "2026-01-08", alertFlag: false, remarks: "Stable" },
                { fixtureId: "CS-405", fixtureType: "Cold Room LED", status: "warning", healthScore: 69, isOperational: true, operatingHours: 6170, energyConsumption: 7.8, powerKw: 0.33, lastInspectionDate: "2026-03-12", lastMaintenanceDate: "2025-11-14", alertFlag: true, remarks: "Output fluctuations detected" }
            ]
        },
        {
            roomId: "RM-QA-05",
            roomName: "QA Lab",
            zone: "Quality",
            fixtures: [
                { fixtureId: "QA-501", fixtureType: "Panel LED", status: "healthy", healthScore: 98, isOperational: true, operatingHours: 2860, energyConsumption: 5.1, powerKw: 0.22, lastInspectionDate: "2026-03-13", lastMaintenanceDate: "2026-02-26", alertFlag: false, remarks: "Best in class condition" },
                { fixtureId: "QA-502", fixtureType: "Panel LED", status: "healthy", healthScore: 96, isOperational: true, operatingHours: 2910, energyConsumption: 5.0, powerKw: 0.21, lastInspectionDate: "2026-03-13", lastMaintenanceDate: "2026-02-26", alertFlag: false, remarks: "Stable" },
                { fixtureId: "QA-503", fixtureType: "Task LED", status: "healthy", healthScore: 94, isOperational: true, operatingHours: 2740, energyConsumption: 4.2, powerKw: 0.18, lastInspectionDate: "2026-03-13", lastMaintenanceDate: "2026-02-20", alertFlag: false, remarks: "Stable" },
                { fixtureId: "QA-504", fixtureType: "Emergency LED", status: "healthy", healthScore: 93, isOperational: true, operatingHours: 3120, energyConsumption: 4.6, powerKw: 0.19, lastInspectionDate: "2026-03-13", lastMaintenanceDate: "2026-01-30", alertFlag: false, remarks: "Stable" }
            ]
        },
        {
            roomId: "RM-OF-06",
            roomName: "Administration Office",
            zone: "Support",
            fixtures: [
                { fixtureId: "OF-601", fixtureType: "Panel LED", status: "healthy", healthScore: 92, isOperational: true, operatingHours: 3550, energyConsumption: 6.3, powerKw: 0.28, lastInspectionDate: "2026-03-14", lastMaintenanceDate: "2026-02-10", alertFlag: false, remarks: "Normal" },
                { fixtureId: "OF-602", fixtureType: "Panel LED", status: "healthy", healthScore: 90, isOperational: true, operatingHours: 3485, energyConsumption: 6.1, powerKw: 0.27, lastInspectionDate: "2026-03-14", lastMaintenanceDate: "2026-02-10", alertFlag: false, remarks: "Normal" },
                { fixtureId: "OF-603", fixtureType: "Task LED", status: "healthy", healthScore: 88, isOperational: true, operatingHours: 3760, energyConsumption: 5.4, powerKw: 0.23, lastInspectionDate: "2026-03-14", lastMaintenanceDate: "2026-01-21", alertFlag: false, remarks: "Minor dimming but within limit" },
                { fixtureId: "OF-604", fixtureType: "Task LED", status: "warning", healthScore: 74, isOperational: true, operatingHours: 4460, energyConsumption: 4.9, powerKw: 0.2, lastInspectionDate: "2026-03-14", lastMaintenanceDate: "2025-12-19", alertFlag: true, remarks: "Communication loss recovered twice this week" }
            ]
        },
        {
            roomId: "RM-UT-07",
            roomName: "Utility Corridor",
            zone: "Support",
            fixtures: [
                { fixtureId: "UT-701", fixtureType: "Linear LED", status: "warning", healthScore: 72, isOperational: true, operatingHours: 5340, energyConsumption: 7.4, powerKw: 0.32, lastInspectionDate: "2026-03-14", lastMaintenanceDate: "2025-11-28", alertFlag: true, remarks: "Abnormal consumption pattern" },
                { fixtureId: "UT-702", fixtureType: "Linear LED", status: "faulty", healthScore: 48, isOperational: false, operatingHours: 6620, energyConsumption: 2.9, powerKw: 0.09, lastInspectionDate: "2026-03-14", lastMaintenanceDate: "2025-09-18", alertFlag: true, remarks: "Offline fixture pending replacement" },
                { fixtureId: "UT-703", fixtureType: "Emergency LED", status: "healthy", healthScore: 85, isOperational: true, operatingHours: 4180, energyConsumption: 4.1, powerKw: 0.17, lastInspectionDate: "2026-03-14", lastMaintenanceDate: "2026-01-05", alertFlag: false, remarks: "Stable" },
                { fixtureId: "UT-704", fixtureType: "Linear LED", status: "warning", healthScore: 67, isOperational: true, operatingHours: 5880, energyConsumption: 6.6, powerKw: 0.29, lastInspectionDate: "2026-03-14", lastMaintenanceDate: "2025-11-28", alertFlag: true, remarks: "End-of-life drift" }
            ]
        },
        {
            roomId: "RM-MD-08",
            roomName: "MDB Room",
            zone: "Utilities",
            fixtures: [
                { fixtureId: "MD-801", fixtureType: "Bulkhead LED", status: "healthy", healthScore: 90, isOperational: true, operatingHours: 4220, energyConsumption: 5.8, powerKw: 0.24, lastInspectionDate: "2026-03-15", lastMaintenanceDate: "2026-02-01", alertFlag: false, remarks: "Stable" },
                { fixtureId: "MD-802", fixtureType: "Bulkhead LED", status: "healthy", healthScore: 87, isOperational: true, operatingHours: 4375, energyConsumption: 5.7, powerKw: 0.23, lastInspectionDate: "2026-03-15", lastMaintenanceDate: "2026-02-01", alertFlag: false, remarks: "Stable" },
                { fixtureId: "MD-803", fixtureType: "Emergency LED", status: "warning", healthScore: 79, isOperational: true, operatingHours: 4820, energyConsumption: 4.8, powerKw: 0.18, lastInspectionDate: "2026-03-15", lastMaintenanceDate: "2025-12-15", alertFlag: true, remarks: "Emergency pack health reduced" }
            ]
        }
    ],
    recentAlerts: [
        { roomId: "RM-LB-02", roomName: "Loading Bay", fixtureId: "LB-202", issueType: "Lamp failure", severity: "Critical", timestamp: "2026-03-19 07:42", currentStatus: "Open" },
        { roomId: "RM-CS-04", roomName: "Cold Storage", fixtureId: "CS-401", issueType: "Communication loss", severity: "Warning", timestamp: "2026-03-19 07:15", currentStatus: "Monitoring" },
        { roomId: "RM-UT-07", roomName: "Utility Corridor", fixtureId: "UT-701", issueType: "Abnormal consumption", severity: "Warning", timestamp: "2026-03-19 06:53", currentStatus: "Investigating" },
        { roomId: "RM-LB-02", roomName: "Loading Bay", fixtureId: "LB-205", issueType: "Offline fixture", severity: "Critical", timestamp: "2026-03-19 06:10", currentStatus: "Awaiting replacement" },
        { roomId: "RM-CS-04", roomName: "Cold Storage", fixtureId: "CS-403", issueType: "Ballast/driver issue", severity: "Critical", timestamp: "2026-03-19 05:48", currentStatus: "Open" },
        { roomId: "RM-OF-06", roomName: "Administration Office", fixtureId: "OF-604", issueType: "Communication loss", severity: "Warning", timestamp: "2026-03-19 05:12", currentStatus: "Recovered" }
    ]
};
