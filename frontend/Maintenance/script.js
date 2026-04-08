document.addEventListener("DOMContentLoaded", () => {
    const urlParams = new URLSearchParams(window.location.search);
    const initialView = (urlParams.get("view") || "overview").toLowerCase();
    const state = {
        activeView: ["overview", "utility", "equipment", "non_scheduled"].includes(initialView) ? initialView : "overview",
        overviewMonth: "",
        overviewCategory: "all",
        overviewStatus: "all",
        overviewSearch: "",
        overviewSort: "date_asc",
        selectedMonth: "",
        listMonthFilter: "",
        statusFilter: "all",
        categoryFilter: "all",
        monthlyCategoryFilter: "all",
        locationFilter: "all",
        monthlyLocationFilter: "all",
        inspectionFilter: "all",
        monthlyInspectionFilter: "all",
        monthlyBreakdownMode: "category",
        search: "",
        sort: "due_date_asc",
        year: new Date().getFullYear(),
        monthStatusView: "pending",
        hasAppliedListFilters: false,
        equipmentPriorityFilter: "all",
        equipmentCriticalOnly: "all",
        equipmentWeekFilter: "all",
        nonScheduledMonth: "",
        nonScheduledStatus: "all",
        nonScheduledPriority: "all",
        nonScheduledArea: "all",
        nonScheduledSearch: "",
    };

    const charts = {};

    initialize().catch((error) => {
        console.error("Maintenance initialization failed:", error);
    });

    async function initialize() {
        bindControls();
        await loadActiveView();
    }

    function getApiBase() {
        return `/api/maintenance/${state.activeView}`;
    }

    function resetViewState() {
        state.statusFilter = "all";
        state.categoryFilter = "all";
        state.monthlyCategoryFilter = "all";
        state.locationFilter = "all";
        state.monthlyLocationFilter = "all";
        state.inspectionFilter = "all";
        state.monthlyInspectionFilter = "all";
        state.monthlyBreakdownMode = "category";
        state.search = "";
        state.sort = "due_date_asc";
        state.monthStatusView = "pending";
        state.hasAppliedListFilters = false;
        state.equipmentPriorityFilter = "all";
        state.equipmentCriticalOnly = "all";
        state.equipmentWeekFilter = "all";
    }

    function updateViewCopy() {
        const isOverview = state.activeView === "overview";
        const isEquipment = state.activeView === "equipment";
        const isNonScheduled = state.activeView === "non_scheduled";
        document.body.classList.toggle("maintenance-equipment", isEquipment);
        document.body.dataset.maintenanceView = state.activeView;
        document.getElementById("overview-view")?.classList.toggle("hidden", !isOverview);
        document.getElementById("utility-view")?.classList.toggle("hidden", isOverview || isNonScheduled);
        document.getElementById("non-scheduled-view")?.classList.toggle("hidden", !isNonScheduled);
        document.querySelectorAll("[data-view-tab]").forEach((button) => {
            button.classList.toggle("active", (button.dataset.viewTab || "utility") === state.activeView);
        });
        setText(
            "maintenance-page-title",
            isOverview
                ? "Maintenance Overview"
                : isNonScheduled
                ? "Non-Scheduled Maintenance"
                : (isEquipment ? "Production Equipment Maintenance" : "Utility Maintenance")
        );
        setText(
            "maintenance-page-subtitle",
            isOverview
                ? "Preventive maintenance summary across utility and equipment schedules from the current imported sources"
                : isNonScheduled
                ? "Reactive and corrective maintenance visibility, ready for future D365 work order integration"
                : isEquipment
                ? "Production equipment preventive maintenance planning with risk-based schedule visibility"
                : "Utility preventive maintenance planning and schedule visibility for management review"
        );
        setText("summary-assets-label", isEquipment ? "Total Equipment Assets" : "Total Utility Assets");
        setText("summary-quarter-label", isEquipment ? "Assets Covered This Quarter" : "Tasks This Quarter");
        setText("monthly-section-title", isEquipment ? "Monthly Equipment Maintenance" : "Monthly Maintenance");
        setText(
            "monthly-section-subtitle",
            isEquipment
                ? "Interactive month summary and progress breakdown by risk category or production area"
                : "Interactive month summary and maintenance status breakdown"
        );
        setText("breakdown-title", isEquipment ? "Risk & Area Breakdown" : "Breakdown");
        setText(
            "breakdown-subtitle",
            isEquipment
                ? "Selected month by equipment risk category or production area"
                : "Selected month by utility category or location"
        );
        setText("breakdown-category-chip", isEquipment ? "Risk" : "Category");
        setText("breakdown-location-chip", isEquipment ? "Area" : "Location");
        setText("breakdown-inspection-chip", "Additional Steps");
        setText("timeline-title", isEquipment ? "Annual Equipment Timeline" : "Year Timeline");
        setText(
            "timeline-subtitle",
            isEquipment
                ? "Month-by-month maintenance load across production equipment areas"
                : "Month-by-month preventive maintenance load for the selected year"
        );
        setText("maintenance-list-title", isEquipment ? "Equipment Maintenance List" : "Maintenance List");
        setText(
            "maintenance-list-subtitle",
            isEquipment
                ? "Filter by month, progress, risk category, area, and equipment details"
                : "Filter by month, status, category, location, and machine details"
        );
        setText("filter-category-label", isEquipment ? "Risk Category" : "Category");
        setText("filter-location-label", isEquipment ? "Area" : "Location");
        setText("maintenance-category-heading", isEquipment ? "Risk Category" : "Category");
        setText("maintenance-location-heading", isEquipment ? "Area" : "Location");
        const searchInput = document.getElementById("filter-search");
        if (searchInput) {
            searchInput.placeholder = isEquipment ? "Equipment code or equipment name" : "Machine code or machine name";
        }
    }

    async function loadActiveView() {
        resetViewState();
        updateViewCopy();

        if (state.activeView === "overview") {
            await loadOverviewView();
            return;
        }

        if (state.activeView === "non_scheduled") {
            return;
        }

        const filtersPayload = await fetchJson(`${getApiBase()}/filters`);
        hydrateFilterOptions(filtersPayload);

        const currentMonthValue = `${state.year}-${String(new Date().getMonth() + 1).padStart(2, "0")}`;
        const defaultMonth = (filtersPayload?.months || []).find((month) => month.value === currentMonthValue)?.value
            || filtersPayload?.months?.[0]?.value
            || currentMonthValue;

        state.selectedMonth = defaultMonth;
        state.listMonthFilter = defaultMonth;
        syncMonthInputs();
        syncFilterInputs();
        await loadMaintenanceDashboard();
    }

    function bindControls() {
        document.querySelectorAll("[data-view-tab]").forEach((button) => {
            button.addEventListener("click", async () => {
                const nextView = button.dataset.viewTab || "utility";
                if (nextView === "downtime") {
                    window.location.href = "/Downtime/index.html";
                    return;
                }
                if (nextView === state.activeView) return;
                state.activeView = nextView;
                const nextUrl = new URL(window.location.href);
                nextUrl.searchParams.set("view", nextView);
                window.history.replaceState({}, "", nextUrl);
                await loadActiveView();
            });
        });

        document.getElementById("overview-filter-month")?.addEventListener("change", (event) => {
            state.overviewMonth = event.target.value;
        });
        document.getElementById("overview-filter-category")?.addEventListener("change", (event) => {
            state.overviewCategory = event.target.value;
        });
        document.getElementById("overview-filter-status")?.addEventListener("change", (event) => {
            state.overviewStatus = event.target.value;
        });
        document.getElementById("overview-filter-sort")?.addEventListener("change", (event) => {
            state.overviewSort = event.target.value;
        });
        document.getElementById("overview-filter-search")?.addEventListener("input", debounce((event) => {
            state.overviewSearch = event.target.value.trim();
        }, 250));
        document.getElementById("apply-overview-filters")?.addEventListener("click", async () => {
            await loadOverviewView();
        });

        document.getElementById("month-selector")?.addEventListener("change", async (event) => {
            state.selectedMonth = event.target.value;
            syncMonthInputs();
            await refreshMonthScopedSections();
        });

        document.querySelectorAll("[data-status]").forEach((chip) => {
            chip.addEventListener("click", async () => {
                state.monthStatusView = chip.dataset.status || "all";
                state.statusFilter = state.monthStatusView;
                syncFilterInputs();
                await loadMonthlyDetail();
                if (state.activeView === "equipment") {
                    state.hasAppliedListFilters = true;
                    await loadList();
                }
            });
        });

        document.querySelectorAll("[data-status-target]").forEach((card) => {
            card.addEventListener("click", async () => {
                const status = card.dataset.statusTarget || "all";
                state.monthStatusView = status;
                state.statusFilter = status;
                syncFilterInputs();
                await loadMonthlyDetail();
                if (state.activeView === "equipment") {
                    state.hasAppliedListFilters = true;
                    await loadList();
                }
            });
        });

        document.querySelectorAll("[data-summary-filter]").forEach((card) => {
            card.addEventListener("click", async () => {
                if (state.activeView !== "equipment") return;
                const filter = card.dataset.summaryFilter || "all";
                if (filter === "completion_rate") return;
                state.hasAppliedListFilters = true;
                state.equipmentPriorityFilter = filter === "high_priority" ? "High" : "all";
                state.statusFilter = ({ done: "done", pending: "pending", overdue: "overdue", total: "all" })[filter] || "all";
                await loadList();
            });
        });

        document.getElementById("filter-month")?.addEventListener("change", async (event) => {
            state.listMonthFilter = event.target.value;
        });

        document.getElementById("filter-status")?.addEventListener("change", (event) => {
            state.statusFilter = event.target.value;
            state.monthStatusView = event.target.value;
            syncStatusControls();
            loadMonthlyDetail();
        });

        document.getElementById("filter-category")?.addEventListener("change", (event) => {
            state.categoryFilter = event.target.value;
        });

        document.getElementById("filter-location")?.addEventListener("change", (event) => {
            state.locationFilter = event.target.value;
        });

        document.getElementById("filter-inspection")?.addEventListener("change", (event) => {
            state.inspectionFilter = event.target.value;
        });

        document.getElementById("filter-sort")?.addEventListener("change", (event) => {
            state.sort = event.target.value;
        });

        document.getElementById("filter-search")?.addEventListener("input", debounce((event) => {
            state.search = event.target.value.trim();
        }, 250));

        document.getElementById("apply-maintenance-filters")?.addEventListener("click", async () => {
            state.hasAppliedListFilters = true;
            await loadList();
        });

        document.querySelectorAll("[data-breakdown-mode]").forEach((button) => {
            button.addEventListener("click", async () => {
                state.monthlyBreakdownMode = button.dataset.breakdownMode || "category";
                await loadMonthly();
            });
        });

        document.getElementById("ns-month-selector")?.addEventListener("change", async (event) => {
            state.nonScheduledMonth = event.target.value;
            await loadNonScheduledMonthly();
            await loadNonScheduledList();
        });
        document.getElementById("ns-filter-month")?.addEventListener("change", (event) => {
            state.nonScheduledMonth = event.target.value;
        });
        document.getElementById("ns-filter-status")?.addEventListener("change", (event) => {
            state.nonScheduledStatus = event.target.value;
        });
        document.getElementById("ns-filter-priority")?.addEventListener("change", (event) => {
            state.nonScheduledPriority = event.target.value;
        });
        document.getElementById("ns-filter-area")?.addEventListener("change", (event) => {
            state.nonScheduledArea = event.target.value;
        });
        document.getElementById("ns-filter-search")?.addEventListener("input", debounce((event) => {
            state.nonScheduledSearch = event.target.value.trim();
        }, 250));
        document.getElementById("apply-ns-filters")?.addEventListener("click", async () => {
            await loadNonScheduledList();
        });
    }

    function hydrateFilterOptions(payload) {
        populateSelect("month-selector", payload?.months || [], true);
        populateSelect(
            "filter-month",
            [{ value: "all", label: `All Months ${state.year}` }, ...(payload?.months || [])],
            true
        );
        populateSelect("filter-status", payload?.status_options || []);
        populateSelect("filter-sort", payload?.sort_options || []);
        populateSelect("filter-category", [{ value: "all", label: "All Categories" }, ...(payload?.categories || []).map((value) => ({ value, label: value }))]);
        populateSelect("filter-location", [{ value: "all", label: "All Locations" }, ...(payload?.locations || []).map((value) => ({ value, label: value }))]);
        populateSelect("filter-inspection", payload?.inspection_options || []);
    }

    function hydrateOverviewFilterOptions(payload) {
        populateSelect("overview-filter-month", payload?.filter_options?.months || [], true);
        populateSelect("overview-filter-category", payload?.filter_options?.categories || [], true);
        populateSelect("overview-filter-status", payload?.filter_options?.status_options || [], true);
        populateSelect("overview-filter-sort", payload?.filter_options?.sort_options || [], true);
    }

    function syncOverviewFilterInputs() {
        const month = document.getElementById("overview-filter-month");
        const category = document.getElementById("overview-filter-category");
        const status = document.getElementById("overview-filter-status");
        const sort = document.getElementById("overview-filter-sort");
        const search = document.getElementById("overview-filter-search");

        if (month && state.overviewMonth) month.value = state.overviewMonth;
        if (category) category.value = state.overviewCategory;
        if (status) status.value = state.overviewStatus;
        if (sort) sort.value = state.overviewSort;
        if (search) search.value = state.overviewSearch;
    }

    async function loadOverviewView() {
        const monthInput = document.getElementById("overview-filter-month");
        const categoryInput = document.getElementById("overview-filter-category");
        const statusInput = document.getElementById("overview-filter-status");
        const sortInput = document.getElementById("overview-filter-sort");
        const searchInput = document.getElementById("overview-filter-search");

        if (monthInput?.value) state.overviewMonth = monthInput.value;
        if (categoryInput?.value) state.overviewCategory = categoryInput.value;
        if (statusInput?.value) state.overviewStatus = statusInput.value;
        if (sortInput?.value) state.overviewSort = sortInput.value;
        if (searchInput) state.overviewSearch = searchInput.value.trim();

        if (!state.overviewMonth) {
            state.overviewMonth = `${state.year}-${String(new Date().getMonth() + 1).padStart(2, "0")}`;
        }

        const params = new URLSearchParams({
            month: state.overviewMonth,
            year: String(state.year),
            category: state.overviewCategory,
            status: state.overviewStatus,
            search: state.overviewSearch,
            sort: state.overviewSort,
        });
        const payload = await fetchJson(`/api/maintenance/overview?${params.toString()}`);
        hydrateOverviewFilterOptions(payload);
        state.overviewMonth = payload?.selected_month?.month_key || state.overviewMonth;
        syncOverviewFilterInputs();
        renderOverviewSummary(payload?.summary || {});
        renderOverviewTable(payload?.rows || []);
    }

    function renderOverviewSummary(summary) {
        setText("overview-preventive-required", formatInteger(summary.preventive_maintenance_required));
        setText("overview-scheduled-tasks", formatInteger(summary.scheduled_tasks));
        setText("overview-completed-tasks", formatInteger(summary.completed_tasks));
        setText("overview-pending-tasks", formatInteger(summary.pending_tasks));
        setText("overview-completion-rate", `${formatNumber(summary.completion_rate, 1)}%`);
        setText("overview-inspection-tasks", formatInteger(summary.tasks_requiring_inspection));
        setText("overview-follow-up-tasks", formatInteger(summary.tasks_pending_follow_up));
    }

    function renderOverviewTable(rows) {
        const body = document.getElementById("overview-table-body");
        if (!body) return;

        if (!rows.length) {
            body.innerHTML = '<tr><td colspan="9" class="empty-row">No data available.</td></tr>';
            return;
        }

        body.innerHTML = rows.map((row) => `
            <tr>
                <td>${escapeHtml(row.date || "-")}</td>
                <td>
                    <div class="table-primary-cell">
                        <strong>${escapeHtml(translateDisplayText(row.asset_name || "-"))}</strong>
                        <span class="table-subtext">${escapeHtml(row.asset_code || "-")}</span>
                    </div>
                </td>
                <td>${escapeHtml(row.category || "-")}</td>
                <td>${escapeHtml(row.preventive_maintenance_required || "-")}</td>
                <td><span class="status-pill ${overviewStatusClass(row.status)}">${escapeHtml(row.status || "-")}</span></td>
                <td>${escapeHtml(row.date_provided || "-")}</td>
                <td>${escapeHtml(row.person_in_charge || "-")}</td>
                <td>${escapeHtml(row.inspection_required || "-")}</td>
                <td>${escapeHtml(row.follow_up_status || "-")}</td>
            </tr>
        `).join("");
    }

    async function loadNonScheduledView() {
        const filtersPayload = await fetchJson("/api/maintenance/non_scheduled/filters");
        populateSelect("ns-month-selector", filtersPayload?.months || [], true);
        populateSelect("ns-filter-month", filtersPayload?.months || [], true);
        populateSelect("ns-filter-status", filtersPayload?.status_options || []);
        populateSelect("ns-filter-priority", filtersPayload?.priority_options || []);
        populateSelect("ns-filter-area", [{ value: "all", label: "All Areas" }, ...(filtersPayload?.areas || []).map((value) => ({ value, label: value }))]);

        const currentMonthValue = `${state.year}-${String(new Date().getMonth() + 1).padStart(2, "0")}`;
        state.nonScheduledMonth =
            (filtersPayload?.months || []).find((month) => month.value === currentMonthValue)?.value
            || filtersPayload?.months?.[1]?.value
            || currentMonthValue;
        document.getElementById("ns-month-selector").value = state.nonScheduledMonth;
        document.getElementById("ns-filter-month").value = state.nonScheduledMonth;

        await Promise.all([
            loadNonScheduledSummary(),
            loadNonScheduledMonthly(),
            loadNonScheduledList(),
        ]);
    }

    async function loadNonScheduledSummary() {
        const payload = await fetchJson(`/api/maintenance/non_scheduled/summary?year=${state.year}`);
        const summary = payload?.summary || {};
        setText("ns-open", formatInteger(summary.open_work_orders));
        setText("ns-closed", formatInteger(summary.closed_work_orders));
        setText("ns-overdue", formatInteger(summary.overdue_work_orders));
        setText("ns-high-priority", formatInteger(summary.high_priority_work_orders));
        setText("ns-critical-open", formatInteger(summary.production_critical_open_work_orders));
        setText("ns-week", formatInteger(summary.this_week_work_orders));
        setText("ns-month", formatInteger(summary.this_month_work_orders));
    }

    async function loadNonScheduledMonthly() {
        const payload = await fetchJson(`/api/maintenance/non_scheduled/monthly?month=${encodeURIComponent(state.nonScheduledMonth)}&year=${state.year}`);
        const counts = payload?.counts || {};
        setText("ns-month-open", formatInteger(counts.open));
        setText("ns-month-closed", formatInteger(counts.closed));
        setText("ns-month-overdue", formatInteger(counts.overdue));
        setText("ns-month-priority", formatInteger(counts.high_priority));

        createChart("ns-status-chart", {
            type: "doughnut",
            data: {
                labels: payload?.chart?.labels || ["Open", "Closed", "Overdue"],
                datasets: [{
                    data: payload?.chart?.values || [0, 0, 0],
                    backgroundColor: ["#2563eb", "#10b981", "#ef4444"],
                    borderWidth: 0,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: "bottom",
                        labels: { usePointStyle: true, boxWidth: 10, font: { family: "Inter", size: 11 } },
                    },
                },
                cutout: "64%",
            },
        });

        const areaTarget = document.getElementById("ns-area-breakdown");
        if (areaTarget) {
            const areas = payload?.area_groups || [];
            areaTarget.innerHTML = areas.length
                ? areas.map((group) => `
                    <button type="button" class="stack-item stack-item-button" data-ns-area="${escapeHtml(group.area)}">
                        <div>
                            <strong>${escapeHtml(translateDisplayText(group.area))}</strong>
                            <div class="insight-meta">${formatInteger(group.overdue)} overdue</div>
                        </div>
                        <strong>${formatInteger(group.count)}</strong>
                    </button>
                `).join("")
                : '<div class="empty-state-block">No work order data available.</div>';
            areaTarget.querySelectorAll("[data-ns-area]").forEach((button) => {
                button.addEventListener("click", async () => {
                    state.nonScheduledArea = button.dataset.nsArea || "all";
                    const areaSelect = document.getElementById("ns-filter-area");
                    if (areaSelect) areaSelect.value = state.nonScheduledArea;
                    await loadNonScheduledList();
                });
            });
        }

        const priorityTarget = document.getElementById("ns-priority-breakdown");
        if (priorityTarget) {
            const rows = payload?.priority_groups || [];
            priorityTarget.innerHTML = rows.length
                ? rows.map((group) => `
                    <button type="button" class="stack-item stack-item-button" data-ns-priority="${escapeHtml(group.priority)}">
                        <div>
                            <strong>${escapeHtml(group.priority)}</strong>
                        </div>
                        <strong>${formatInteger(group.count)}</strong>
                    </button>
                `).join("")
                : '<div class="empty-state-block">No priority data available.</div>';
            priorityTarget.querySelectorAll("[data-ns-priority]").forEach((button) => {
                button.addEventListener("click", async () => {
                    state.nonScheduledPriority = button.dataset.nsPriority?.toLowerCase() || "all";
                    const select = document.getElementById("ns-filter-priority");
                    if (select) select.value = state.nonScheduledPriority;
                    await loadNonScheduledList();
                });
            });
        }

        const criticalTarget = document.getElementById("ns-critical-list");
        if (criticalTarget) {
            const rows = payload?.critical_attention || [];
            criticalTarget.innerHTML = rows.length
                ? rows.map((row) => `
                    <button type="button" class="stack-item stack-item-button critical-item" data-ns-machine="${escapeHtml(row.machine_code)}">
                        <div>
                            <strong>${escapeHtml(translateDisplayText(row.machine_name))}</strong>
                            <div class="insight-meta">${escapeHtml(translateDisplayText(row.area))} | ${escapeHtml(row.status)}</div>
                        </div>
                        <strong>${escapeHtml(formatShortDate(row.due_at))}</strong>
                    </button>
                `).join("")
                : '<div class="empty-state-block">No production-critical open work orders.</div>';
            criticalTarget.querySelectorAll("[data-ns-machine]").forEach((button) => {
                button.addEventListener("click", async () => {
                    state.nonScheduledSearch = button.dataset.nsMachine || "";
                    const input = document.getElementById("ns-filter-search");
                    if (input) input.value = state.nonScheduledSearch;
                    await loadNonScheduledList();
                });
            });
        }
    }

    async function loadNonScheduledList() {
        const body = document.getElementById("ns-table-body");
        if (!body) return;
        const params = new URLSearchParams({
            month: state.nonScheduledMonth,
            status: state.nonScheduledStatus,
            priority: state.nonScheduledPriority,
            area: state.nonScheduledArea,
            search: state.nonScheduledSearch,
            year: String(state.year),
        });
        const payload = await fetchJson(`/api/maintenance/non_scheduled/list?${params.toString()}`);
        const rows = payload?.rows || [];
        if (!rows.length) {
            body.innerHTML = '<tr><td colspan="13" class="empty-row">No work orders match the current filters.</td></tr>';
            return;
        }
        body.innerHTML = rows.map((row) => `
            <tr class="${row.status === "Overdue" ? "row-overdue" : ""} ${row.is_production_critical ? "row-critical" : ""}">
                <td>${escapeHtml(row.work_order_id)}</td>
                <td>${escapeHtml(row.maintenance_order_id || "--")}</td>
                <td>${escapeHtml(row.machine_code || "--")}</td>
                <td><div class="table-primary-cell"><strong>${escapeHtml(translateDisplayText(row.machine_name || "--"))}</strong>${row.is_production_critical ? '<span class="table-subtext">Production Critical</span>' : ""}</div></td>
                <td>${escapeHtml(translateDisplayText(row.area || "--"))}</td>
                <td>${escapeHtml(row.description || "--")}</td>
                <td>${escapeHtml(formatShortDate(row.created_at))}</td>
                <td>${escapeHtml(formatShortDate(row.due_at))}</td>
                <td>${escapeHtml(row.status)}</td>
                <td>${escapeHtml(row.priority)}</td>
                <td>${escapeHtml(row.technician || "--")}</td>
                <td>${escapeHtml(`${formatNumber(row.downtime_hours || 0, 1)} hrs`)}</td>
                <td>${escapeHtml(row.remarks || "--")}</td>
            </tr>
        `).join("");
    }

    async function loadMaintenanceDashboard() {
        await Promise.all([
            loadSummary(),
            loadMonthly(false),
        ]);
        await loadList();
        queueDeferredMaintenanceLoads();
    }

    async function refreshMonthScopedSections() {
        await Promise.all([
            loadMonthly(false),
        ]);
        await loadList();
        queueDeferredMaintenanceLoads();
    }

    function queueDeferredMaintenanceLoads() {
        window.setTimeout(() => {
            loadTimeline().catch((error) => console.error("Maintenance timeline load failed:", error));
        }, 0);
        window.setTimeout(() => {
            loadMonthlyDetail().catch((error) => console.error("Maintenance monthly detail load failed:", error));
        }, 0);
    }

    async function loadSummary() {
        const payload = await fetchJson(`${getApiBase()}/summary?year=${state.year}`);
        const summary = payload?.summary || {};
        const isEquipment = state.activeView === "equipment";

        setSummaryCount("summary-due-week", summary.due_this_week);
        setSummaryCount("summary-due-month", summary.due_this_month);
        setText("summary-rate-week", `${formatNumber(summary.completion_rate_week, 1)}%`);
        setText("summary-rate-month", `${formatNumber(summary.completion_rate_month, 1)}%`);
        setSummaryCount("summary-upcoming", summary.upcoming_next_7_days);
        setText("summary-assets", formatInteger(isEquipment ? summary.total_equipment_assets : summary.total_utility_assets));
        setText("summary-quarter", formatInteger(summary.tasks_this_quarter));
        if (isEquipment) {
            const risk = summary.risk_breakdown || {};
            setText(
                "summary-next-month",
                `High: ${formatInteger(risk.high)} | Medium: ${formatInteger(risk.medium)} | Low: ${formatInteger(risk.low)}`
            );
        } else {
            setText("summary-next-month", `Due next month: ${formatInteger(summary.tasks_due_next_month)}`);
        }

    }

    async function loadMonthly(includeDetail = true) {
        const payload = await fetchJson(`${getApiBase()}/monthly?month=${encodeURIComponent(state.selectedMonth)}&year=${state.year}`);
        const counts = payload?.counts || {};
        const isEquipment = state.activeView === "equipment";

        setText("monthly-done", formatInteger(counts.done));
        setText("monthly-pending", formatInteger(counts.pending));
        setText("monthly-overdue", formatInteger(counts.overdue));
        setText("monthly-total", formatInteger(counts.total));

        if (isEquipment) {
            document.getElementById("summary-card-1")?.setAttribute("data-summary-filter", "done");
            document.getElementById("summary-card-2")?.setAttribute("data-summary-filter", "pending");
            document.getElementById("summary-card-3")?.setAttribute("data-summary-filter", "overdue");
            document.getElementById("summary-card-4")?.setAttribute("data-summary-filter", "completion_rate");
            document.getElementById("summary-card-5")?.setAttribute("data-summary-filter", "high_priority");
            setText("summary-label-1", "Done");
            setText("summary-label-2", "Pending");
            setText("summary-label-3", "Overdue");
            setText("summary-label-4", "Completion Rate");
            setText("summary-label-5", "High Priority Open");
            setSummaryCount("summary-due-week", counts.done);
            setSummaryCount("summary-due-month", counts.pending);
            setSummaryCount("summary-rate-week", counts.overdue);
            setText("summary-rate-month", `${formatNumber(counts.completion_rate, 1)}%`);
            setSummaryCount("summary-upcoming", counts.high_priority_open);
            setText("summary-quarter-label", "Total Scheduled This Month");
            setText("summary-quarter", formatInteger(counts.total));
            setText("summary-next-month", `Production-critical open: ${formatInteger(counts.production_critical_open)}`);
            renderCriticalAttention(payload?.critical_attention || []);
            renderTopRiskyEquipment(payload?.top_risky_equipment || []);
        } else {
            document.getElementById("summary-card-1")?.setAttribute("data-summary-filter", "due_this_week");
            document.getElementById("summary-card-2")?.setAttribute("data-summary-filter", "due_this_month");
            document.getElementById("summary-card-3")?.setAttribute("data-summary-filter", "completion_aux");
            document.getElementById("summary-card-4")?.setAttribute("data-summary-filter", "completion_rate");
            document.getElementById("summary-card-5")?.setAttribute("data-summary-filter", "upcoming");
            setText("summary-label-1", "Due This Week");
            setText("summary-label-2", "Due This Month");
            setText("summary-label-3", "Completion Rate Week");
            setText("summary-label-4", "Completion Rate Month");
            setText("summary-label-5", "Upcoming Next 7 Days");
        }

        document.querySelectorAll("[data-status-target]").forEach((card) => {
            card.classList.toggle("active", (card.dataset.statusTarget || "all") === state.monthStatusView);
        });

        createChart("monthly-status-chart", {
            type: "doughnut",
            data: {
                labels: payload?.chart?.labels || ["Done", "Pending", "Overdue"],
                datasets: [{
                    data: payload?.chart?.values || [0, 0, 0],
                    backgroundColor: isEquipment
                        ? ["#0f766e", "#f59e0b", "#ef4444"]
                        : ["#10b981", "#2563eb", "#ef4444"],
                    borderWidth: 0,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: "bottom",
                        labels: {
                            usePointStyle: true,
                            boxWidth: 10,
                            font: { family: "Inter", size: 11 },
                        },
                    },
                },
                cutout: "64%",
            },
        });

        renderMonthlyBreakdown(payload);

        if (includeDetail) {
            await loadMonthlyDetail();
        }
    }

    function renderMonthlyBreakdown(payload) {
        const target = document.getElementById("monthly-breakdown-list");
        if (!target) return;

        document.querySelectorAll("[data-breakdown-mode]").forEach((button) => {
            button.classList.toggle("active", (button.dataset.breakdownMode || "category") === state.monthlyBreakdownMode);
        });

        const isLocationMode = state.monthlyBreakdownMode === "location";
        const isInspectionMode = state.monthlyBreakdownMode === "inspection";
        const groups = isInspectionMode
            ? (payload?.inspection_groups || [])
            : isLocationMode
            ? (payload?.location_groups || [])
            : (payload?.category_groups || []);
        const selectedValue = isInspectionMode
            ? state.monthlyInspectionFilter
            : isLocationMode
            ? state.monthlyLocationFilter
            : state.monthlyCategoryFilter;
        const valueKey = isInspectionMode ? "inspection" : isLocationMode ? "location" : "category";

        if (selectedValue !== "all" && !groups.some((group) => group[valueKey] === selectedValue)) {
            if (isInspectionMode) {
                state.monthlyInspectionFilter = "all";
            } else if (isLocationMode) {
                state.monthlyLocationFilter = "all";
            } else {
                state.monthlyCategoryFilter = "all";
            }
        }

        if (!groups.length) {
            target.innerHTML = '<div class="empty-state-block">No maintenance scheduled for the selected month.</div>';
            return;
        }

        target.innerHTML = groups.map((group) => {
            const itemValue = group[valueKey];
            const isActive = itemValue === (
                isInspectionMode
                    ? state.monthlyInspectionFilter
                    : isLocationMode
                    ? state.monthlyLocationFilter
                    : state.monthlyCategoryFilter
            );
            const groupMeta = state.activeView === "equipment"
                ? `${group.done} done | ${group.pending} pending | ${group.overdue} overdue`
                : `${group.done} done | ${group.pending} pending`;
            return `
                <button
                    type="button"
                    class="stack-item stack-item-button ${isActive ? "active" : ""}"
                    data-breakdown-filter="${escapeHtml(itemValue)}"
                >
                    <div>
                        <strong>${escapeHtml(translateDisplayText(group.label || itemValue))}</strong>
                        <div class="insight-meta">${groupMeta}</div>
                    </div>
                    <strong>${formatInteger(group.count)}</strong>
                </button>
            `;
        }).join("");

        target.querySelectorAll("[data-breakdown-filter]").forEach((button) => {
            button.addEventListener("click", async () => {
                const itemValue = button.dataset.breakdownFilter || "all";
                if (isInspectionMode) {
                    state.monthlyInspectionFilter = state.monthlyInspectionFilter === itemValue ? "all" : itemValue;
                    state.monthlyCategoryFilter = "all";
                    state.monthlyLocationFilter = "all";
                } else if (isLocationMode) {
                    state.monthlyLocationFilter = state.monthlyLocationFilter === itemValue ? "all" : itemValue;
                    state.monthlyCategoryFilter = "all";
                    state.monthlyInspectionFilter = "all";
                } else {
                    state.monthlyCategoryFilter = state.monthlyCategoryFilter === itemValue ? "all" : itemValue;
                    state.monthlyLocationFilter = "all";
                    state.monthlyInspectionFilter = "all";
                }
                await loadMonthlyDetail();
                if (state.activeView === "equipment") {
                    state.hasAppliedListFilters = true;
                    state.categoryFilter = isInspectionMode || isLocationMode ? "all" : state.monthlyCategoryFilter;
                    state.locationFilter = isLocationMode ? state.monthlyLocationFilter : "all";
                    state.inspectionFilter = isInspectionMode ? state.monthlyInspectionFilter : "all";
                    syncFilterInputs();
                    await loadList();
                }
                renderMonthlyBreakdown(payload);
            });
        });
    }

    function renderCriticalAttention(rows) {
        const target = document.getElementById("critical-attention-list");
        if (!target) return;
        target.innerHTML = rows.length
            ? rows.map((row) => `
                <button type="button" class="stack-item stack-item-button critical-item" data-critical-asset="${escapeHtml(row.asset_code)}">
                    <div>
                        <strong>${escapeHtml(translateDisplayText(row.asset_name))}</strong>
                        <div class="insight-meta">${escapeHtml(translateDisplayText(row.location_display || "--"))} | ${escapeHtml(row.status)}</div>
                    </div>
                    <strong>${escapeHtml(row.next_due_date_label || "--")}</strong>
                </button>
            `).join("")
            : '<div class="empty-state-block">No production-critical open items.</div>';
        target.querySelectorAll("[data-critical-asset]").forEach((button) => {
            button.addEventListener("click", async () => {
                state.hasAppliedListFilters = true;
                state.search = button.dataset.criticalAsset || "";
                state.equipmentCriticalOnly = "true";
                const input = document.getElementById("filter-search");
                if (input) input.value = state.search;
                await loadList();
            });
        });
    }

    function renderTopRiskyEquipment(rows) {
        const target = document.getElementById("top-risky-equipment-list");
        if (!target) return;
        target.innerHTML = rows.length
            ? rows.map((row) => `
                <button type="button" class="stack-item stack-item-button ${row.is_production_critical ? "critical-item" : ""}" data-risky-asset="${escapeHtml(row.asset_code)}">
                    <div>
                        <strong>${escapeHtml(translateDisplayText(row.asset_name))}</strong>
                        <div class="insight-meta">${escapeHtml(row.priority)} | ${escapeHtml(row.status)}</div>
                    </div>
                    <strong>${escapeHtml(translateDisplayText(row.category || "--"))}</strong>
                </button>
            `).join("")
            : '<div class="empty-state-block">No open high-risk equipment items.</div>';
        target.querySelectorAll("[data-risky-asset]").forEach((button) => {
            button.addEventListener("click", async () => {
                state.hasAppliedListFilters = true;
                state.search = button.dataset.riskyAsset || "";
                const input = document.getElementById("filter-search");
                if (input) input.value = state.search;
                await loadList();
            });
        });
    }

    async function loadMonthlyDetail() {
        const target = document.getElementById("monthly-detail-list");
        const title = document.getElementById("monthly-detail-title");
        const subtitle = document.getElementById("monthly-detail-subtitle");
        if (!target) return;

        const status = state.monthStatusView || "all";
        const params = new URLSearchParams({
            month: state.selectedMonth,
            year: String(state.year),
            status,
            category: state.monthlyCategoryFilter,
            location: state.monthlyLocationFilter,
            inspection: state.monthlyInspectionFilter,
            search: "",
            sort: "due_date_asc",
        });

        const payload = await fetchJson(`${getApiBase()}/list?${params.toString()}`);
        const rows = payload?.rows || [];

        const statusLabelMap = {
            all: "All",
            done: "Done",
            pending: "Pending",
            overdue: "Overdue",
        };
        const statusLabel = statusLabelMap[status] || "Pending";
        const monthLabel = payload?.selected_month?.label || state.selectedMonth;
        const categoryLabel = state.monthlyCategoryFilter !== "all" ? translateDisplayText(state.monthlyCategoryFilter) : null;
        const locationLabel = state.monthlyLocationFilter !== "all" ? translateDisplayText(state.monthlyLocationFilter) : null;
        const inspectionLabel = state.monthlyInspectionFilter === "inspection"
            ? "With Additional Steps"
            : state.monthlyInspectionFilter === "standard"
            ? "Normal Checklist"
            : null;
        const activeFilterLabel = inspectionLabel || locationLabel || categoryLabel;
        const isEquipment = state.activeView === "equipment";

        if (title) {
            title.textContent = categoryLabel
                ? `${statusLabel} Maintenance • ${categoryLabel}`
                : `${statusLabel} Maintenance`;
        }
        if (subtitle) {
            subtitle.textContent = categoryLabel
                ? `${monthLabel} machine list for ${statusLabel.toLowerCase()} progress in ${categoryLabel}`
                : `${monthLabel} machine list for ${statusLabel.toLowerCase()} progress`;
        }

        if (title) {
            title.textContent = activeFilterLabel
                ? `${statusLabel} ${isEquipment ? "Equipment" : "Maintenance"} - ${activeFilterLabel}`
                : `${statusLabel} ${isEquipment ? "Equipment" : "Maintenance"}`;
        }
        if (subtitle) {
            subtitle.textContent = activeFilterLabel
                ? `${monthLabel} ${isEquipment ? "equipment" : "machine"} list for ${statusLabel.toLowerCase()} progress in ${activeFilterLabel}`
                : `${monthLabel} ${isEquipment ? "equipment" : "machine"} list for ${statusLabel.toLowerCase()} progress`;
        }

        if (!rows.length) {
            target.innerHTML = `<div class="empty-state-block">No ${statusLabel.toLowerCase()} maintenance records for the selected month.</div>`;
            return;
        }

        target.innerHTML = rows.map((row) => `
            <div class="monthly-detail-item">
                <div class="monthly-detail-meta">
                    <span class="monthly-detail-code">${escapeHtml(row.asset_code)}</span>
                    <strong class="monthly-detail-name">${escapeHtml(translateDisplayText(row.asset_name))}</strong>
                    ${row.location_detail ? `<span class="monthly-detail-note">${escapeHtml(translateDisplayText(row.location_detail))}</span>` : ""}
                    ${renderInspectionSubtext(row)}
                </div>
                <div class="monthly-detail-week">
                    <span class="monthly-detail-label">Scheduled Week</span>
                    <strong>${escapeHtml(formatScheduledWeek(row))}</strong>
                </div>
                <div class="monthly-detail-status">
                    <span class="monthly-detail-label">Status</span>
                    <span class="status-pill ${statusClass(row.status)}">${escapeHtml(row.status === "Upcoming" ? "Pending" : row.status)}</span>
                </div>
            </div>
        `).join("");
    }

    async function loadList() {
        const body = document.getElementById("maintenance-table-body");
        if (!body) return;

        const maintenanceColumnCount = state.activeView === "equipment" ? 10 : 7;

        if (!state.hasAppliedListFilters) {
            body.innerHTML = `<tr><td colspan="${maintenanceColumnCount}" class="empty-row">Apply filters to load the maintenance list.</td></tr>`;
            return;
        }

        const params = new URLSearchParams({
            month: state.listMonthFilter || state.selectedMonth,
            year: String(state.year),
            status: state.statusFilter,
            category: state.categoryFilter,
            location: state.locationFilter,
            inspection: state.inspectionFilter,
            search: state.search,
            sort: state.sort,
            aggregate: "asset",
            priority: state.activeView === "equipment" ? state.equipmentPriorityFilter : "all",
            critical: state.activeView === "equipment" ? state.equipmentCriticalOnly : "all",
            week: state.activeView === "equipment" ? state.equipmentWeekFilter : "all",
        });

        const payload = await fetchJson(`${getApiBase()}/list?${params.toString()}`);
        const rows = payload?.rows || [];

        if (!rows.length) {
            body.innerHTML = `<tr><td colspan="${maintenanceColumnCount}" class="empty-row">No maintenance records match the current filters.</td></tr>`;
            return;
        }

        body.innerHTML = rows.map((row) => `
            <tr class="${row.status === "Overdue" ? "row-overdue" : ""} ${row.is_production_critical ? "row-critical" : ""}">
                <td>${escapeHtml(row.asset_code)}</td>
                <td>
                    <div class="table-primary-cell">
                        <strong>${escapeHtml(translateDisplayText(row.asset_name))}</strong>
                        ${row.location_detail ? `<span class="table-subtext">${escapeHtml(translateDisplayText(row.location_detail))}</span>` : ""}
                        ${row.is_production_critical ? '<span class="table-subtext">Production Critical</span>' : ""}
                        ${renderInspectionSubtext(row)}
                      </div>
                  </td>
                  <td>${escapeHtml(translateDisplayText(row.category))}</td>
                  <td>${escapeHtml(translateDisplayText(row.location_display || "--"))}</td>
                  <td>${renderStackedMetricCell(formatFrequencyStack(row))}</td>
                  <td>${renderStackedMetricCell(formatNextDueStack(row))}</td>
                  <td>${renderStackedMetricCell(formatLatestMaintenanceStack(row))}</td>
                  ${state.activeView === "equipment" ? `
                    <td>${escapeHtml(row.status || "--")}</td>
                    <td>${escapeHtml(String(row.days_overdue || 0))}</td>
                    <td>${escapeHtml(row.assigned_technician || "--")}</td>
                  ` : ""}
              </tr>
          `).join("");
      }

    async function loadTimeline() {
        const payload = await fetchJson(`${getApiBase()}/timeline?year=${state.year}&month=${encodeURIComponent(state.selectedMonth)}`);
        const months = payload?.months || [];
        const weeklyProgress = payload?.weekly_progress || [];

        const strip = document.getElementById("timeline-month-strip");
        if (strip) {
            strip.innerHTML = months.map((month) => `
                <button type="button" class="month-chip ${month.month_key === state.selectedMonth ? "active" : ""}" data-month="${month.month_key}">
                    <span>${escapeHtml(month.label)}</span>
                    <span class="month-total">${formatInteger(month.total)}</span>
                </button>
            `).join("");

            strip.querySelectorAll(".month-chip").forEach((button) => {
                button.addEventListener("click", async () => {
                    state.selectedMonth = button.dataset.month || state.selectedMonth;
                    syncMonthInputs();
                    await refreshMonthScopedSections();
                });
            });
        }

        createChart("timeline-chart", {
            type: "bar",
            data: {
                labels: weeklyProgress.map((week) => week.label),
                datasets: [
                    {
                        label: "Scheduled",
                        data: weeklyProgress.map((week) => week.scheduled),
                        backgroundColor: weeklyProgress.map((week) => (week.pending || 0) > 2 ? "#f59e0b" : "#0f766e"),
                        borderRadius: 10,
                    },
                    {
                        label: "Completed",
                        data: weeklyProgress.map((week) => week.completed),
                        backgroundColor: "#10b981",
                        borderRadius: 10,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: "bottom",
                        labels: {
                            usePointStyle: true,
                            boxWidth: 10,
                            font: { family: "Inter", size: 11 },
                        },
                    },
                },
                scales: {
                    x: {
                        grid: { display: false },
                        ticks: { color: "#64748b" },
                    },
                    y: {
                        beginAtZero: true,
                        grid: { color: "rgba(148, 163, 184, 0.14)" },
                        ticks: { color: "#64748b", precision: 0 },
                    },
                },
                onClick: state.activeView === "equipment" ? async (_event, elements, chart) => {
                    const point = elements?.[0];
                    if (!point) return;
                    const selectedWeek = chart.data.labels?.[point.index] || "all";
                    state.equipmentWeekFilter = state.equipmentWeekFilter === selectedWeek ? "all" : selectedWeek;
                    state.hasAppliedListFilters = true;
                    await loadList();
                } : undefined,
            },
        });
    }

    function populateSelect(id, options, useRawLabel = false) {
        const node = document.getElementById(id);
        if (!node) return;
        node.innerHTML = options.map((option) => {
            const value = option.value ?? option;
            const label = useRawLabel ? (option.label ?? value) : (option.label ?? option);
            return `<option value="${escapeHtml(String(value))}">${escapeHtml(translateDisplayText(String(label)))}</option>`;
        }).join("");
    }

    function createChart(id, config) {
        const canvas = document.getElementById(id);
        if (!canvas || typeof Chart === "undefined") return;
        if (charts[id]) charts[id].destroy();
        charts[id] = new Chart(canvas, config);
    }

    function syncMonthInputs() {
        const monthSelector = document.getElementById("month-selector");
        const filterMonth = document.getElementById("filter-month");
        if (monthSelector) monthSelector.value = state.selectedMonth;
        if (filterMonth) filterMonth.value = state.listMonthFilter || state.selectedMonth;
    }

    function syncStatusControls() {
        const filterStatus = document.getElementById("filter-status");
        if (filterStatus) filterStatus.value = state.statusFilter;

        document.querySelectorAll("[data-status]").forEach((chip) => {
            chip.classList.toggle("active", (chip.dataset.status || "all") === state.monthStatusView);
        });

        document.querySelectorAll("[data-status-target]").forEach((card) => {
            card.classList.toggle("active", (card.dataset.statusTarget || "all") === state.monthStatusView);
        });
    }

    function syncFilterInputs() {
        syncStatusControls();
        const category = document.getElementById("filter-category");
        const location = document.getElementById("filter-location");
        const inspection = document.getElementById("filter-inspection");
        const sort = document.getElementById("filter-sort");
        const search = document.getElementById("filter-search");

        if (category) category.value = state.categoryFilter;
        if (location) location.value = state.locationFilter;
        if (inspection) inspection.value = state.inspectionFilter;
        if (sort) sort.value = state.sort;
        if (search) search.value = state.search;
    }

    function setText(id, value) {
        const node = document.getElementById(id);
        if (node) node.textContent = value;
    }

    function setSummaryCount(id, value) {
        const node = document.getElementById(id);
        if (!node) return;
        const label = state.activeView === "equipment" ? "No. of machine" : "No. of utilities";
        node.innerHTML = `${escapeHtml(formatInteger(value))}<span class="summary-subtext">${escapeHtml(label)}</span>`;
    }

    function formatInteger(value) {
        return Number(value || 0).toLocaleString();
    }

    function formatShortDate(value) {
        if (!value) return "--";
        const parsed = new Date(value);
        if (Number.isNaN(parsed.getTime())) return String(value);
        return parsed.toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" });
    }

    function formatNumber(value, digits = 1) {
        const numeric = Number(value || 0);
        return numeric.toLocaleString(undefined, {
            minimumFractionDigits: digits,
            maximumFractionDigits: digits,
        });
    }


    function formatFrequency(row) {
        if (row.frequency_type === "monthly" && row.target_week === "every_week") return "Monthly | Every week";
        if (row.frequency_type === "monthly") return `Monthly | ${row.planned_week}`;
        return `Every ${row.frequency_value} months | ${row.planned_week}`;
    }

    function formatFrequencyStack(row) {
        if (row?.frequency_label_primary || row?.frequency_label_secondary) {
            return {
                primary: row?.frequency_label_primary || "--",
                secondary: row?.frequency_label_secondary || "",
            };
        }
        return {
            primary: row?.planned_week || "--",
            secondary: row?.frequency_type === "monthly"
                ? "Monthly"
                : `Every ${row?.frequency_value ?? "--"} months`,
        };
    }

    function formatNextDueStack(row) {
        return {
            primary: row?.next_due_date_label || "--",
            secondary: row?.next_due_week || "--",
        };
    }

    function formatLatestMaintenanceStack(row) {
        if (!row?.latest_done_week) {
            return {
                primary: "--",
                secondary: "No completed week yet",
            };
        }

        return {
            primary: row.latest_done_week,
            secondary: "",
        };
    }

    function renderStackedMetricCell(value) {
        return `
            <div class="table-metric-cell">
                <strong class="table-metric-primary">${escapeHtml(value?.primary || "--")}</strong>
                ${value?.secondary ? `<span class="table-subtext">${escapeHtml(value.secondary)}</span>` : ""}
            </div>
        `;
    }

    function renderInspectionSubtext(row) {
        if (!row?.inspection_required) return "";
        return `<span class="table-subtext">${escapeHtml(row.inspection_label || "Additional steps required beyond the normal checklist")}</span>`;
    }

    function formatScheduledWeek(row) {
        return translateDisplayText(row?.scheduled_week_label || row?.planned_week || "--");
    }

    function translateDisplayText(value) {
        const text = String(value ?? "").trim();
        if (!text) return "";

        const exactMap = {
            "\u0e40\u0e04\u0e23\u0e37\u0e48\u0e2d\u0e07 UV": "UV Machine",
            "\u0e40\u0e04\u0e23\u0e37\u0e48\u0e2d\u0e07\u0e0b\u0e31\u0e01\u0e1c\u0e49\u0e32 1": "Washing Machine 1",
            "\u0e40\u0e04\u0e23\u0e37\u0e48\u0e2d\u0e07\u0e0b\u0e31\u0e01\u0e1c\u0e49\u0e32 2": "Washing Machine 2",
            "\u0e40\u0e04\u0e23\u0e37\u0e48\u0e2d\u0e07\u0e2d\u0e1a\u0e1c\u0e49\u0e32 1": "Dryer 1",
            "\u0e40\u0e04\u0e23\u0e37\u0e48\u0e2d\u0e07\u0e2d\u0e1a\u0e1c\u0e49\u0e32 2": "Dryer 2",
            "\u0e1a\u0e19\u0e1d\u0e49\u0e32\u0e40\u0e1e\u0e14\u0e32\u0e19\u0e2d\u0e32\u0e04\u0e32\u0e23": "Ceiling Space",
            "\u0e2d\u0e32\u0e04\u0e32\u0e23\u0e1a\u0e2d\u0e22\u0e40\u0e25\u0e2d\u0e23\u0e4c": "Boiler Room",
            "\u0e2b\u0e49\u0e2d\u0e07\u0e1b\u0e31\u0e4a\u0e21\u0e25\u0e21": "Air Compressor Room",
            "\u0e42\u0e23\u0e07\u0e1a\u0e33\u0e1a\u0e31\u0e14\u0e19\u0e49\u0e33\u0e14\u0e35": "Water Treatment Plant",
            "\u0e42\u0e23\u0e07\u0e1a\u0e33\u0e1a\u0e31\u0e14\u0e19\u0e49\u0e33\u0e40\u0e2a\u0e35\u0e22": "Wastewater Treatment Plant",
        };

        if (exactMap[text]) return exactMap[text];

        let translated = text;
        const replacements = [
            ["\u0e23\u0e30\u0e1a\u0e1a\u0e40\u0e15\u0e34\u0e21\u0e2d\u0e32\u0e01\u0e32\u0e28", "Air Intake System"],
            ["\u0e23\u0e30\u0e1a\u0e1a\u0e14\u0e39\u0e14\u0e2d\u0e32\u0e01\u0e32\u0e28", "Exhaust System"],
            ["\u0e2b\u0e49\u0e2d\u0e07 Cooking", "Cooking Room"],
            ["\u0e2b\u0e49\u0e2d\u0e07\u0e25\u0e49\u0e32\u0e07\u0e1d\u0e31\u0e48\u0e07\u0e14\u0e34\u0e1a", "Raw Wash Area"],
            ["\u0e1d\u0e31\u0e48\u0e07\u0e14\u0e34\u0e1a", "Raw Side"],
            ["\u0e2d\u0e32\u0e04\u0e32\u0e23", "Building "],
            ["\u0e2b\u0e49\u0e2d\u0e07", "Room "],
        ];

        replacements.forEach(([source, replacement]) => {
            translated = translated.replaceAll(source, replacement);
        });

        return /[\u0E00-\u0E7F]/.test(translated) ? text : translated;
    }

    function statusClass(status) {
        const normalized = String(status || "").toLowerCase();
        if (normalized === "done") return "status-done";
        if (normalized === "overdue") return "status-overdue";
        return "status-pending";
    }

    function overviewStatusClass(status) {
        const normalized = String(status || "").toLowerCase();
        if (normalized === "completed") return "status-done";
        if (normalized === "pending") return "status-overdue";
        return "status-pending";
    }

    function debounce(callback, wait) {
        let timeoutId = null;
        return (...args) => {
            window.clearTimeout(timeoutId);
            timeoutId = window.setTimeout(() => callback(...args), wait);
        };
    }

    async function fetchJson(url) {
        const response = await fetch(url);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
    }

    function escapeHtml(value) {
        return String(value ?? "").replace(/[&<>"']/g, (match) => ({
            "&": "&amp;",
            "<": "&lt;",
            ">": "&gt;",
            '"': "&quot;",
            "'": "&#39;",
        }[match]));
    }
});
