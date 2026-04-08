import json
import os
from datetime import datetime, timedelta

import pandas as pd


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "data"))
DOWNTIME_CACHE_OUTPUT_FILE = os.path.abspath(
    os.path.join(BASE_DIR, "..", "frontend", "Downtime", "downtime-cache.json")
)

_DOWNTIME_CACHE = {}
DOWNTIME_CACHE_VERSION = "2026-04-08-status-derived-source-fix"
STATUS_DERIVED_SOURCE = "Status-derived"


ASSET_CONFIGS = [
    {
        "machine_code": "MDB-EMDB-1",
        "machine_name": "Main MDB-1",
        "system": "MDB / Power",
        "area": "Main Electrical Control Room",
        "source": "Energy-derived",
        "series_kind": "cumulative",
        "file_name": "mdb_emdb.csv",
        "preferred_values": ["Value (kW-hr)", "Value", "kWh"],
    },
    {
        "machine_code": "MDB-06",
        "machine_name": "MDB 6",
        "system": "MDB / Power",
        "area": "Main Electrical Control Room",
        "source": "Energy-derived",
        "series_kind": "cumulative",
        "file_name": "mdb6_energy.csv",
        "preferred_values": ["Value (kW-hr)", "Value", "kWh"],
    },
    {
        "machine_code": "MDB-07",
        "machine_name": "MDB 7",
        "system": "MDB / Power",
        "area": "Main Electrical Control Room",
        "source": "Energy-derived",
        "series_kind": "cumulative",
        "file_name": "mdb7_energy.csv",
        "preferred_values": ["Value (kW-hr)", "Value", "kWh"],
    },
    {
        "machine_code": "MDB-08",
        "machine_name": "MDB 8",
        "system": "MDB / Power",
        "area": "Main Electrical Control Room",
        "source": "Energy-derived",
        "series_kind": "cumulative",
        "file_name": "mdb8_energy.csv",
        "preferred_values": ["Value (kW-hr)", "Value", "kWh"],
    },
    {
        "machine_code": "MDB-09",
        "machine_name": "MDB 9",
        "system": "MDB / Power",
        "area": "Main Electrical Control Room",
        "source": "Energy-derived",
        "series_kind": "cumulative",
        "file_name": "mdb9_energy.csv",
        "preferred_values": ["Value (kW-hr)", "Value", "kWh"],
    },
    {
        "machine_code": "MDB-10",
        "machine_name": "MDB 10",
        "system": "MDB / Power",
        "area": "Main Electrical Control Room",
        "source": "Energy-derived",
        "series_kind": "cumulative",
        "file_name": "mdb10_energy.csv",
        "preferred_values": ["Value (kW-hr)", "Value", "kWh"],
    },
    {
        "machine_code": "SBF-01",
        "machine_name": "Spiral Freezer 1",
        "system": "Freezer / Refrigeration",
        "area": "Spiral Blast Freezer",
        "source": "Status-derived",
        "series_kind": "freezer_activity",
        "file_name": "sbf_spiral1_Data.csv",
    },
    {
        "machine_code": "SBF-02",
        "machine_name": "Spiral Freezer 2",
        "system": "Freezer / Refrigeration",
        "area": "Spiral Blast Freezer",
        "source": "Status-derived",
        "series_kind": "freezer_activity",
        "file_name": "sbf_spiral2_Data.csv",
    },
    {
        "machine_code": "SBF-03",
        "machine_name": "Spiral Freezer 3",
        "system": "Freezer / Refrigeration",
        "area": "Spiral Blast Freezer",
        "source": "Status-derived",
        "series_kind": "freezer_activity",
        "file_name": "sbf_spiral3_Data.csv",
    },
    {
        "machine_code": "WTP-RO-01",
        "machine_name": "RO Water Supply",
        "system": "Water / Wastewater",
        "area": "Water Treatment Plant",
        "source": "Energy-derived",
        "series_kind": "cumulative",
        "file_name": "FIT-103-ROWaterSupply_Total.csv",
        "preferred_values": ["Value (m3)", "m3", "Value"],
    },
    {
        "machine_code": "WTP-SW1-01",
        "machine_name": "Softwater 1",
        "system": "Water / Wastewater",
        "area": "Water Treatment Plant",
        "source": "Energy-derived",
        "series_kind": "cumulative",
        "file_name": "FIT-102-SoftWaterSupply-01_Total.csv",
        "preferred_values": ["Value (m3)", "m3", "Value"],
    },
    {
        "machine_code": "WTP-SW2-02",
        "machine_name": "Softwater 2",
        "system": "Water / Wastewater",
        "area": "Water Treatment Plant",
        "source": "Energy-derived",
        "series_kind": "cumulative",
        "file_name": "FIT-104-SoftWaterSupply-02_Total.csv",
        "preferred_values": ["Value (m3)", "m3", "Value"],
    },
    {
        "machine_code": "WWTP-EP-01",
        "machine_name": "Effluent Pump",
        "system": "Water / Wastewater",
        "area": "Wastewater Treatment Plant",
        "source": "Energy-derived",
        "series_kind": "cumulative",
        "file_name": "EffluentPump_Total.csv",
        "preferred_values": ["EffluentPump_Total(m3)", "Value", "m3"],
    },
    {
        "machine_code": "WWTP-RAW-01",
        "machine_name": "Raw Water Waste Pump",
        "system": "Water / Wastewater",
        "area": "Wastewater Treatment Plant",
        "source": "Energy-derived",
        "series_kind": "cumulative",
        "file_name": "_RawWaterWastePump-01_Total.csv",
        "preferred_values": ["RawWaterWastePump01_Total(m3)", "Value", "m3"],
    },
    {
        "machine_code": "BLR-DIR-01",
        "machine_name": "Boiler Direct Panel",
        "system": "Boiler / Compressor",
        "area": "Boiler Building",
        "source": "Energy-derived",
        "series_kind": "cumulative",
        "file_name": "boiler_direct_energy.csv",
        "preferred_values": ["Value (kW-hr)", "Value", "kWh"],
    },
    {
        "machine_code": "BLR-IND-02",
        "machine_name": "Boiler Indirect Panel",
        "system": "Boiler / Compressor",
        "area": "Boiler Building",
        "source": "Energy-derived",
        "series_kind": "cumulative",
        "file_name": "boiler_indirect_energy.csv",
        "preferred_values": ["Value (kW-hr)", "Value", "kWh"],
    },
    {
        "machine_code": "COMP-01",
        "machine_name": "Air Compressor",
        "system": "Boiler / Compressor",
        "area": "Air Pump Room",
        "source": "Energy-derived",
        "series_kind": "cumulative",
        "file_name": "airmeter_flow.csv",
        "preferred_values": ["Value (m3)", "Value", "m3"],
    },
]

WORK_ORDER_DOWNTIME_FILE = os.path.join(DATA_DIR, "work_order_downtime.csv")
SUPPORTED_EVENT_SERIES_KINDS = {"freezer_activity", "status"}


def normalize_period(value):
    cleaned = str(value or "").strip().lower()
    if cleaned in {"7d", "week", "next week", "last 7 days"}:
        return "7d"
    if cleaned in {"mtd", "month to date", "monthtodate"}:
        return "mtd"
    if cleaned in {"90d", "quarter", "qtr", "last 90 days"}:
        return "90d"
    if cleaned in {"ytd", "year", "year to date", "full year"}:
        return "ytd"
    return "30d"


def get_period_days(period):
    return {"7d": 7, "30d": 30, "90d": 90}.get(period, 30)


def get_period_label(period):
    return {"7d": "Last 7 Days", "30d": "Last 30 Days", "mtd": "Month to Date", "90d": "Quarter", "ytd": "Year to Date"}.get(period, "Last 30 Days")


def normalize_month_filter(value):
    cleaned = str(value or "").strip()
    if not cleaned or cleaned.lower() == "all":
        return None
    parsed = pd.to_datetime(f"{cleaned}-01", errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.strftime("%Y-%m")


def format_month_label(month_key):
    parsed = pd.to_datetime(f"{month_key}-01", errors="coerce")
    if pd.isna(parsed):
        return month_key
    return parsed.strftime("%b %Y")


def build_year_month_options(reference_dt):
    if reference_dt is None:
        return []
    year = reference_dt.year
    current_month = reference_dt.month
    return [f"{year}-{month:02d}" for month in range(1, current_month + 1)]


def normalize_key(value):
    return "".join(ch for ch in str(value).strip().lower() if ch.isalnum())


def parse_dashboard_timestamp(value):
    if value is None or pd.isna(value):
        return pd.NaT

    cleaned = str(value).replace(" ICT", "").strip()
    parsed = pd.to_datetime(cleaned, format="%d-%b-%y %I:%M:%S %p", errors="coerce")
    if pd.isna(parsed):
        parsed = pd.to_datetime(cleaned, dayfirst=True, errors="coerce")
    return parsed


def get_path_signature(path):
    try:
        stat = os.stat(path)
    except (FileNotFoundError, OSError):
        return None
    return (stat.st_mtime_ns, stat.st_size)


def percentile(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    index = int(round((len(ordered) - 1) * fraction))
    return ordered[max(0, min(index, len(ordered) - 1))]


def format_hours(hours):
    if hours is None:
        return None
    if hours < 1:
        return f"{round(hours * 60)} min"
    return f"{hours:.2f} h"


def load_numeric_timeseries(file_name, preferred_value_names=None):
    path = os.path.join(DATA_DIR, file_name)
    if not os.path.exists(path):
        return pd.DataFrame(columns=["dt", "value"])

    preferred = [normalize_key(name) for name in (preferred_value_names or [])]

    for skiprows in (0, 1, 2):
        try:
            df = pd.read_csv(path, skiprows=skiprows, encoding="utf-8-sig")
            df.columns = [str(col).strip().replace("\ufeff", "") for col in df.columns]
        except Exception:
            continue

        normalized = {normalize_key(col): col for col in df.columns if str(col).strip()}
        time_col = next(
            (
                original
                for key, original in normalized.items()
                if key in {"timestamp", "time", "datetime", "date", "datetimestamp"} or "timestamp" in key
            ),
            None,
        )
        if not time_col:
            continue

        meta_keys = {"timestamp", "time", "datetime", "date", "trendflags", "trendflagstag", "status", "statustag"}
        value_col = next((normalized[name] for name in preferred if name in normalized), None)
        if value_col is None:
            value_col = next(
                (
                    original
                    for key, original in normalized.items()
                    if key not in meta_keys and "timestamp" not in key
                ),
                None,
            )
        if value_col is None:
            continue

        working = df[[time_col, value_col]].copy()
        working["dt"] = working[time_col].apply(parse_dashboard_timestamp)
        working["value"] = pd.to_numeric(working[value_col], errors="coerce")
        working = working.dropna(subset=["dt", "value"]).sort_values("dt")
        if not working.empty:
            return working[["dt", "value"]].reset_index(drop=True)

    return pd.DataFrame(columns=["dt", "value"])


def load_status_timeseries(file_name):
    path = os.path.join(DATA_DIR, file_name)
    if not os.path.exists(path):
        return pd.DataFrame(columns=["dt", "status"])

    for skiprows in (0, 1, 2):
        try:
            df = pd.read_csv(path, skiprows=skiprows, encoding="utf-8-sig")
            df.columns = [str(col).strip().replace("\ufeff", "") for col in df.columns]
        except Exception:
            continue

        normalized = {normalize_key(col): col for col in df.columns if str(col).strip()}
        time_col = next(
            (
                original
                for key, original in normalized.items()
                if key in {"timestamp", "time", "datetime", "date", "datetimestamp"} or "timestamp" in key
            ),
            None,
        )
        status_col = next((original for key, original in normalized.items() if key == "status" or "status" in key), None)
        if not time_col or not status_col:
            continue

        working = df[[time_col, status_col]].copy()
        working["dt"] = working[time_col].apply(parse_dashboard_timestamp)
        working["status"] = working[status_col].astype(str).str.strip()
        working = working.dropna(subset=["dt"]).sort_values("dt")
        if not working.empty:
            return working[["dt", "status"]].reset_index(drop=True)

    return pd.DataFrame(columns=["dt", "status"])


def load_freezer_activity_series(file_name):
    path = os.path.join(DATA_DIR, file_name)
    if not os.path.exists(path):
        return pd.DataFrame(columns=["dt", "value"])

    try:
        df = pd.read_csv(path, skiprows=[1], encoding="latin1")
        df.columns = [str(col).strip().lower().replace(" ", "_") for col in df.columns]
    except Exception:
        return pd.DataFrame(columns=["dt", "value"])

    if "time" not in df.columns:
        return pd.DataFrame(columns=["dt", "value"])

    base_date = datetime.fromtimestamp(os.path.getmtime(path)).date()
    df["parsed_time"] = pd.to_datetime(df["time"], format="%H:%M:%S", errors="coerce")
    df["main_drive"] = pd.to_numeric(df.get("main_drive"), errors="coerce")
    df["sub_drive"] = pd.to_numeric(df.get("sub_drive"), errors="coerce")
    df["value"] = df[["main_drive", "sub_drive"]].max(axis=1, skipna=True)
    df = df.dropna(subset=["parsed_time", "value"]).copy()
    if df.empty:
        return pd.DataFrame(columns=["dt", "value"])

    df["dt"] = df["parsed_time"].apply(lambda ts: datetime.combine(base_date, ts.time()))
    return df[["dt", "value"]].sort_values("dt").reset_index(drop=True)


def build_intervals(series_df, kind):
    if series_df is None or series_df.empty:
        return []

    ordered = series_df.sort_values("dt").reset_index(drop=True)
    intervals = []

    if kind == "cumulative":
        for index in range(1, len(ordered)):
            prev_row = ordered.iloc[index - 1]
            curr_row = ordered.iloc[index]
            start_dt = pd.Timestamp(prev_row["dt"])
            end_dt = pd.Timestamp(curr_row["dt"])
            if start_dt.date() != end_dt.date():
                continue

            interval_minutes = (end_dt - start_dt).total_seconds() / 60
            if interval_minutes <= 0 or interval_minutes > 240:
                continue

            delta_value = max(float(curr_row["value"]) - float(prev_row["value"]), 0.0)
            intervals.append(
                {
                    "date": end_dt.date().isoformat(),
                    "start": start_dt,
                    "end": end_dt,
                    "interval_minutes": interval_minutes,
                    "metric": delta_value,
                }
            )
        return intervals

    for index in range(len(ordered) - 1):
        curr_row = ordered.iloc[index]
        next_row = ordered.iloc[index + 1]
        start_dt = pd.Timestamp(curr_row["dt"])
        end_dt = pd.Timestamp(next_row["dt"])
        if start_dt.date() != end_dt.date():
            continue

        interval_minutes = (end_dt - start_dt).total_seconds() / 60
        if interval_minutes <= 0 or interval_minutes > 240:
            continue

        intervals.append(
            {
                "date": start_dt.date().isoformat(),
                "start": start_dt,
                "end": end_dt,
                "interval_minutes": interval_minutes,
                "metric": max(float(curr_row["value"]), 0.0),
            }
        )

    return intervals


def derive_activity_threshold(intervals, kind):
    if not intervals:
        return None

    if kind == "cumulative":
        # For cumulative counters, zero-delta intervals are the only reliable
        # downtime signal in the imported data.
        return 0.0

    positive_values = [row["metric"] for row in intervals if row["metric"] > 0]
    if len(positive_values) < 5:
        return 0.0

    median_positive = percentile(positive_values, 0.5) or 0.0
    return round(median_positive * 0.05, 3)


def get_operating_hours_for_system(intervals, threshold):
    windows = {}
    by_date = {}
    for row in intervals:
        by_date.setdefault(row["date"], []).append(row)

    for date_key, rows in by_date.items():
        active_rows = [row for row in rows if row["metric"] > (threshold or 0)]
        if not active_rows:
            continue
        windows[date_key] = {
            "start": min(row["start"] for row in active_rows),
            "end": max(row["end"] for row in active_rows),
        }
    return windows


def interval_overlaps_window(interval_row, window):
    if not window:
        return False
    return min(interval_row["end"], window["end"]) > max(interval_row["start"], window["start"])


def group_consecutive_downtime_intervals(intervals):
    if not intervals:
        return []

    ordered = sorted(intervals, key=lambda row: row["start"])
    median_interval = percentile([row["interval_minutes"] for row in ordered], 0.5) or 0
    max_gap_minutes = max(median_interval * 1.5, 1)

    groups = []
    current = None

    for row in ordered:
        if current is None:
            current = {
                "start": row["start"],
                "end": row["end"],
                "duration_minutes": row["interval_minutes"],
            }
            continue

        gap_minutes = (row["start"] - current["end"]).total_seconds() / 60
        if gap_minutes <= max_gap_minutes:
            current["end"] = max(current["end"], row["end"])
            current["duration_minutes"] += row["interval_minutes"]
        else:
            groups.append(current)
            current = {
                "start": row["start"],
                "end": row["end"],
                "duration_minutes": row["interval_minutes"],
            }

    if current is not None:
        groups.append(current)

    return groups


def get_min_downtime_minutes(kind, median_interval_minutes):
    if kind == "freezer_activity":
        return max(median_interval_minutes * 5, 10)
    return max(median_interval_minutes * 2, 30)


def build_confirmed_downtime_candidates(rows, threshold, kind):
    if not rows:
        return []

    median_interval = percentile([row["interval_minutes"] for row in rows], 0.5) or 0
    minimum_duration = get_min_downtime_minutes(kind, median_interval)
    active_flags = [row["metric"] > (threshold or 0) for row in rows]

    flagged = []
    block = []

    for index, row in enumerate(rows):
        if active_flags[index]:
            if block:
                flagged.extend(_confirm_candidate_block(block, active_flags, rows, minimum_duration))
                block = []
            continue
        block.append(index)

    if block:
        flagged.extend(_confirm_candidate_block(block, active_flags, rows, minimum_duration))

    return flagged


def _confirm_candidate_block(block_indexes, active_flags, rows, minimum_duration):
    has_active_before = any(active_flags[:block_indexes[0]])
    has_active_after = any(active_flags[block_indexes[-1] + 1 :])
    if not (has_active_before and has_active_after):
        return []

    block_rows = [rows[index] for index in block_indexes]
    duration_minutes = sum(row["interval_minutes"] for row in block_rows)
    if duration_minutes < minimum_duration:
        return []

    return block_rows


def is_production_critical(machine_name):
    normalized = str(machine_name or "").strip().lower()
    if not normalized:
        return False
    return "combi" in normalized or "brattpan" in normalized


def status_indicates_downtime(status_value):
    normalized = str(status_value or "").strip().lower()
    return "down" in normalized or "fault" in normalized


def detect_status_downtime_events(asset_config):
    status_df = load_status_timeseries(asset_config["file_name"])
    if status_df.empty:
        return [], [], None, None

    latest_dt = pd.Timestamp(status_df.iloc[-1]["dt"])
    ordered = status_df.sort_values("dt").reset_index(drop=True)
    intervals = []
    interval_minutes = []

    for index in range(len(ordered) - 1):
        curr_row = ordered.iloc[index]
        next_row = ordered.iloc[index + 1]
        start_dt = pd.Timestamp(curr_row["dt"])
        end_dt = pd.Timestamp(next_row["dt"])
        minutes = (end_dt - start_dt).total_seconds() / 60
        if minutes <= 0 or minutes > 240:
            continue
        interval_minutes.append(minutes)
        intervals.append(
            {
                "start": start_dt,
                "end": end_dt,
                "status": curr_row["status"],
                "is_down": status_indicates_downtime(curr_row["status"]),
                "interval_minutes": minutes,
            }
        )

    median_interval = percentile(interval_minutes, 0.5) or 15
    candidate_rows = []
    event_rows = []
    active_block = []

    def flush_block():
        nonlocal active_block
        if not active_block:
            return
        duration_minutes = sum(row["interval_minutes"] for row in active_block)
        event_rows.append(
            {
                "system": asset_config["system"],
                "machine_code": asset_config["machine_code"],
                "machine_name": asset_config["machine_name"],
                "area": asset_config["area"],
                "source": STATUS_DERIVED_SOURCE,
                "status": "Downtime Detected",
                "detection_type": "Fault / Down status",
                "start_time": active_block[0]["start"].isoformat(),
                "end_time": active_block[-1]["end"].isoformat(),
                "duration_hours": round(duration_minutes / 60, 3),
                "is_critical": is_production_critical(asset_config["machine_name"]),
            }
        )
        active_block = []

    for row in intervals:
        if row["is_down"]:
            candidate_rows.append(
                {
                    "date": row["start"].date().isoformat(),
                    "system": asset_config["system"],
                    "machine_code": asset_config["machine_code"],
                    "machine_name": asset_config["machine_name"],
                    "area": asset_config["area"],
                    "source": STATUS_DERIVED_SOURCE,
                    "start_time": row["start"].isoformat(),
                    "end_time": row["end"].isoformat(),
                    "duration_hours": round(row["interval_minutes"] / 60, 3),
                    "within_operating_hours": True,
                }
            )
            if active_block:
                gap_minutes = (row["start"] - active_block[-1]["end"]).total_seconds() / 60
                if gap_minutes <= max(median_interval * 1.5, 1):
                    active_block.append(row)
                else:
                    flush_block()
                    active_block = [row]
            else:
                active_block = [row]
        else:
            flush_block()

    flush_block()
    return candidate_rows, event_rows, latest_dt, None


def detect_asset_downtime_events(asset_config):
    status_candidates, status_events, status_latest_dt, _ = detect_status_downtime_events(asset_config)
    if status_events or status_latest_dt is not None:
        return status_candidates, status_events, status_latest_dt, None

    if asset_config["series_kind"] not in SUPPORTED_EVENT_SERIES_KINDS:
        if asset_config["series_kind"] == "freezer_activity":
            series_df = load_freezer_activity_series(asset_config["file_name"])
        else:
            series_df = load_numeric_timeseries(asset_config["file_name"], asset_config.get("preferred_values"))

        latest_dt = pd.Timestamp(series_df.iloc[-1]["dt"]) if not series_df.empty else None
        return [], [], latest_dt, None

    if asset_config["series_kind"] == "freezer_activity":
        series_df = load_freezer_activity_series(asset_config["file_name"])
    else:
        series_df = load_numeric_timeseries(asset_config["file_name"], asset_config.get("preferred_values"))

    if series_df.empty:
        return [], [], None, None

    intervals = build_intervals(series_df, asset_config["series_kind"])
    if not intervals:
        latest_dt = pd.Timestamp(series_df.iloc[-1]["dt"])
        return [], [], latest_dt, None

    threshold = derive_activity_threshold(intervals, asset_config["series_kind"])
    windows = get_operating_hours_for_system(intervals, threshold)
    latest_dt = pd.Timestamp(series_df.iloc[-1]["dt"])

    candidate_rows = []
    event_rows = []
    detection_type = "Zero activity" if (threshold or 0) <= 0 else "Below activity threshold"

    by_date = {}
    for row in intervals:
        by_date.setdefault(row["date"], []).append(row)

    for date_key, rows in by_date.items():
        window = windows.get(date_key)
        if not window:
            continue

        in_window_rows = [row for row in rows if interval_overlaps_window(row, window)]
        confirmed_candidates = build_confirmed_downtime_candidates(
            in_window_rows,
            threshold,
            asset_config["series_kind"],
        )

        for row in confirmed_candidates:
            candidate_rows.append(
                {
                    "date": date_key,
                    "system": asset_config["system"],
                    "machine_code": asset_config["machine_code"],
                    "machine_name": asset_config["machine_name"],
                    "area": asset_config["area"],
                    "source": asset_config["source"],
                    "start_time": row["start"].isoformat(),
                    "end_time": row["end"].isoformat(),
                    "duration_hours": round(row["interval_minutes"] / 60, 3),
                    "within_operating_hours": True,
                }
            )

        for grouped in group_consecutive_downtime_intervals(confirmed_candidates):
            event_rows.append(
                {
                    "system": asset_config["system"],
                    "machine_code": asset_config["machine_code"],
                    "machine_name": asset_config["machine_name"],
                    "area": asset_config["area"],
                    "source": asset_config["source"],
                    "status": "Downtime Detected",
                    "detection_type": detection_type,
                    "start_time": grouped["start"].isoformat(),
                    "end_time": grouped["end"].isoformat(),
                    "duration_hours": round(grouped["duration_minutes"] / 60, 3),
                    "is_critical": is_production_critical(asset_config["machine_name"]),
                }
            )

    operating_window = None
    latest_date_key = latest_dt.date().isoformat()
    if latest_date_key in windows:
        latest_window = windows[latest_date_key]
        operating_window = {
            "start": latest_window["start"].strftime("%H:%M"),
            "end": latest_window["end"].strftime("%H:%M"),
        }

    return candidate_rows, event_rows, latest_dt, operating_window


def load_work_order_downtime():
    if not os.path.exists(WORK_ORDER_DOWNTIME_FILE):
        return {
            "available": False,
            "records": [],
            "message": "No work order downtime source connected yet.",
            "last_synced": None,
        }

    try:
        df = pd.read_csv(WORK_ORDER_DOWNTIME_FILE, encoding="utf-8-sig")
    except Exception:
        return {
            "available": False,
            "records": [],
            "message": "Work order downtime source could not be read.",
            "last_synced": None,
        }

    df.columns = [str(col).strip() for col in df.columns]
    if df.empty:
        return {
            "available": True,
            "records": [],
            "message": "Work order downtime source is connected but empty.",
            "last_synced": datetime.fromtimestamp(os.path.getmtime(WORK_ORDER_DOWNTIME_FILE)).isoformat(),
        }

    records = []
    for _, row in df.iterrows():
        start_time = pd.to_datetime(row.get("start_time"), errors="coerce")
        end_time = pd.to_datetime(row.get("end_time"), errors="coerce")
        downtime_hours = pd.to_numeric(row.get("downtime_hours"), errors="coerce")

        if pd.isna(downtime_hours) and pd.notna(start_time) and pd.notna(end_time) and end_time > start_time:
            downtime_hours = (end_time - start_time).total_seconds() / 3600

        records.append(
            {
                "system": row.get("system") or "Work Order",
                "machine_code": row.get("machine_code") or "",
                "machine_name": row.get("machine_name") or "",
                "area": row.get("area") or "",
                "source": row.get("source") or "Work Order",
                "status": row.get("status") or "Open",
                "detection_type": "Work Order",
                "start_time": start_time.isoformat() if pd.notna(start_time) else None,
                "end_time": end_time.isoformat() if pd.notna(end_time) else None,
                "duration_hours": round(float(downtime_hours), 3) if pd.notna(downtime_hours) else None,
                "is_critical": is_production_critical(row.get("machine_name")),
                "work_order_id": row.get("work_order_id"),
                "maintenance_order_id": row.get("maintenance_order_id"),
                "remarks": row.get("remarks"),
            }
        )

    return {
        "available": True,
        "records": records,
        "message": "Work order downtime source loaded.",
        "last_synced": datetime.fromtimestamp(os.path.getmtime(WORK_ORDER_DOWNTIME_FILE)).isoformat(),
    }


def within_period(iso_string, start_dt, end_dt):
    if not iso_string:
        return False
    dt = pd.to_datetime(iso_string, errors="coerce")
    if pd.isna(dt):
        return False
    return start_dt <= dt <= end_dt


def summarize_downtime_metrics(events, candidate_rows, reference_dt):
    if reference_dt is None:
        return {
            "this_week_hours": None,
            "this_month_hours": None,
            "within_operating_pct": None,
        }

    week_start = (reference_dt - timedelta(days=reference_dt.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    week_end = week_start + timedelta(days=7)
    month_start = reference_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if reference_dt.month == 12:
        next_month = reference_dt.replace(year=reference_dt.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        next_month = reference_dt.replace(month=reference_dt.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)

    week_hours = sum(event["duration_hours"] for event in events if within_period(event.get("start_time"), week_start, week_end))
    month_hours = sum(event["duration_hours"] for event in events if within_period(event.get("start_time"), month_start, next_month))

    candidate_in_window = sum(row["duration_hours"] for row in candidate_rows if row.get("within_operating_hours"))
    candidate_all = sum(row["duration_hours"] for row in candidate_rows)
    within_pct = round((candidate_in_window / candidate_all) * 100, 1) if candidate_all > 0 else None

    return {
        "this_week_hours": round(week_hours, 3),
        "this_month_hours": round(month_hours, 3),
        "within_operating_pct": within_pct,
    }


def build_asset_breakdown(events):
    grouped = {}
    for event in events:
        key = event["machine_code"]
        row = grouped.setdefault(
            key,
            {
                "machine_code": event["machine_code"],
                "machine_name": event["machine_name"],
                "system": event["system"],
                "area": event["area"],
                "downtime_hours": 0.0,
                "event_count": 0,
                "is_critical": bool(event.get("is_critical")),
            },
        )
        row["downtime_hours"] += float(event.get("duration_hours") or 0)
        row["event_count"] += 1

    rows = sorted(grouped.values(), key=lambda item: (-item["downtime_hours"], -item["event_count"], item["machine_name"]))
    for row in rows:
        row["downtime_hours"] = round(row["downtime_hours"], 3)
    return rows


def build_breakdown_rows(events, key_name):
    grouped = {}
    for event in events:
        label = event.get(key_name) or "Unassigned"
        row = grouped.setdefault(label, {"label": label, "downtime_hours": 0.0, "event_count": 0})
        row["downtime_hours"] += float(event.get("duration_hours") or 0)
        row["event_count"] += 1

    rows = sorted(grouped.values(), key=lambda item: (-item["downtime_hours"], -item["event_count"], item["label"]))
    for row in rows:
        row["downtime_hours"] = round(row["downtime_hours"], 3)
    return rows


def build_trend_series(events, start_dt, end_dt):
    labels = []
    hours = []
    counts = []

    current = start_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    end_date = end_dt.replace(hour=0, minute=0, second=0, microsecond=0)

    while current <= end_date:
        next_day = current + timedelta(days=1)
        day_events = [event for event in events if within_period(event.get("start_time"), current, next_day)]
        labels.append(current.strftime("%d %b"))
        hours.append(round(sum(event["duration_hours"] for event in day_events), 3))
        counts.append(len(day_events))
        current = next_day

    return {"labels": labels, "downtime_hours": hours, "event_counts": counts}


def build_cache_signature(period, month_filter=None):
    signatures = [DOWNTIME_CACHE_VERSION, period, month_filter]
    for config in ASSET_CONFIGS:
        signatures.append(get_path_signature(os.path.join(DATA_DIR, config["file_name"])))
    signatures.append(get_path_signature(WORK_ORDER_DOWNTIME_FILE))
    return tuple(signatures)


def build_downtime_payload(period=None, month=None):
    normalized_period = normalize_period(period)
    normalized_month = normalize_month_filter(month)
    cache_signature = build_cache_signature(normalized_period, normalized_month)
    cached = _DOWNTIME_CACHE.get(cache_signature)
    if cached is not None:
        return cached

    candidate_rows = []
    energy_events = []
    latest_timestamps = []
    operating_windows = []

    for asset in ASSET_CONFIGS:
        asset_candidates, asset_events, latest_dt, operating_window = detect_asset_downtime_events(asset)
        candidate_rows.extend(asset_candidates)
        energy_events.extend(asset_events)
        if latest_dt is not None:
            latest_timestamps.append(pd.Timestamp(latest_dt))
        if operating_window:
            operating_windows.append(
                {
                    "machine_code": asset["machine_code"],
                    "machine_name": asset["machine_name"],
                    "system": asset["system"],
                    "window": operating_window,
                }
            )

    work_order_payload = load_work_order_downtime()
    work_order_events = [row for row in work_order_payload["records"] if row.get("duration_hours")]
    if work_order_payload.get("last_synced"):
        latest_timestamps.append(pd.Timestamp(work_order_payload["last_synced"]))

    reference_dt = max(latest_timestamps) if latest_timestamps else None
    if reference_dt is None:
        payload = {
            "meta": {
                "period": normalized_period,
                "period_label": get_period_label(normalized_period),
                "month": normalized_month,
                "month_label": format_month_label(normalized_month) if normalized_month else "All Months",
                "reference_end": None,
                "last_synced": None,
                "work_order_available": work_order_payload["available"],
            },
            "summary": {
                "total_hours": None,
                "this_week_hours": None,
                "this_month_hours": None,
                "event_count": 0,
                "avg_event_hours": None,
                "longest_event_hours": None,
                "highest_system": None,
                "within_operating_pct": None,
                "energy_hours": None,
                "work_order_hours": None,
            },
            "alerts": [],
            "trend": {"labels": [], "downtime_hours": [], "event_counts": []},
            "system_breakdown": [],
            "source_breakdown": [
                {"label": "Status-derived", "downtime_hours": None, "available": False, "message": "No supported status/activity source is available"},
                {
                    "label": "Work Order",
                    "downtime_hours": None,
                    "available": work_order_payload["available"],
                    "message": work_order_payload["message"],
                },
            ],
            "area_breakdown": [],
            "asset_breakdown": [],
            "events": [],
            "filters": {"systems": [], "areas": [], "sources": ["Status-derived", "Work Order"]},
            "months": [],
            "work_order_source": work_order_payload,
            "operating_windows": [],
        }
        _DOWNTIME_CACHE[cache_signature] = payload
        return payload

    month_options = list(reversed(build_year_month_options(reference_dt)))

    if normalized_period == "mtd":
        target_month = normalized_month or reference_dt.strftime("%Y-%m")
        month_start = pd.to_datetime(f"{target_month}-01").to_pydatetime().replace(hour=0, minute=0, second=0, microsecond=0)
        if month_start.year == reference_dt.year and month_start.month == reference_dt.month:
            period_end = reference_dt
        elif month_start.month == 12:
            period_end = month_start.replace(year=month_start.year + 1, month=1) - timedelta(microseconds=1)
        else:
            period_end = month_start.replace(month=month_start.month + 1) - timedelta(microseconds=1)
        period_start = month_start
        normalized_month = target_month
    elif normalized_month:
        month_start = pd.to_datetime(f"{normalized_month}-01").to_pydatetime().replace(hour=0, minute=0, second=0, microsecond=0)
        if month_start.month == 12:
            period_end = month_start.replace(year=month_start.year + 1, month=1) - timedelta(microseconds=1)
        else:
            period_end = month_start.replace(month=month_start.month + 1) - timedelta(microseconds=1)
        period_start = month_start
    elif normalized_period == "ytd":
        period_end = reference_dt
        period_start = reference_dt.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        period_days = get_period_days(normalized_period)
        period_end = reference_dt
        period_start = (reference_dt - timedelta(days=period_days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)

    selected_energy_events = [event for event in energy_events if within_period(event.get("start_time"), period_start, period_end)]
    selected_work_orders = [event for event in work_order_events if within_period(event.get("start_time"), period_start, period_end)]
    selected_events = selected_energy_events + selected_work_orders
    selected_candidate_rows = [row for row in candidate_rows if within_period(row.get("start_time"), period_start, period_end)]
    summarized = summarize_downtime_metrics(energy_events, candidate_rows, reference_dt)
    selected_candidate_in_window = sum(row["duration_hours"] for row in selected_candidate_rows if row.get("within_operating_hours"))
    selected_candidate_all = sum(row["duration_hours"] for row in selected_candidate_rows)
    selected_within_pct = round((selected_candidate_in_window / selected_candidate_all) * 100, 1) if selected_candidate_all > 0 else None

    total_hours = round(sum(event["duration_hours"] for event in selected_events), 3) if selected_events else 0.0
    event_count = len(selected_events)
    longest_event_hours = max((event["duration_hours"] for event in selected_events), default=None)
    avg_event_hours = round(total_hours / event_count, 3) if event_count else None

    system_breakdown = build_breakdown_rows(selected_events, "system")
    area_breakdown = build_breakdown_rows(selected_events, "area")
    asset_breakdown = build_asset_breakdown(selected_events)
    highest_system = system_breakdown[0]["label"] if system_breakdown else None

    energy_hours = round(sum(event["duration_hours"] for event in selected_energy_events), 3) if selected_energy_events else 0.0
    work_order_hours = None
    if work_order_payload["available"]:
        work_order_hours = round(sum(event["duration_hours"] for event in selected_work_orders), 3) if selected_work_orders else 0.0

    source_rows = [
        {
            "label": "Status-derived",
            "downtime_hours": energy_hours,
            "available": True,
            "message": "Calculated from imported fault/down status tags first, then supported activity traces where no status field exists.",
        },
        {
            "label": "Work Order",
            "downtime_hours": work_order_hours,
            "available": work_order_payload["available"],
            "message": work_order_payload["message"],
        },
    ]

    alerts = []
    if highest_system and system_breakdown and system_breakdown[0]["downtime_hours"] >= 3:
        alerts.append(
            {
                "level": "warning",
                "message": f"{highest_system} has the highest downtime in the selected period ({format_hours(system_breakdown[0]['downtime_hours'])}).",
            }
        )
    if longest_event_hours and longest_event_hours >= 2:
        longest_event = max(selected_events, key=lambda event: event["duration_hours"])
        alerts.append(
            {
                "level": "critical",
                "message": f"{longest_event['machine_name']} recorded the longest downtime event ({format_hours(longest_event_hours)}).",
            }
        )

    filters = {
        "systems": sorted({event["system"] for event in selected_events}),
        "areas": sorted({event["area"] for event in selected_events}),
        "sources": ["Status-derived"] + (["Work Order"] if work_order_payload["available"] else []),
    }

    payload = {
        "meta": {
            "period": normalized_period,
            "period_label": get_period_label(normalized_period),
            "month": normalized_month,
            "month_label": format_month_label(normalized_month) if normalized_month else "All Months",
            "reference_end": period_end.isoformat(),
            "last_synced": max(latest_timestamps).isoformat(),
            "work_order_available": work_order_payload["available"],
        },
        "summary": {
            "total_hours": total_hours,
            "this_week_hours": summarized["this_week_hours"],
            "this_month_hours": summarized["this_month_hours"],
            "event_count": event_count,
            "avg_event_hours": avg_event_hours,
            "longest_event_hours": round(longest_event_hours, 3) if longest_event_hours is not None else None,
            "highest_system": highest_system,
            "within_operating_pct": selected_within_pct if selected_within_pct is not None else summarized["within_operating_pct"],
            "energy_hours": energy_hours,
            "work_order_hours": work_order_hours,
        },
        "alerts": alerts,
        "trend": build_trend_series(selected_events, period_start, period_end),
        "system_breakdown": system_breakdown,
        "source_breakdown": source_rows,
        "area_breakdown": area_breakdown,
        "asset_breakdown": asset_breakdown[:8],
        "events": sorted(selected_events, key=lambda event: (event.get("start_time") or "", event.get("machine_name") or ""), reverse=True),
        "filters": filters,
        "months": [{"value": value, "label": format_month_label(value)} for value in month_options],
        "work_order_source": work_order_payload,
        "operating_windows": operating_windows,
    }

    _DOWNTIME_CACHE[cache_signature] = payload
    return payload


def build_downtime_cache_document():
    default_payload = build_downtime_payload("30d")
    month_values = [row["value"] for row in default_payload.get("months", [])]

    payloads = {}
    for period in ("7d", "30d", "90d", "ytd"):
        payloads[period] = build_downtime_payload(period)

    for month_value in month_values:
        payloads[f"mtd:{month_value}"] = build_downtime_payload("mtd", month_value)

    return {
        "generated_at": datetime.now().isoformat(),
        "months": month_values,
        "payloads": payloads,
    }


def write_downtime_cache_file(output_path=None):
    target_path = output_path or DOWNTIME_CACHE_OUTPUT_FILE
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    document = build_downtime_cache_document()
    with open(target_path, "w", encoding="utf-8") as handle:
        json.dump(document, handle, ensure_ascii=False)
    return target_path
