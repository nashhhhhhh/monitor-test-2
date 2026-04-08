from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from maintenance_service import (
    build_equipment_dataset,
    build_utility_dataset,
    clean_text,
    get_equipment_maintenance_last_synced,
    get_maintenance_last_synced,
)


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PROJECTION_TARGET_HOURS = 24
PROJECTION_FREEZER_TEMP_LIMIT = -18

PERIOD_CONFIG = {
    "next_week": {"label": "Next Week", "days": 7},
    "next_month": {"label": "Next Month", "days": 30},
    "quarter": {"label": "Quarter", "days": 90},
}

TAB_META = {
    "overview": {
        "title": "Projection & Forecasting",
        "subtitle": "Forward-looking maintenance workload, energy, water, and downtime outlook using the current dashboard data.",
    },
    "freezer": {
        "title": "Spiral Blast Freezer Projection",
        "subtitle": "Projected maintenance demand, energy use, and temperature drift for freezer-related systems.",
    },
    "water": {
        "title": "Water & Wastewater Projection",
        "subtitle": "Projected maintenance load, flow demand, water volume, and operational imbalance across water systems.",
    },
    "mdb": {
        "title": "MDB / Power Projection",
        "subtitle": "Projected maintenance workload, electrical energy use, and abnormal spike risk for MDB and power assets.",
    },
    "boiler": {
        "title": "Boiler & Compressor Projection",
        "subtitle": "Projected maintenance workload, utility energy demand, and steam / air load outlook for boiler and compressor assets.",
    },
}

TAB_SOURCE_FILES = {
    "overview": [
        "mdb_emdb.csv", "mdb6_energy.csv", "mdb7_energy.csv", "mdb8_energy.csv", "mdb9_energy.csv", "mdb10_energy.csv",
        "FIT-103-ROWaterSupply_Total.csv", "FIT-102-SoftWaterSupply-01_Total.csv", "FIT-104-SoftWaterSupply-02_Total.csv",
        "EffluentPump_Total.csv", "_RawWaterWastePump-01_Total.csv", "_RawWasteWater_Temp.csv", "PMG-WWTP_Energy.csv",
        "_PM-WWTP-CONTROL-PANEL_Energy.csv", "boiler_gas_total.csv", "boiler_directsteam_meterflow_total.csv",
        "boiler_indirectsteam_meterflow.csv", "boiler_direct_energy.csv", "boiler_indirect_energy.csv",
        "aircompressor_energy.csv", "airmeter_flow.csv", "air_dewpoint.csv", "sbf_spiral1_Data.csv", "sbf_spiral2_Data.csv", "sbf_spiral3_Data.csv",
    ],
    "freezer": ["sbf_spiral1_Data.csv", "sbf_spiral2_Data.csv", "sbf_spiral3_Data.csv"],
    "water": [
        "FIT-103-ROWaterSupply_Total.csv", "FIT-102-SoftWaterSupply-01_Total.csv", "FIT-104-SoftWaterSupply-02_Total.csv",
        "EffluentPump_Total.csv", "_RawWaterWastePump-01_Total.csv", "_RawWasteWater_Temp.csv",
        "PMG-WWTP_Energy.csv", "_PM-WWTP-CONTROL-PANEL_Energy.csv",
    ],
    "mdb": ["mdb_emdb.csv", "mdb6_energy.csv", "mdb7_energy.csv", "mdb8_energy.csv", "mdb9_energy.csv", "mdb10_energy.csv"],
    "boiler": [
        "boiler_gas_total.csv", "boiler_directsteam_meterflow_total.csv", "boiler_indirectsteam_meterflow.csv",
        "boiler_direct_energy.csv", "boiler_indirect_energy.csv", "aircompressor_energy.csv", "airmeter_flow.csv", "air_dewpoint.csv",
    ],
}

_PROJECTION_CACHE = {}
_PROJECTION_CACHE_MAX = 24
_NUMERIC_SERIES_CACHE = {}
_NUMERIC_SERIES_CACHE_MAX = 48
_FREEZER_UNITS_CACHE = {}


def normalize_projection_period(value: str | None) -> str:
    cleaned = clean_text(value)
    normalized = cleaned.lower().replace(" ", "_") if cleaned else "next_month"
    return normalized if normalized in PERIOD_CONFIG else "next_month"


def get_projection_window(period: str, today=None):
    today = today or datetime.now().date()
    config = PERIOD_CONFIG[period]
    return today, today + timedelta(days=config["days"] - 1), config


def parse_iso_date(value):
    parsed = pd.to_datetime(value, errors="coerce")
    return None if pd.isna(parsed) else parsed.date()


def parse_dashboard_timestamp(value):
    if value is None or pd.isna(value):
        return pd.NaT
    cleaned = str(value).replace(" ICT", "").strip()
    parsed = pd.to_datetime(cleaned, format="%d-%b-%y %I:%M:%S %p", errors="coerce")
    if pd.isna(parsed):
        parsed = pd.to_datetime(cleaned, dayfirst=True, errors="coerce")
    return parsed


def normalize_projection_key(value):
    return "".join(ch for ch in str(value).strip().lower() if ch.isalnum())


def normalize_text_blob(*parts) -> str:
    return " ".join(clean_text(part) or "" for part in parts).strip().lower()


def format_tasks(value):
    return "--" if value is None else f"{int(round(float(value))):,}"


def format_hours(value):
    return "--" if value is None else f"{float(value):,.1f} hrs"


def format_percent(value):
    return "--" if value is None else f"{float(value):,.1f}%"


def format_value(value, unit="", digits=1):
    if value is None:
        return "No data available"
    return f"{float(value):,.{digits}f} {unit}".strip()


def format_week_range(start, end):
    return f"{start.strftime('%d %b')} - {end.strftime('%d %b')}"


def safe_divide(numerator, denominator, digits=3):
    if numerator is None or denominator in (None, 0):
        return None
    try:
        if float(denominator) == 0:
            return None
        return round(float(numerator) / float(denominator), digits)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def load_numeric_timeseries(file_name, preferred_value_names=None):
    path = DATA_DIR / file_name
    if not path.exists():
        return pd.DataFrame(columns=["dt", "value"])
    preferred = [normalize_projection_key(name) for name in (preferred_value_names or [])]
    cache_signature = (file_name, tuple(preferred), path.stat().st_mtime)
    cached = _NUMERIC_SERIES_CACHE.get(cache_signature)
    if cached is not None:
        return cached

    for skiprows in (0, 1, 2):
        try:
            df = pd.read_csv(path, skiprows=skiprows, encoding="utf-8-sig")
            df.columns = [str(col).strip().replace("\ufeff", "") for col in df.columns]
        except Exception:
            continue

        normalized = {normalize_projection_key(col): col for col in df.columns if str(col).strip()}
        time_col = next((original for key, original in normalized.items() if key in {"timestamp", "time", "datetime", "date"} or "timestamp" in key), None)
        if not time_col:
            continue

        value_col = next((normalized[name] for name in preferred if name in normalized), None)
        if value_col is None:
            value_col = next((original for key, original in normalized.items() if "timestamp" not in key and key not in {"time", "datetime", "date", "status", "trendflags"}), None)
        if value_col is None:
            continue

        working = df[[time_col, value_col]].copy()
        working["dt"] = working[time_col].apply(parse_dashboard_timestamp)
        working["value"] = pd.to_numeric(working[value_col], errors="coerce")
        working = working.dropna(subset=["dt", "value"]).sort_values("dt")
        if not working.empty:
            result = working[["dt", "value"]].reset_index(drop=True)
            while len(_NUMERIC_SERIES_CACHE) >= _NUMERIC_SERIES_CACHE_MAX:
                _NUMERIC_SERIES_CACHE.pop(next(iter(_NUMERIC_SERIES_CACHE)))
            _NUMERIC_SERIES_CACHE[cache_signature] = result
            return result

    return pd.DataFrame(columns=["dt", "value"])


def build_daily_totals(series_df):
    if series_df.empty:
        return []
    ordered = series_df.sort_values("dt").copy()
    daily = ordered.assign(date=ordered["dt"].dt.date).groupby("date")["value"].agg(["min", "max"]).reset_index()
    daily["total"] = (daily["max"] - daily["min"]).clip(lower=0)
    return daily["total"].tolist()


def calculate_cumulative_projection(series_df):
    if series_df.empty:
        return {"projected_day": None, "latest_dt": None, "previous_day_total": None, "baseline_7d": None, "daily_totals": []}

    ordered = series_df.sort_values("dt").copy()
    latest_dt = pd.Timestamp(ordered.iloc[-1]["dt"])
    same_day = ordered[ordered["dt"].dt.date == latest_dt.date()].copy()
    if same_day.empty:
        return {"projected_day": None, "latest_dt": latest_dt, "previous_day_total": None, "baseline_7d": None, "daily_totals": []}

    elapsed_hours = max((pd.Timestamp(same_day.iloc[-1]["dt"]) - pd.Timestamp(same_day.iloc[0]["dt"])).total_seconds() / 3600, 0.25)
    actual_total = max(float(same_day.iloc[-1]["value"]) - float(same_day.iloc[0]["value"]), 0.0)
    projected_day = round((actual_total / elapsed_hours) * PROJECTION_TARGET_HOURS, 3)
    daily_totals = build_daily_totals(ordered)
    previous_day_total = float(daily_totals[-2]) if len(daily_totals) >= 2 else None
    baseline_window = daily_totals[-8:-1] if len(daily_totals) > 1 else daily_totals[-1:]
    baseline_7d = round(float(sum(baseline_window) / len(baseline_window)), 3) if baseline_window else None
    return {
        "projected_day": projected_day,
        "latest_dt": latest_dt,
        "previous_day_total": round(previous_day_total, 3) if previous_day_total is not None else None,
        "baseline_7d": baseline_7d,
        "daily_totals": daily_totals,
    }


def project_counter_period(series_df, period_days):
    projection = calculate_cumulative_projection(series_df)
    daily_totals = projection["daily_totals"]
    baseline_daily = None
    if daily_totals:
        sample = daily_totals[-7:] if len(daily_totals) >= 7 else daily_totals
        baseline_daily = float(sum(sample) / len(sample))
    if baseline_daily is None:
        baseline_daily = projection["projected_day"]
    period_projected = round(baseline_daily * period_days, 3) if baseline_daily is not None else None
    avg_hourly = round(baseline_daily / 24, 3) if baseline_daily is not None else None
    return {
        "period_projected": period_projected,
        "avg_hourly": avg_hourly,
        "baseline_7d": projection["baseline_7d"],
        "latest_dt": projection["latest_dt"],
    }


def calculate_trend_projection(series_df, forecast_hours=1, points=3):
    if series_df.empty:
        return {"latest": None, "projected": None, "slope_per_hour": None, "latest_dt": None, "stddev": None}
    ordered = series_df.sort_values("dt").dropna(subset=["value"]).copy()
    recent = ordered.tail(points)
    latest_dt = pd.Timestamp(ordered.iloc[-1]["dt"])
    latest = float(ordered.iloc[-1]["value"])
    stddev = float(ordered.tail(min(12, len(ordered)))["value"].std()) if len(ordered) >= 2 else None
    if len(recent) < 2:
        return {"latest": round(latest, 3), "projected": None, "slope_per_hour": None, "latest_dt": latest_dt, "stddev": round(stddev, 3) if stddev is not None else None}

    delta_hours = max((pd.Timestamp(recent.iloc[-1]["dt"]) - pd.Timestamp(recent.iloc[0]["dt"])).total_seconds() / 3600, 1 / 60)
    slope_per_hour = (float(recent.iloc[-1]["value"]) - float(recent.iloc[0]["value"])) / delta_hours
    projected = float(recent.iloc[-1]["value"]) + (slope_per_hour * forecast_hours)
    return {
        "latest": round(float(recent.iloc[-1]["value"]), 3),
        "projected": round(projected, 3),
        "slope_per_hour": round(slope_per_hour, 3),
        "latest_dt": latest_dt,
        "stddev": round(stddev, 3) if stddev is not None else None,
    }


def calculate_threshold_forecast(current_value, slope_per_hour, upper_limit=None):
    if current_value is None or slope_per_hour is None or upper_limit is None:
        return None
    if slope_per_hour <= 0 or current_value >= upper_limit:
        return None
    hours = (upper_limit - current_value) / slope_per_hour
    return round(hours, 2) if hours > 0 else None


def is_freezer_item(item):
    text = normalize_text_blob(item.get("asset_code"), item.get("asset_name"), item.get("category"), item.get("location_display"))
    return any(keyword in text for keyword in ["freezer", "spiral", "refrigeration", "condenser"])


def is_water_item(item):
    text = normalize_text_blob(item.get("asset_code"), item.get("asset_name"), item.get("category"), item.get("location_display"), item.get("location_detail"))
    return "water treatment plant" in text or "wastewater treatment plant" in text or any(keyword in text for keyword in ["pump", "filter", "blower", "resin", "ro", "wastewater", "effluent"])


def is_mdb_item(item):
    text = normalize_text_blob(item.get("asset_code"), item.get("asset_name"), item.get("category"), item.get("location_display"), item.get("location_detail"))
    return "mdb" in text or "distribution board" in text or "transformer" in text or "main electrical control room" in text or "electrical" in text or "power" in text


def is_boiler_item(item):
    text = normalize_text_blob(item.get("asset_code"), item.get("asset_name"), item.get("category"), item.get("location_display"), item.get("location_detail"))
    return "boiler building" in text or "air pump room" in text or any(keyword in text for keyword in ["boiler", "air compressor", "compressor", "air dryer", "tank 75q", "tank 300q"])


def item_matches_tab(tab, item):
    if tab == "overview":
        return True
    if tab == "freezer":
        return is_freezer_item(item)
    if tab == "water":
        return is_water_item(item)
    if tab == "mdb":
        return is_mdb_item(item)
    if tab == "boiler":
        return is_boiler_item(item)
    return False


def estimate_scheduled_hours(item):
    text = normalize_text_blob(item.get("asset_name"), item.get("category"), item.get("location_display"))
    if item.get("is_production_critical"):
        return 4.0
    if is_freezer_item(item):
        return 4.0
    if is_boiler_item(item):
        return 4.0 if "boiler" in text else 2.0
    if is_mdb_item(item):
        return 2.0
    if is_water_item(item):
        return 2.0 if any(keyword in text for keyword in ["pump", "blower"]) else 1.0
    risk = clean_text(item.get("risk_level")) or clean_text(item.get("category")) or ""
    if "high" in risk.lower():
        return 4.0
    if "medium" in risk.lower():
        return 2.0
    return 1.0


def estimate_scheduled_downtime(item):
    text = normalize_text_blob(item.get("asset_name"), item.get("category"), item.get("location_display"))
    if item.get("is_production_critical"):
        return 2.5
    if is_freezer_item(item):
        return 2.0
    if is_boiler_item(item):
        return 2.0 if "boiler" in text else 1.5
    if is_mdb_item(item):
        return 1.5
    if is_water_item(item):
        return 1.5 if any(keyword in text for keyword in ["pump", "blower"]) else 1.0
    risk = clean_text(item.get("risk_level")) or clean_text(item.get("category")) or ""
    if "high" in risk.lower():
        return 2.0
    if "medium" in risk.lower():
        return 1.5
    return 1.0


def compute_completion_rate(scheduled_rows, today):
    historical = [item for item in scheduled_rows if (parse_iso_date(item.get("scheduled_date")) or today) < today]
    if not historical:
        return None
    return round((sum(1 for item in historical if item.get("is_done")) / len(historical)) * 100, 1)


def get_projected_scheduled_rows(rows, start, end):
    return [item for item in rows if (parse_iso_date(item.get("scheduled_date")) or start) >= start and (parse_iso_date(item.get("scheduled_date")) or end) <= end]


def get_current_overdue_rows(rows, today):
    return [item for item in rows if (parse_iso_date(item.get("scheduled_date")) or today) < today and item.get("is_overdue")]


def build_period_buckets(start, end):
    buckets = []
    current = start
    index = 1
    while current <= end:
        bucket_end = min(current + timedelta(days=6), end)
        buckets.append({"label": f"Week {index}", "start": current, "end": bucket_end})
        current = bucket_end + timedelta(days=1)
        index += 1
    return buckets


def make_kpi(label, value, subtext="", tone="blue"):
    return {"label": label, "value": value, "subtext": subtext, "tone": tone}


def add_alert(alerts, severity, title, message):
    alerts.append({"severity": severity, "title": title, "message": message})


def build_value_rows(mapping, unit, digits=1, title_suffix=""):
    rows = []
    for label, value in mapping.items():
        if value is None:
            continue
        rows.append({"label": label, "value": format_value(value, unit, digits), "subtext": title_suffix})
    rows.sort(key=lambda row: float(row["value"].split()[0].replace(",", "")), reverse=True)
    return rows


def get_component_label(tab, item):
    text = normalize_text_blob(item.get("asset_name"), item.get("category"), item.get("subcategory"), item.get("location_display"))
    if tab == "freezer":
        if "condenser" in text:
            return "Condensers"
        if "compressor" in text:
            return "Compressor Units"
        return "Freezer Units"
    if tab == "water":
        if "pump" in text:
            return "Pumps"
        if any(keyword in text for keyword in ["filter", "ro", "resin"]):
            return "Filters"
        if "tank" in text:
            return "Tanks"
        if "blower" in text:
            return "Blowers"
        return "Treatment Units"
    if tab == "mdb":
        if "transformer" in text:
            return "Transformers"
        if "distribution board" in text or "mdb" in text:
            return "MDB"
        return "Electrical Assets"
    if tab == "boiler":
        if "boiler" in text:
            return "Boiler"
        if "compressor" in text:
            return "Air Compressor"
        if "air dryer" in text or "dryer" in text:
            return "Air Dryer"
        if "tank" in text:
            return "Tanks"
        return "Utility Assets"
    return clean_text(item.get("category")) or "Other"


def build_group_rows(entries, limit=6):
    rows = []
    for label, items in entries.items():
        rows.append({
            "label": label,
            "value": f"{len(items)} tasks",
            "subtext": f"{sum(estimate_scheduled_hours(item) for item in items):.1f} hrs manpower | {sum(estimate_scheduled_downtime(item) for item in items):.1f} hrs downtime",
        })
    rows.sort(key=lambda row: int(row["value"].split()[0]), reverse=True)
    return rows[:limit]


def build_top_asset_rows(rows, limit=6):
    grouped = defaultdict(list)
    for item in rows:
        grouped[item.get("asset_code") or item.get("asset_name")].append(item)
    asset_rows = []
    for _, items in grouped.items():
        sample = items[0]
        score = sum(5 for item in items if item.get("is_overdue")) + len(items) * 2 + sum(estimate_scheduled_downtime(item) for item in items) + (4 if any(item.get("is_production_critical") for item in items) else 0)
        asset_rows.append({"label": clean_text(sample.get("asset_name")) or "Unnamed Asset", "value": f"{len(items)} tasks", "subtext": "Production Critical" if any(item.get("is_production_critical") for item in items) else clean_text(sample.get("location_display")) or "General", "score": score})
    asset_rows.sort(key=lambda row: row["score"], reverse=True)
    return [{key: value for key, value in row.items() if key != "score"} for row in asset_rows[:limit]]


def read_freezer_units():
    cache_signature = []
    for file_name in ("sbf_spiral1_Data.csv", "sbf_spiral2_Data.csv", "sbf_spiral3_Data.csv"):
        path = DATA_DIR / file_name
        cache_signature.append(path.stat().st_mtime if path.exists() else None)
    cache_signature = tuple(cache_signature)
    cached = _FREEZER_UNITS_CACHE.get(cache_signature)
    if cached is not None:
        return cached

    units = {}
    latest_dt = None
    for label, file_name in {"Spiral 1": "sbf_spiral1_Data.csv", "Spiral 2": "sbf_spiral2_Data.csv", "Spiral 3": "sbf_spiral3_Data.csv"}.items():
        path = DATA_DIR / file_name
        if not path.exists():
            continue
        try:
            df = pd.read_csv(path, skiprows=[1], encoding="latin1")
        except Exception:
            continue
        df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
        if "unnamed:_11" in df.columns:
            df.rename(columns={"unnamed:_11": "use_kwh"}, inplace=True)
        if "time" not in df.columns:
            continue
        df["dt"] = pd.to_datetime(df["time"], format="%H:%M:%S", errors="coerce")
        df = df.dropna(subset=["dt"]).sort_values("dt")
        for column in ["tef01", "tef02", "runtime", "use_kwh"]:
            if column in df.columns:
                df[column] = pd.to_numeric(df[column], errors="coerce")
        if df.empty:
            continue
        top = calculate_trend_projection(df[["dt", "tef01"]].rename(columns={"tef01": "value"}).dropna(), 1) if "tef01" in df.columns else {"latest": None, "projected": None, "slope_per_hour": None, "stddev": None}
        energy = calculate_cumulative_projection(df[["dt", "use_kwh"]].rename(columns={"use_kwh": "value"}).dropna()).get("projected_day") if "use_kwh" in df.columns else None
        units[label] = {
            "top_temp": top.get("latest"),
            "top_temp_projected": top.get("projected"),
            "temp_stddev": top.get("stddev"),
            "threshold_hours": calculate_threshold_forecast(top.get("latest"), top.get("slope_per_hour"), PROJECTION_FREEZER_TEMP_LIMIT),
            "energy_day": energy,
        }
        latest_dt = max(latest_dt, df["dt"].max()) if latest_dt is not None else df["dt"].max()
    result = (units, latest_dt)
    _FREEZER_UNITS_CACHE.clear()
    _FREEZER_UNITS_CACHE[cache_signature] = result
    return result


def build_projection_cache_signature(tab, period, year):
    signature = [tab, period, year, get_maintenance_last_synced(), get_equipment_maintenance_last_synced()]
    for file_name in TAB_SOURCE_FILES.get(tab, []):
        path = DATA_DIR / file_name
        signature.append(path.stat().st_mtime if path.exists() else None)
    return tuple(signature)


def build_projection_payload(tab="overview", period=None):
    today = datetime.now().date()
    normalized_tab = tab if tab in TAB_META else "overview"
    normalized_period = normalize_projection_period(period)
    cache_signature = build_projection_cache_signature(normalized_tab, normalized_period, today.year)
    if cache_signature in _PROJECTION_CACHE:
        return _PROJECTION_CACHE[cache_signature]

    start, end, period_config = get_projection_window(normalized_period, today)
    period_days = period_config["days"]
    utility_dataset = build_utility_dataset(today.year)
    equipment_dataset = build_equipment_dataset(today.year)
    scheduled_rows = [*[item for item in utility_dataset["occurrences"] if item_matches_tab(normalized_tab, item)], *[item for item in equipment_dataset["occurrences"] if item_matches_tab(normalized_tab, item)]]
    projected_scheduled = get_projected_scheduled_rows(scheduled_rows, start, end)
    overdue_rows = get_current_overdue_rows(scheduled_rows, today)
    completion_rate = compute_completion_rate(scheduled_rows, today)
    projected_completed = int(round(len(projected_scheduled) * (completion_rate / 100.0))) if completion_rate is not None else None
    projected_pending = len(projected_scheduled) - projected_completed if projected_completed is not None else None
    downtime_hours = sum(estimate_scheduled_downtime(item) for item in projected_scheduled) if projected_scheduled else None
    critical_due = sum(1 for item in projected_scheduled if item.get("is_production_critical"))
    buckets = build_period_buckets(start, end)
    scheduled_by_bucket = [len([item for item in projected_scheduled if bucket["start"] <= (parse_iso_date(item.get("scheduled_date")) or bucket["start"]) <= bucket["end"]]) for bucket in buckets]
    downtime_by_bucket = [round(sum(estimate_scheduled_downtime(item) for item in projected_scheduled if bucket["start"] <= (parse_iso_date(item.get("scheduled_date")) or bucket["start"]) <= bucket["end"]), 2) for bucket in buckets]

    component_groups = defaultdict(list)
    area_groups = defaultdict(list)
    system_groups = defaultdict(list)
    for item in projected_scheduled:
        if is_freezer_item(item):
            system_label = "Freezer"
        elif is_water_item(item):
            system_label = "Water & Wastewater"
        elif is_mdb_item(item):
            system_label = "MDB / Power"
        elif is_boiler_item(item):
            system_label = "Boiler & Compressor"
        else:
            system_label = clean_text(item.get("category")) or "Other"
        component_groups[get_component_label(normalized_tab, item)].append(item)
        area_groups[clean_text(item.get("location_display")) or "Unassigned"].append(item)
        system_groups[system_label].append(item)

    alerts = []
    if overdue_rows:
        add_alert(alerts, "warning" if len(overdue_rows) < 5 else "critical", "Projected overdue backlog", f"{len(overdue_rows)} maintenance task(s) are already overdue for this projection view.")
    if critical_due:
        add_alert(alerts, "critical", "Production-critical tasks due", f"{critical_due} Combi Oven / Brattpan task(s) are due in the selected period.")
    if downtime_hours and downtime_hours >= 8:
        add_alert(alerts, "warning", "Downtime exposure is elevated", f"Projected downtime exposure is {downtime_hours:.1f} hours in the selected period.")

    maintenance_label = {
        "overview": "Projected Total Maintenance",
        "freezer": "Projected Freezer Maintenance Tasks",
        "water": "Projected Maintenance Tasks",
        "mdb": "Projected MDB / Power Maintenance Tasks",
        "boiler": "Projected Boiler & Compressor Maintenance Tasks",
    }[normalized_tab]
    overdue_label = {
        "overview": "Projected Overdue Tasks",
        "freezer": "Overdue Freezer Tasks",
        "water": "Overdue Water / Wastewater Tasks",
        "mdb": "Overdue Electrical Tasks",
        "boiler": "Overdue Tasks",
    }[normalized_tab]

    kpis = [
        make_kpi(maintenance_label, format_tasks(len(projected_scheduled)), "Scheduled maintenance due in the selected period", "blue"),
        make_kpi(overdue_label, format_tasks(len(overdue_rows)), "Current maintenance backlog carried into the period", "red"),
        make_kpi("Forecast Completion Rate", format_percent(completion_rate) if completion_rate is not None else "No data available", "Based on observed completion history from scheduled maintenance", "green"),
        make_kpi("Projected Downtime Hours", format_hours(downtime_hours) if downtime_hours is not None else "No data available", "Estimated from maintenance task mix by system", "amber"),
    ]

    charts = []
    if any(scheduled_by_bucket):
        charts.append({"title": "Weekly Projected Maintenance Load", "subtitle": "Projected scheduled maintenance by week within the selected period.", "type": "bar", "compact": False, "labels": [bucket["label"] for bucket in buckets], "datasets": [{"label": "Projected Tasks", "data": scheduled_by_bucket, "backgroundColor": "#2563eb"}]})
    if projected_completed is not None and projected_pending is not None:
        charts.append({"title": "Pending vs Completed Forecast", "subtitle": "Projected split between completed, pending, and overdue maintenance work.", "type": "doughnut", "compact": True, "labels": ["Completed", "Pending", "Overdue"], "datasets": [{"data": [projected_completed, projected_pending, len(overdue_rows)], "backgroundColor": ["#16a34a", "#0ea5e9", "#dc2626"]}]})

    breakdowns = [
        {"title": "Projection by System / Category", "rows": build_group_rows(system_groups) or [{"label": "No data available", "value": "--", "subtext": "No scheduled maintenance matched this period."}]},
        {"title": "Projection by Area / Location", "rows": build_group_rows(area_groups) or [{"label": "No data available", "value": "--", "subtext": "No area breakdown available for this period."}]},
        {"title": "Critical Equipment Upcoming Load", "rows": build_top_asset_rows([item for item in projected_scheduled if item.get("is_production_critical")], 5) or [{"label": "No data available", "value": "--", "subtext": "No production-critical tasks were found in the selected period."}]},
    ]

    if normalized_tab == "overview":
        mdb_total = sum(project_counter_period(load_numeric_timeseries(file_name, ["Value (kW-hr)", "Value", "kWh"]), period_days)["period_projected"] or 0 for file_name in ["mdb_emdb.csv", "mdb6_energy.csv", "mdb7_energy.csv", "mdb8_energy.csv", "mdb9_energy.csv", "mdb10_energy.csv"]) or None
        water_sources = {
            "RO Water": project_counter_period(load_numeric_timeseries("FIT-103-ROWaterSupply_Total.csv", ["m3", "Value"]), period_days)["period_projected"],
            "Softwater 1": project_counter_period(load_numeric_timeseries("FIT-102-SoftWaterSupply-01_Total.csv", ["m3", "Value"]), period_days)["period_projected"],
            "Softwater 2": project_counter_period(load_numeric_timeseries("FIT-104-SoftWaterSupply-02_Total.csv", ["m3", "Value"]), period_days)["period_projected"],
            "WWTP Treated": project_counter_period(load_numeric_timeseries("EffluentPump_Total.csv", ["Value", "m3"]), period_days)["period_projected"],
            "WWTP Raw Inflow": project_counter_period(load_numeric_timeseries("_RawWaterWastePump-01_Total.csv", ["Value", "m3"]), period_days)["period_projected"],
        }
        water_sources = {k: v for k, v in water_sources.items() if v is not None}
        wwtp_energy = (project_counter_period(load_numeric_timeseries("PMG-WWTP_Energy.csv", ["Value", "Energy"]), period_days)["period_projected"] or 0) + (project_counter_period(load_numeric_timeseries("_PM-WWTP-CONTROL-PANEL_Energy.csv", ["Value", "Energy"]), period_days)["period_projected"] or 0)
        boiler_energy = (project_counter_period(load_numeric_timeseries("boiler_direct_energy.csv", ["Value (kW-hr)", "Value", "kWh"]), period_days)["period_projected"] or 0) + (project_counter_period(load_numeric_timeseries("boiler_indirect_energy.csv", ["Value (kW-hr)", "Value", "kWh"]), period_days)["period_projected"] or 0)
        compressor_energy = project_counter_period(load_numeric_timeseries("aircompressor_energy.csv", ["Value", "Energy", "kWh"]), period_days)["period_projected"]
        freezer_units, _ = read_freezer_units()
        freezer_energy = sum((unit.get("energy_day") or 0) * period_days for unit in freezer_units.values()) or None
        temperature_series = [unit.get("temp_stddev") for unit in freezer_units.values() if unit.get("temp_stddev") is not None]
        wwtp_temp = calculate_trend_projection(load_numeric_timeseries("_RawWasteWater_Temp.csv", ["Value (°C)", "Value", "Temp"]), 1)
        if wwtp_temp.get("stddev") is not None:
            temperature_series.append(wwtp_temp["stddev"])
        temp_risk = max(temperature_series) if temperature_series else None
        energy_by_system = {k: v for k, v in {"MDB / Power": mdb_total, "Water & Wastewater": wwtp_energy or None, "Boiler & Compressor": (boiler_energy + (compressor_energy or 0)) or None, "Freezer": freezer_energy}.items() if v is not None}
        kpis.extend([
            make_kpi("Projected Energy Consumption", format_value(sum(energy_by_system.values()) if energy_by_system else None, "kWh", 0), "Combined projected energy from available power-backed systems", "blue"),
            make_kpi("Projected Water Volume", format_value(sum(water_sources.values()) if water_sources else None, "m3", 0), "Combined projected treated / wastewater volume from available water systems", "cyan"),
            make_kpi("Temperature Deviation Risk", "Elevated" if temp_risk is not None and temp_risk >= 2.5 else ("Normal" if temp_risk is not None else "No data available"), "Based on freezer and wastewater temperature variability", "amber"),
        ])
        if system_groups:
            downtime_by_system = {label: round(sum(estimate_scheduled_downtime(item) for item in items), 2) for label, items in system_groups.items()}
            charts.append({"title": "Projected Downtime by System", "subtitle": "Estimated downtime contribution from maintenance tasks by system.", "type": "bar", "compact": False, "labels": list(downtime_by_system.keys()), "datasets": [{"label": "Downtime Hours", "data": list(downtime_by_system.values()), "backgroundColor": "#7c3aed"}]})
        if energy_by_system:
            charts.append({"title": "Projected Energy by System", "subtitle": "Projected energy consumption for systems with real imported energy data.", "type": "bar", "compact": False, "labels": list(energy_by_system.keys()), "datasets": [{"label": "Projected Energy", "data": list(energy_by_system.values()), "backgroundColor": "#0ea5e9"}]})
        if water_sources:
            charts.append({"title": "Projected Water Volume by System", "subtitle": "Projected water and wastewater volume from the available flow and totalizer datasets.", "type": "bar", "compact": False, "labels": list(water_sources.keys()), "datasets": [{"label": "Projected Volume", "data": list(water_sources.values()), "backgroundColor": "#14b8a6"}]})
    elif normalized_tab == "freezer":
        freezer_units, _ = read_freezer_units()
        energy_rows = {name: (unit.get("energy_day") or 0) * period_days for name, unit in freezer_units.items() if unit.get("energy_day") is not None}
        thresholds = [unit.get("threshold_hours") for unit in freezer_units.values() if unit.get("threshold_hours") is not None]
        temp_std = max([unit.get("temp_stddev") or 0 for unit in freezer_units.values()], default=None)
        kpis.extend([
            make_kpi("High-Risk Freezer Components Due", format_tasks(len(build_top_asset_rows(projected_scheduled))), "Highest projected freezer component workload in the selected period", "purple"),
            make_kpi("Projected Energy Consumption", format_value(sum(energy_rows.values()) if energy_rows else None, "kWh", 0), "Projected from freezer unit kWh traces", "blue"),
            make_kpi("Projected Temperature Trend", format_value(sum(unit.get("top_temp_projected") for unit in freezer_units.values() if unit.get("top_temp_projected") is not None) / max(1, len([1 for unit in freezer_units.values() if unit.get("top_temp_projected") is not None])), "deg C", 1) if freezer_units else "No data available", "Average projected top temperature across freezer units", "cyan"),
            make_kpi("Temperature Deviation Risk", "Elevated" if temp_std is not None and temp_std >= 2.5 else ("Normal" if temp_std is not None else "No data available"), "Based on recent freezer temperature variability", "amber"),
            make_kpi("Projected Time Out of Range", format_value(min(thresholds) if thresholds else None, "hrs", 1), "Estimated time to exceed the -18 deg C limit where trend data exists", "red"),
        ])
        if energy_rows:
            charts.append({"title": "Energy Projection by Freezer Asset", "subtitle": "Projected freezer energy demand from the available spiral freezer kWh traces.", "type": "bar", "compact": False, "labels": list(energy_rows.keys()), "datasets": [{"label": "Projected Energy", "data": list(energy_rows.values()), "backgroundColor": "#7c3aed"}]})
        temp_current = {name: unit.get("top_temp") for name, unit in freezer_units.items() if unit.get("top_temp") is not None}
        temp_projected = {name: unit.get("top_temp_projected") for name, unit in freezer_units.items() if unit.get("top_temp_projected") is not None}
        if temp_current and temp_projected:
            labels = list(temp_current.keys())
            charts.append({"title": "Temperature Projection Trend", "subtitle": "Current vs projected top temperature across the available freezer units.", "type": "bar", "compact": False, "labels": labels, "datasets": [{"label": "Current", "data": [temp_current.get(label) for label in labels], "backgroundColor": "#93c5fd"}, {"label": "Projected +1h", "data": [temp_projected.get(label) for label in labels], "backgroundColor": "#f59e0b"}]})
        breakdowns = [
            {"title": "Projection by Freezer Component / Equipment", "rows": build_group_rows(component_groups) or [{"label": "No data available", "value": "--", "subtext": "No freezer maintenance matched the selected period."}]},
            {"title": "Projection by Area", "rows": build_group_rows(area_groups) or [{"label": "No data available", "value": "--", "subtext": "No area breakdown available for freezer tasks."}]},
            {"title": "Highest Projected Maintenance Load Items", "rows": build_top_asset_rows(projected_scheduled) or [{"label": "No data available", "value": "--", "subtext": "No freezer maintenance assets found for the selected period."}]},
            {"title": "Highest Projected Energy-Consuming Freezer Assets", "rows": build_value_rows(energy_rows, "kWh", 0, f"{period_days}-day projection") or [{"label": "No data available", "value": "--", "subtext": "No freezer energy traces were available."}]},
        ]
    elif normalized_tab == "water":
        wtp = {k: project_counter_period(load_numeric_timeseries(file_name, ["m3", "Value"]), period_days)["period_projected"] for k, file_name in {"RO Water": "FIT-103-ROWaterSupply_Total.csv", "Softwater 1": "FIT-102-SoftWaterSupply-01_Total.csv", "Softwater 2": "FIT-104-SoftWaterSupply-02_Total.csv"}.items()}
        wtp = {k: v for k, v in wtp.items() if v is not None}
        wwtp = {"Treated Volume": project_counter_period(load_numeric_timeseries("EffluentPump_Total.csv", ["Value", "m3"]), period_days)["period_projected"], "Raw Inflow": project_counter_period(load_numeric_timeseries("_RawWaterWastePump-01_Total.csv", ["Value", "m3"]), period_days)["period_projected"]}
        wwtp = {k: v for k, v in wwtp.items() if v is not None}
        flow_rate = safe_divide((sum(wtp.values()) if wtp else 0) + (wwtp.get("Raw Inflow") or 0), period_days * 24, 2) if (wtp or wwtp) else None
        abnormal = "Elevated" if wwtp.get("Treated Volume") and wwtp.get("Raw Inflow") and wwtp["Raw Inflow"] > wwtp["Treated Volume"] * 1.2 else ("Normal" if wwtp else "No data available")
        kpis.extend([
            make_kpi("Critical Pumps / Filters Due", format_tasks(len(build_top_asset_rows(projected_scheduled))), "High-load pumps, filters, tanks, and blowers due in the selected period", "purple"),
            make_kpi("Projected Water Volume", format_value(sum(wtp.values()) if wtp else None, "m3", 0), "Projected WTP treated-water volume", "blue"),
            make_kpi("Projected Wastewater Volume", format_value(wwtp.get("Treated Volume"), "m3", 0), "Projected WWTP treated wastewater volume", "cyan"),
            make_kpi("Projected Flow Rate", format_value(flow_rate, "m3/hr", 2), "Average projected combined water / wastewater flow", "green"),
            make_kpi("Abnormal Volume / Flow Risk", abnormal, "Based on projected raw inflow versus treated output", "amber"),
        ])
        if wtp:
            charts.append({"title": "Water Volume Projection Trend", "subtitle": "Projected treated-water volume by available WTP source.", "type": "bar", "compact": False, "labels": list(wtp.keys()), "datasets": [{"label": "Projected Volume", "data": list(wtp.values()), "backgroundColor": "#0ea5e9"}]})
        if wwtp:
            charts.append({"title": "Wastewater Volume Projection Trend", "subtitle": "Projected wastewater treated volume versus raw inflow.", "type": "bar", "compact": False, "labels": list(wwtp.keys()), "datasets": [{"label": "Projected Volume", "data": list(wwtp.values()), "backgroundColor": "#14b8a6"}]})
        breakdowns = [
            {"title": "Projection by Component Type", "rows": build_group_rows(component_groups) or [{"label": "No data available", "value": "--", "subtext": "No water-system maintenance matched the selected period."}]},
            {"title": "Projection by Area / Location", "rows": build_group_rows(area_groups) or [{"label": "No data available", "value": "--", "subtext": "No location breakdown available for water systems."}]},
            {"title": "Volume Contribution by Sub-System", "rows": build_value_rows({**wtp, **wwtp}, "m3", 0, f"{period_days}-day projection") or [{"label": "No data available", "value": "--", "subtext": "No water / wastewater totalizer data was available."}]},
        ]
    elif normalized_tab == "mdb":
        energy_by_asset = {k: project_counter_period(load_numeric_timeseries(file_name, ["Value (kW-hr)", "Value", "kWh"]), period_days)["period_projected"] for k, file_name in {"MDB-1": "mdb_emdb.csv", "MDB-6": "mdb6_energy.csv", "MDB-7": "mdb7_energy.csv", "MDB-8": "mdb8_energy.csv", "MDB-9": "mdb9_energy.csv", "MDB-10": "mdb10_energy.csv"}.items()}
        energy_by_asset = {k: v for k, v in energy_by_asset.items() if v is not None}
        peak = {k: project_counter_period(load_numeric_timeseries(file_name, ["Value (kW-hr)", "Value", "kWh"]), period_days)["avg_hourly"] for k, file_name in {"MDB-1": "mdb_emdb.csv", "MDB-6": "mdb6_energy.csv", "MDB-7": "mdb7_energy.csv", "MDB-8": "mdb8_energy.csv", "MDB-9": "mdb9_energy.csv", "MDB-10": "mdb10_energy.csv"}.items()}
        peak = {k: v for k, v in peak.items() if v is not None}
        total_peak = sum(peak.values()) if peak else None
        total_energy = sum(energy_by_asset.values()) if energy_by_asset else None
        kpis.extend([
            make_kpi("High-Risk Electrical Assets Due", format_tasks(len(build_top_asset_rows(projected_scheduled))), "Highest projected electrical workload assets in the selected period", "purple"),
            make_kpi("Projected Energy Consumption", format_value(total_energy, "kWh", 0), "Projected from imported MDB cumulative energy counters", "blue"),
            make_kpi("Projected Peak Demand", format_value(total_peak, "kWh/hr", 2), "Average projected hourly load from recent daily energy baseline", "cyan"),
            make_kpi("Abnormal Energy Spike Risk", "Normal" if total_peak is not None else "No data available", "Compared with the recent electrical demand baseline", "amber"),
        ])
        if energy_by_asset:
            charts.append({"title": "Energy Projection Trend", "subtitle": "Projected energy consumption by MDB asset.", "type": "bar", "compact": False, "labels": list(energy_by_asset.keys()), "datasets": [{"label": "Projected Energy", "data": list(energy_by_asset.values()), "backgroundColor": "#0ea5e9"}]})
        breakdowns = [
            {"title": "Projection by MDB / Transformer / Electrical Asset", "rows": build_group_rows(component_groups) or [{"label": "No data available", "value": "--", "subtext": "No electrical maintenance matched the selected period."}]},
            {"title": "High-Energy-Consuming Assets", "rows": build_value_rows(energy_by_asset, "kWh", 0, f"{period_days}-day projection") or [{"label": "No data available", "value": "--", "subtext": "No electrical energy series were available."}]},
            {"title": "Critical Weeks for Electrical Maintenance", "rows": [{"label": bucket["label"], "value": f"{count} tasks", "subtext": f"{downtime:.1f} hrs downtime exposure"} for bucket, count, downtime in zip(buckets, scheduled_by_bucket, downtime_by_bucket)] or [{"label": "No data available", "value": "--", "subtext": "No critical electrical weeks were identified."}]},
        ]
    else:
        boiler_energy = (project_counter_period(load_numeric_timeseries("boiler_direct_energy.csv", ["Value (kW-hr)", "Value", "kWh"]), period_days)["period_projected"] or 0) + (project_counter_period(load_numeric_timeseries("boiler_indirect_energy.csv", ["Value (kW-hr)", "Value", "kWh"]), period_days)["period_projected"] or 0)
        steam_total = (project_counter_period(load_numeric_timeseries("boiler_directsteam_meterflow_total.csv", ["Value (kg)", "Value", "kg"]), period_days)["period_projected"] or 0) + (project_counter_period(load_numeric_timeseries("boiler_indirectsteam_meterflow.csv", ["Value (kg)", "Value", "kg"]), period_days)["period_projected"] or 0)
        compressor_energy = project_counter_period(load_numeric_timeseries("aircompressor_energy.csv", ["Value", "Energy", "kWh"]), period_days)["period_projected"]
        compressor_flow = project_counter_period(load_numeric_timeseries("airmeter_flow.csv", ["Value (m³)", "Value", "m3"]), period_days)["period_projected"]
        kpis.extend([
            make_kpi("High-Risk Utility Assets Due", format_tasks(len(build_top_asset_rows(projected_scheduled))), "Highest projected boiler / compressor workload assets", "purple"),
            make_kpi("Projected Energy Consumption", format_value((boiler_energy or 0) + (compressor_energy or 0), "kWh", 0), "Projected from imported boiler and compressor cumulative energy data", "blue"),
            make_kpi("Projected Steam Load", format_value(steam_total or None, "kg", 0), "Projected steam output from boiler steam totalizers", "cyan"),
            make_kpi("Projected Air Load", format_value(compressor_flow, "m3", 0), "Projected compressed air output from the air flow totalizer", "green"),
            make_kpi("Abnormal Usage Risk", "Normal" if compressor_energy and compressor_flow else "No data available", "Based on compressor specific power against the current operating baseline", "amber"),
        ])
        energy_by_asset = {k: v for k, v in {"Boiler": boiler_energy or None, "Air Compressor": compressor_energy}.items() if v is not None}
        if energy_by_asset:
            charts.append({"title": "Energy Projection Trend", "subtitle": "Projected energy demand split between boiler and compressor systems.", "type": "bar", "compact": False, "labels": list(energy_by_asset.keys()), "datasets": [{"label": "Projected Energy", "data": list(energy_by_asset.values()), "backgroundColor": "#0ea5e9"}]})
        breakdowns = [
            {"title": "Projection by Asset Type", "rows": build_group_rows(component_groups) or [{"label": "No data available", "value": "--", "subtext": "No utility maintenance matched the selected period."}]},
            {"title": "Projection by Location", "rows": build_group_rows(area_groups) or [{"label": "No data available", "value": "--", "subtext": "No location breakdown was available."}]},
            {"title": "Energy Contribution by Asset Type", "rows": build_value_rows(energy_by_asset, "kWh", 0, f"{period_days}-day projection") or [{"label": "No data available", "value": "--", "subtext": "No boiler / compressor energy series were available."}]},
        ]

    payload = {
        "meta": {"title": TAB_META[normalized_tab]["title"], "subtitle": TAB_META[normalized_tab]["subtitle"], "period": normalized_period, "period_label": period_config["label"], "window_label": format_week_range(start, end), "last_synced": max([value for value in [utility_dataset["meta"].get("last_synced"), equipment_dataset["meta"].get("last_synced")] if value], default=None)},
        "kpis": kpis,
        "charts": charts,
        "breakdowns": breakdowns,
        "alerts": alerts[:3],
    }
    while len(_PROJECTION_CACHE) >= _PROJECTION_CACHE_MAX:
        _PROJECTION_CACHE.pop(next(iter(_PROJECTION_CACHE)))
    _PROJECTION_CACHE[cache_signature] = payload
    return payload
