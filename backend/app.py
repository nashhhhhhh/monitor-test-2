from flask import Flask, jsonify, send_from_directory, request, make_response, Blueprint, send_file
import sqlite3
import csv
import os
import io
import json
import random
import copy
import pandas as pd
from datetime import datetime, timedelta
from fpdf import FPDF
import matplotlib
matplotlib.use('Agg')  # Required for headless server environments
import matplotlib.pyplot as plt
from fpdf import FPDF
from fpdf.enums import XPos, YPos
from io import BytesIO
import tempfile
from maintenance_service import (
    build_maintenance_overview_payload,
    build_filter_payload,
    build_list_payload,
    build_monthly_payload,
    build_summary_payload,
    build_timeline_payload,
    build_equipment_filter_payload,
    build_equipment_list_payload,
    build_equipment_monthly_payload,
    build_equipment_summary_payload,
    build_equipment_timeline_payload,
    build_non_scheduled_filter_payload,
    build_non_scheduled_list_payload,
    build_non_scheduled_monthly_payload,
    build_non_scheduled_summary_payload,
    get_maintenance_last_synced,
    get_equipment_maintenance_last_synced,
)
from spare_parts_service import build_spare_parts_payload
from projection_service import build_projection_payload as build_maintenance_projection_payload
from downtime_service import build_downtime_payload, DOWNTIME_CACHE_OUTPUT_FILE


export_pdf_bp = Blueprint("export_pdf", __name__)

# =====================================================
# PATH CONFIGURATION
# =====================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "frontend"))
DATA_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "data"))
LOGO_LOCATIONS = [
    os.path.abspath("/shared/assets/SATS_Logo.png"),
    os.path.abspath(os.path.join(DATA_DIR, "SATS_Logo.png")),
    os.path.abspath(os.path.join(BASE_DIR, "SATS_Logo.png"))
]

app = Flask(
    __name__,
    static_folder=FRONTEND_DIR,
    static_url_path=""
)
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 300

_CSV_READ_CACHE = {}
_CSV_TIMESTAMP_CACHE = {}
_NUMERIC_TIMESERIES_CACHE = {}
_LIGHTING_DATA_CACHE = {}
PDF_REPORT_CACHE_SECONDS = 300
_PDF_REPORT_CACHE = {
    "signature": None,
    "generated_at": None,
    "bytes": None,
}


def get_file_signature(path):
    try:
        stat = os.stat(path)
    except FileNotFoundError:
        return None

    return (stat.st_mtime_ns, stat.st_size)


def build_pdf_report_signature():
    signature = []

    try:
        with os.scandir(DATA_DIR) as entries:
            for entry in entries:
                if not entry.is_file():
                    continue
                if not entry.name.lower().endswith((".csv", ".xlsx", ".json", ".db")):
                    continue
                try:
                    stat = entry.stat()
                except OSError:
                    continue
                signature.append((entry.name, stat.st_mtime_ns, stat.st_size))
    except OSError:
        pass

    for extra_path in [
        DOWNTIME_CACHE_OUTPUT_FILE,
        os.path.join(BASE_DIR, "temps.db"),
    ]:
        signature.append((extra_path, get_file_signature(extra_path)))

    return tuple(sorted(signature, key=lambda item: str(item[0])))


def get_cached_pdf_report(signature):
    cached_bytes = _PDF_REPORT_CACHE.get("bytes")
    cached_at = _PDF_REPORT_CACHE.get("generated_at")

    if not cached_bytes or not cached_at:
        return None
    if _PDF_REPORT_CACHE.get("signature") != signature:
        return None
    if (datetime.now() - cached_at).total_seconds() > PDF_REPORT_CACHE_SECONDS:
        return None

    return cached_bytes


def make_pdf_report_response(pdf_bytes, cache_status):
    pdf_stream = BytesIO(pdf_bytes)
    pdf_stream.seek(0)
    response = send_file(
        pdf_stream,
        mimetype="application/pdf",
        as_attachment=True,
        download_name="SFST_Master_Report.pdf"
    )
    response.headers["X-PDF-Cache"] = cache_status
    return response


def get_path_mtime_iso(path):
    try:
        return datetime.fromtimestamp(os.path.getmtime(path)).isoformat()
    except (FileNotFoundError, OSError, ValueError):
        return None


@app.after_request
def apply_dashboard_cache_headers(response):
    if request.method != "GET":
        return response

    path = (request.path or "").lower()

    if path.startswith("/api/export/"):
        response.cache_control.no_store = True
        response.cache_control.max_age = 0
        return response

    if (
        path.endswith((".css", ".js", ".png", ".jpg", ".jpeg", ".svg", ".ico", ".woff", ".woff2"))
        or path == "/shared/navbar.html"
    ):
        response.cache_control.public = True
        response.cache_control.max_age = 300
        return response

    if path.startswith("/api/page-sync/"):
        response.cache_control.public = True
        response.cache_control.max_age = 60
        return response

    if path.endswith(".html") or path == "/":
        response.cache_control.public = True
        response.cache_control.max_age = 60
        return response

    return response


def get_source_timestamp(file_name):
    path = os.path.join(DATA_DIR, file_name)
    if not os.path.exists(path):
        return None

    if file_name.lower().endswith(".csv"):
        return get_latest_csv_timestamp(file_name) or get_path_mtime_iso(path)

    return get_path_mtime_iso(path)


def get_latest_timestamp_from_files(file_names):
    values = [get_source_timestamp(file_name) for file_name in file_names]
    return max([value for value in values if value], default=None)


def get_temperature_last_synced():
    db_path = os.path.join(BASE_DIR, "temps.db")
    sync_values = []
    if not os.path.exists(db_path):
        db_path = None

    try:
        if not db_path:
            raise FileNotFoundError("Temperature database missing")
        conn = sqlite3.connect(db_path)
        columns = conn.execute("PRAGMA table_info(room_temperature)").fetchall()
        name_map = {
            str(col[1]).strip().lower(): str(col[1]).strip()
            for col in columns
            if len(col) > 1
        }

        for candidate in ["timestamp", "recorded_at", "updated_at", "created_at", "datetime", "time"]:
            if candidate not in name_map:
                continue

            actual = name_map[candidate]
            value = conn.execute(
                f'SELECT MAX("{actual}") FROM room_temperature WHERE "{actual}" IS NOT NULL'
            ).fetchone()[0]
            parsed = pd.to_datetime(value, errors="coerce")
            if pd.notna(parsed):
                conn.close()
                sync_values.append(parsed.isoformat())
                break

        conn.close()
    except Exception:
        pass

    if db_path:
        sync_values.append(get_path_mtime_iso(db_path))

    for source in (TEMPERATURE_ENERGY_CONFIG.get("sources") or {}).values():
        file_name = source.get("file_name")
        if not file_name:
            continue
        path = file_name if os.path.isabs(file_name) else os.path.join(DATA_DIR, file_name)
        if os.path.exists(path):
            sync_values.append(get_source_timestamp(file_name) if not os.path.isabs(file_name) else get_path_mtime_iso(path))

    return max([value for value in sync_values if value], default=None)


PROJECTION_TARGET_HOURS = 24
PROJECTION_TREND_HOURS = 1
PROJECTION_WARNING_HEALTH_PCT = 70
PROJECTION_CRITICAL_HEALTH_PCT = 40
PROJECTION_FREEZER_TEMP_LIMIT = -18
PROJECTION_FREEZER_PRESSURE_LIMIT = 6.5
PROJECTION_COMPRESSOR_SPECIFIC_POWER_WARN = 1.15

ROOM_TEMP_THRESHOLDS = {
    # User-provided expected temperature list. Tolerance checks should use these
    # configured thresholds, not the reported source setpoint field.
    "L:01": {"target": 10, "area_group": "Medium risk - Inbound", "label": "10 deg C"},
    "L:02": {"target": 25, "area_group": "Medium risk - Inbound", "label": "25 deg C"},
    "L:03": {"min_normal": 20, "max_normal": 25, "area_group": "Medium risk - Inbound", "label": "20-25 deg C"},
    "L:04": {"target": 10, "area_group": "Medium risk - Inbound", "label": "10 deg C"},
    "L:05": {"target": 10, "area_group": "Medium risk - Inbound", "label": "10 deg C"},
    "L:06": {"min_normal": 4, "max_normal": 10, "area_group": "Medium risk - Inbound", "label": "4-10 deg C"},
    "L:07": {"target": 25, "area_group": "Medium risk - Inbound", "label": "25 deg C"},
    "L:08": {"target": 25, "area_group": "Medium risk - Inbound", "label": "25 deg C"},
    "L:09": {"min_normal": 18, "max_normal": 20, "area_group": "Medium risk - Inbound", "label": "18-20 deg C"},
    "L:10": {"target": 25, "area_group": "Medium risk - Inbound", "label": "25 deg C"},
    "L:11": {"target": 10, "area_group": "Medium risk - Inbound", "label": "10 deg C"},
    "L:12": {"min_normal": 4, "max_normal": 8, "area_group": "Medium risk - Inbound", "label": "4-8 deg C"},
    "L:13": {"min_normal": 4, "max_normal": 8, "area_group": "Medium risk - Inbound", "label": "4-8 deg C"},
    "L:14": {"min_normal": -5, "max_normal": 10, "area_group": "Medium risk - Inbound", "label": "-5 to +10 deg C"},
    "L:15": {"target": -20, "area_group": "Medium risk - Inbound", "label": "-20 deg C"},
    "L:16": {"min_normal": -5, "max_normal": 10, "area_group": "Medium risk - Inbound", "label": "-5 to +10 deg C"},
    "L:17": {"target": -20, "area_group": "Medium risk - Inbound", "label": "-20 deg C"},
    "L:18": {"target": -20, "area_group": "Medium risk - Inbound", "label": "-20 deg C"},
    "L:19": {"target": 25, "area_group": "Medium risk - Inbound", "label": "25 deg C"},
    "L:20": {"target": 10, "area_group": "Medium risk - Inbound", "label": "10 deg C"},
    "L:21": {"target": 10, "area_group": "Low risk - Preparation & Cooking", "label": "10 deg C"},
    "L:22": {"min_normal": 20, "max_normal": 25, "area_group": "Low risk - Preparation & Cooking", "label": "20-25 deg C"},
    "L:23": {"min_normal": 20, "max_normal": 25, "area_group": "Low risk - Preparation & Cooking", "label": "20-25 deg C"},
    "L:24": {"min_normal": 20, "max_normal": 25, "area_group": "Low risk - Preparation & Cooking", "label": "20-25 deg C"},
    "L:25": {"min_normal": 20, "max_normal": 25, "area_group": "Low risk - Preparation & Cooking", "label": "20-25 deg C"},
    "L:26": {"min_normal": 20, "max_normal": 25, "area_group": "Low risk - Preparation & Cooking", "label": "20-25 deg C"},
    "L:27": {"target": 10, "area_group": "Medium risk - Inbound", "label": "10 deg C"},
    "L:28": {"min_normal": 4, "max_normal": 8, "area_group": "Low risk - Preparation & Cooking", "label": "4-8 deg C"},
    "L:29": {"max_normal": 4, "area_group": "Low risk - Preparation & Cooking", "label": "<=4 deg C"},
    "L:30": {"max_normal": 4, "area_group": "Low risk - Preparation & Cooking", "label": "<=4 deg C"},
    "L:31": {"max_normal": 4, "area_group": "Low risk - Preparation & Cooking", "label": "<=4 deg C"},
    "L:32": {"min_normal": 20, "max_normal": 25, "area_group": "Low risk - Preparation & Cooking", "label": "20-25 deg C"},
    "L:33": {"min_normal": 10, "max_normal": 12, "area_group": "Low risk - Preparation & Cooking", "label": "10-12 deg C"},
    "L:34": {"min_normal": 20, "max_normal": 25, "area_group": "Low risk - Preparation & Cooking", "label": "20-25 deg C"},
    "L:35": {"min_normal": 20, "max_normal": 25, "area_group": "Low risk - Preparation & Cooking", "label": "20-25 deg C"},
    "L:36": {"min_normal": 20, "max_normal": 25, "area_group": "Low risk - Preparation & Cooking", "label": "20-25 deg C"},
    "L:37": {"min_normal": 20, "max_normal": 25, "area_group": "Low risk - Preparation & Cooking", "label": "20-25 deg C"},
    "L:38": {"target": 25, "area_group": "Low risk - Preparation & Cooking", "label": "25 deg C"},
    "L:39": {"min_normal": 20, "max_normal": 25, "area_group": "Low risk - Preparation & Cooking", "label": "20-25 deg C"},
    "L:40": {"max_normal": 4, "area_group": "Low risk - Preparation & Cooking", "label": "<=4 deg C"},
    "L:41": {"min_normal": 20, "max_normal": 25, "area_group": "Low risk - Preparation & Cooking", "label": "20-25 deg C"},
    "L:42": {"max_normal": 4, "area_group": "Low risk - Preparation & Cooking", "label": "<=4 deg C"},
    "L:43": {"min_normal": 10, "max_normal": 12, "area_group": "Low risk - Preparation & Cooking", "label": "10-12 deg C"},
    "L:44": {"max_normal": 4, "area_group": "Low risk - Preparation & Cooking", "label": "<=4 deg C"},
    "L:45": {"min_normal": 10, "max_normal": 12, "area_group": "Low risk - Preparation & Cooking", "label": "10-12 deg C"},
    "L:46": {"max_normal": 4, "area_group": "Low risk - Preparation & Cooking", "label": "<=4 deg C"},
    "L:47": {"min_normal": 10, "max_normal": 12, "area_group": "Low risk - Preparation & Cooking", "label": "10-12 deg C"},
    "L:48": {"max_normal": 4, "area_group": "Low risk - Preparation & Cooking", "label": "<=4 deg C"},
    "L:49": {"min_normal": 20, "max_normal": 25, "area_group": "Low risk - Preparation & Cooking", "label": "20-25 deg C"},
    "L:51": {"min_normal": 20, "max_normal": 25, "area_group": "Low risk - Preparation & Cooking", "label": "20-25 deg C"},
    "L:52": {"min_normal": 10, "max_normal": 12, "area_group": "Low risk - Preparation & Cooking", "label": "10-12 deg C"},
    "H:01": {"min_normal": 20, "max_normal": 25, "area_group": "High risk - Assembly", "label": "20-25 deg C"},
    "H:02": {"min_normal": 10, "max_normal": 12, "area_group": "High risk - Assembly", "label": "10-12 deg C"},
    "H:03": {"min_normal": 20, "max_normal": 25, "area_group": "High risk - Assembly", "label": "20-25 deg C"},
    "H:04": {"target": -10, "area_group": "High risk - Assembly", "label": "-10 deg C"},
    "H:05": {"target": -10, "area_group": "High risk - Assembly", "label": "-10 deg C"},
    "H:06": {"target": -10, "area_group": "High risk - Assembly", "label": "-10 deg C"},
    "H:07": {"max_normal": 4, "area_group": "High risk - Assembly", "label": "<=4 deg C"},
    "H:08": {"target": -10, "area_group": "High risk - Assembly", "label": "-10 deg C"},
    "H:09": {"target": -10, "area_group": "High risk - Assembly", "label": "-10 deg C"},
    "H:10": {"max_normal": 4, "area_group": "High risk - Assembly", "label": "<=4 deg C"},
    "H:11": {"min_normal": -5, "max_normal": 10, "area_group": "High risk - Assembly", "label": "-5 to +10 deg C"},
    "H:12": {"min_normal": 10, "max_normal": 12, "area_group": "High risk - Assembly", "label": "10-12 deg C"},
    "H:13": {"min_normal": 10, "max_normal": 12, "area_group": "High risk - Assembly", "label": "10-12 deg C"},
    "H:14": {"target": -35, "area_group": "High risk - Assembly", "label": "-35 deg C"},
    "H:15": {"min_normal": 10, "max_normal": 12, "area_group": "High risk - Assembly", "label": "10-12 deg C"},
    "H:16": {"min_normal": 10, "max_normal": 12, "area_group": "High risk - Assembly", "label": "10-12 deg C"},
    "H:17": {"min_normal": 10, "max_normal": 12, "area_group": "High risk - Assembly", "label": "10-12 deg C"},
    "H:18": {"min_normal": 10, "max_normal": 12, "area_group": "High risk - Assembly", "label": "10-12 deg C"},
    "H:19": {"target": -20, "area_group": "High risk - Assembly", "label": "-20 deg C"},
    "M:02": {"min_normal": 10, "max_normal": 12, "area_group": "Medium risk - Outbound", "label": "10-12 deg C"},
    "M:03": {"min_normal": 20, "max_normal": 25, "area_group": "Medium risk - Outbound", "label": "20-25 deg C"},
    "M:04": {"target": 25, "area_group": "Medium risk - Outbound", "label": "25 deg C"},
    "M:05": {"min_normal": 10, "max_normal": 12, "area_group": "Medium risk - Outbound", "label": "10-12 deg C"},
    "M:06": {"min_normal": -5, "max_normal": 10, "area_group": "High risk - Assembly", "label": "-5 to +10 deg C"},
    "M:07": {"min_normal": -5, "max_normal": 10, "area_group": "Medium risk - Outbound", "label": "-5 to +10 deg C"},
    "M:08": {"target": -20, "area_group": "Medium risk - Outbound", "label": "-20 deg C"},
    "M:09": {"min_normal": -5, "max_normal": 10, "area_group": "Medium risk - Outbound", "label": "-5 to +10 deg C"},
    "M:10": {"target": -20, "area_group": "Medium risk - Outbound", "label": "-20 deg C"},
}

TEMPERATURE_ENERGY_CONFIG = {
    "minimum_baseline_samples": 5,
    "history_points": 24,
    "sources": {
        # Future-ready default source. Edit this when the final temperature
        # energy export name/columns are confirmed.
        "temperature_energy": {
            "file_name": "temp_energy.csv",
            "label": "Temperature Energy",
            "unit": "kWh",
            "timestamp_columns": ["Time", "Timestamp", "DateTime", "Date"],
            "value_columns": ["kWh", "Value (kWh)", "Value", "Energy"],
            "room_columns": ["base_room", "room_name", "Room", "Room Name", "Equipment", "Source"],
        },
    },
}

ROOM_TO_ENERGY_SOURCE_MAP = {
    # Add mappings here when room-level energy source ownership is confirmed.
    # "Room A": {"source_key": "temperature_energy", "label": "Room A Cooling Energy", "type": "energy"},
    # "H:01": {"source_key": "temperature_energy", "label": "Trolley Storage Cooling Energy", "type": "energy"},
}

OVERVIEW_MIN_BASELINE_SAMPLES = 5


def normalize_projection_key(value):
    return "".join(ch for ch in str(value).strip().lower() if ch.isalnum())


def parse_dashboard_timestamp(value):
    if value is None or pd.isna(value):
        return pd.NaT

    cleaned = str(value).replace(" ICT", "").strip()
    parsed = pd.to_datetime(cleaned, format="%d-%b-%y %I:%M:%S %p", errors="coerce")
    if pd.isna(parsed):
        parsed = pd.to_datetime(cleaned, dayfirst=True, errors="coerce")
    return parsed


def load_numeric_timeseries(file_name, preferred_value_names=None):
    path = os.path.join(DATA_DIR, file_name)
    if not os.path.exists(path):
        return pd.DataFrame(columns=["dt", "value"])

    preferred = [normalize_projection_key(name) for name in (preferred_value_names or [])]
    signature = get_file_signature(path)
    cache_key = (file_name, tuple(preferred))
    cached = _NUMERIC_TIMESERIES_CACHE.get(cache_key)
    if cached and cached["signature"] == signature:
        return cached["data"].copy()

    for skiprows in (0, 1, 2):
        try:
            if str(path).lower().endswith((".xlsx", ".xls")):
                df = pd.read_excel(path, sheet_name=source_config.get("sheet_name", 0), skiprows=skiprows)
            else:
                df = pd.read_csv(path, skiprows=skiprows, encoding="utf-8-sig")
            df.columns = [str(col).strip().replace("\ufeff", "") for col in df.columns]
        except Exception:
            continue

        normalized = {normalize_projection_key(col): col for col in df.columns if str(col).strip()}
        time_col = next(
            (
                original
                for key, original in normalized.items()
                if key in {"timestamp", "time", "datetime", "date", "datetimestamp"}
                or "timestamp" in key
            ),
            None
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
                None
            )
        if value_col is None:
            continue

        working = df[[time_col, value_col]].copy()
        working["dt"] = working[time_col].apply(parse_dashboard_timestamp)
        working["value"] = pd.to_numeric(working[value_col], errors="coerce")
        working = working.dropna(subset=["dt", "value"]).sort_values("dt")
        if not working.empty:
            result = working[["dt", "value"]].reset_index(drop=True)
            _NUMERIC_TIMESERIES_CACHE[cache_key] = {
                "signature": signature,
                "data": result.copy(),
            }
            return result

    return pd.DataFrame(columns=["dt", "value"])


def get_latest_value(series_df):
    if series_df.empty:
        return None
    return float(series_df.iloc[-1]["value"])


def get_latest_timestamp_from_series(series_df):
    if series_df.empty:
        return None
    return pd.Timestamp(series_df.iloc[-1]["dt"])


def safe_divide(numerator, denominator, digits=3):
    if numerator is None or denominator in (None, 0):
        return None
    try:
        if float(denominator) == 0:
            return None
        return round(float(numerator) / float(denominator), digits)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def calculate_cumulative_projection(series_df, total_period_hours=PROJECTION_TARGET_HOURS):
    if series_df.empty:
        return {
            "actual": None,
            "projected": None,
            "elapsed_hours": None,
            "latest_dt": None,
            "current_value": None,
            "previous_day_total": None,
            "baseline_7d": None,
        }

    ordered = series_df.sort_values("dt").copy()
    latest_dt = pd.Timestamp(ordered.iloc[-1]["dt"])
    same_day = ordered[ordered["dt"].dt.date == latest_dt.date()].copy()
    if same_day.empty:
        return {
            "actual": None,
            "projected": None,
            "elapsed_hours": None,
            "latest_dt": latest_dt,
            "current_value": float(ordered.iloc[-1]["value"]),
            "previous_day_total": None,
            "baseline_7d": None,
        }

    start_row = same_day.iloc[0]
    end_row = same_day.iloc[-1]
    elapsed_hours = max((pd.Timestamp(end_row["dt"]) - pd.Timestamp(start_row["dt"])).total_seconds() / 3600, 0.25)
    actual_total = max(float(end_row["value"]) - float(start_row["value"]), 0.0)
    projected_total = round((actual_total / elapsed_hours) * total_period_hours, 3)

    daily = ordered.assign(date=ordered["dt"].dt.date).groupby("date")["value"].agg(["min", "max"])
    daily["total"] = daily["max"] - daily["min"]
    daily_totals = daily["total"].tolist()
    previous_day_total = float(daily_totals[-2]) if len(daily_totals) >= 2 else None
    recent_baseline = None
    if daily_totals:
        baseline_window = daily_totals[-8:-1] if len(daily_totals) > 1 else daily_totals[-1:]
        if baseline_window:
            recent_baseline = round(float(sum(baseline_window) / len(baseline_window)), 3)

    return {
        "actual": round(actual_total, 3),
        "projected": projected_total,
        "elapsed_hours": round(elapsed_hours, 2),
        "latest_dt": latest_dt,
        "current_value": float(end_row["value"]),
        "previous_day_total": round(previous_day_total, 3) if previous_day_total is not None else None,
        "baseline_7d": recent_baseline,
    }


def calculate_trend_projection(series_df, forecast_hours=PROJECTION_TREND_HOURS, points=3):
    if series_df.empty:
        return {
            "latest": None,
            "projected": None,
            "slope_per_hour": None,
            "latest_dt": None,
            "point_count": 0,
        }

    recent = series_df.sort_values("dt").dropna(subset=["value"]).tail(points)
    if len(recent) < 2:
        latest = float(recent.iloc[-1]["value"]) if not recent.empty else None
        latest_dt = pd.Timestamp(recent.iloc[-1]["dt"]) if not recent.empty else None
        return {
            "latest": latest,
            "projected": None,
            "slope_per_hour": None,
            "latest_dt": latest_dt,
            "point_count": int(len(recent)),
        }

    first = recent.iloc[0]
    last = recent.iloc[-1]
    delta_hours = max((pd.Timestamp(last["dt"]) - pd.Timestamp(first["dt"])).total_seconds() / 3600, 1 / 60)
    slope_per_hour = (float(last["value"]) - float(first["value"])) / delta_hours
    projected = float(last["value"]) + (slope_per_hour * forecast_hours)

    return {
        "latest": round(float(last["value"]), 3),
        "projected": round(projected, 3),
        "slope_per_hour": round(slope_per_hour, 3),
        "latest_dt": pd.Timestamp(last["dt"]),
        "point_count": int(len(recent)),
    }


def calculate_threshold_forecast(current_value, slope_per_hour, upper_limit=None, lower_limit=None):
    if current_value is None or slope_per_hour is None:
        return None

    if upper_limit is not None and slope_per_hour > 0 and current_value < upper_limit:
        hours = (upper_limit - current_value) / slope_per_hour
        if hours > 0:
            return round(hours, 2)

    if lower_limit is not None and slope_per_hour < 0 and current_value > lower_limit:
        hours = (lower_limit - current_value) / slope_per_hour
        if hours > 0:
            return round(hours, 2)

    return None


def calculate_projection_variance(projected_total, baseline_total):
    if projected_total is None or baseline_total in (None, 0):
        return None
    return round(((projected_total - baseline_total) / baseline_total) * 100, 1)


def combine_status(*statuses):
    priority = {"NORMAL": 0, "ATTENTION": 1, "WARNING": 2, "OFFLINE": 3, "UNAVAILABLE": 3}
    cleaned = [str(status or "NORMAL").upper() for status in statuses]
    return max(cleaned or ["NORMAL"], key=lambda status: priority.get(status, 0))


def recent_value_baseline(series_df, min_samples=OVERVIEW_MIN_BASELINE_SAMPLES, window=24):
    if series_df is None or series_df.empty:
        return None
    values = pd.to_numeric(series_df.sort_values("dt")["value"], errors="coerce").dropna()
    if len(values) < min_samples + 1:
        return None
    baseline_values = values.iloc[-(window + 1):-1] if len(values) > window else values.iloc[:-1]
    if len(baseline_values) < min_samples:
        return None
    baseline = float(baseline_values.mean())
    return baseline if baseline > 0 else None


def classify_high_baseline(current_value, baseline_value, attention_ratio=1.20, warning_ratio=1.40):
    if current_value is None or baseline_value in (None, 0):
        return "NORMAL"
    try:
        ratio = float(current_value) / float(baseline_value)
    except (TypeError, ValueError, ZeroDivisionError):
        return "NORMAL"
    if ratio > warning_ratio:
        return "WARNING"
    if ratio > attention_ratio:
        return "ATTENTION"
    return "NORMAL"


def classify_low_baseline(current_value, baseline_value, attention_ratio=0.80, warning_ratio=0.70):
    if current_value is None or baseline_value in (None, 0):
        return "NORMAL"
    try:
        ratio = float(current_value) / float(baseline_value)
    except (TypeError, ValueError, ZeroDivisionError):
        return "NORMAL"
    if ratio < warning_ratio:
        return "WARNING"
    if ratio < attention_ratio:
        return "ATTENTION"
    return "NORMAL"


def classify_deviation_from_baseline(current_value, baseline_value, attention_pct=0.20, warning_pct=0.30):
    if current_value is None or baseline_value in (None, 0):
        return "NORMAL"
    try:
        deviation = abs(float(current_value) - float(baseline_value)) / abs(float(baseline_value))
    except (TypeError, ValueError, ZeroDivisionError):
        return "NORMAL"
    if deviation > warning_pct:
        return "WARNING"
    if deviation > attention_pct:
        return "ATTENTION"
    return "NORMAL"


def classify_projection_against_baseline(projection_payload, mode="high"):
    if not projection_payload:
        return "NORMAL"
    projected = projection_payload.get("projected")
    baseline = projection_payload.get("baseline_7d")
    if baseline in (None, 0) or projected is None:
        return "NORMAL"
    if mode == "low":
        return classify_low_baseline(projected, baseline)
    return classify_high_baseline(projected, baseline)


def classify_flatline_against_baseline(series_df, baseline_value):
    if series_df is None or series_df.empty or baseline_value in (None, 0):
        return "NORMAL"
    ordered = series_df.sort_values("dt").tail(6)
    if len(ordered) < 4:
        return "NORMAL"
    values = pd.to_numeric(ordered["value"], errors="coerce").dropna()
    if len(values) < 4:
        return "NORMAL"
    recent_delta = float(values.max() - values.min())
    baseline = float(baseline_value)
    if recent_delta <= max(baseline * 0.005, 0.01):
        return "WARNING"
    if recent_delta <= max(baseline * 0.02, 0.05):
        return "ATTENTION"
    return "NORMAL"


def classify_chlorine_overview(value):
    if value is None:
        return "NORMAL"
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "NORMAL"
    if numeric < 0.1 or numeric > 1.5:
        return "WARNING"
    if numeric < 0.2 or numeric > 1.2:
        return "ATTENTION"
    return "NORMAL"


def normalize_room_threshold_config(config):
    if not config:
        return None
    normalized = dict(config)
    if normalized.get("target") is not None:
        normalized.setdefault("min_normal", normalized.get("target"))
        normalized.setdefault("max_normal", normalized.get("target"))
    normalized.setdefault("attention_buffer", 1)
    normalized.setdefault("warning_buffer", 3)
    return normalized


def classify_temperature_value(value, config):
    if value is None:
        return "NORMAL"
    config = normalize_room_threshold_config(config)
    if not config:
        return "NORMAL"
    min_normal = config.get("min_normal")
    max_normal = config.get("max_normal")
    if min_normal is None and max_normal is None:
        return "NORMAL"
    try:
        temp = float(value)
        min_normal = float(min_normal) if min_normal is not None else None
        max_normal = float(max_normal) if max_normal is not None else None
    except (TypeError, ValueError):
        return "NORMAL"
    attention_buffer = float(config.get("attention_buffer", 1) or 0)
    warning_buffer = float(config.get("warning_buffer", attention_buffer or 1) or attention_buffer or 1)
    above_min = min_normal is None or temp >= min_normal
    below_max = max_normal is None or temp <= max_normal
    if above_min and below_max:
        return "NORMAL"
    attention_min = min_normal - attention_buffer if min_normal is not None else None
    attention_max = max_normal + attention_buffer if max_normal is not None else None
    warning_min = min_normal - warning_buffer if min_normal is not None else None
    warning_max = max_normal + warning_buffer if max_normal is not None else None
    if (attention_min is None or temp >= attention_min) and (attention_max is None or temp <= attention_max):
        return "ATTENTION"
    if (warning_min is not None and temp < warning_min) or (warning_max is not None and temp > warning_max):
        return "WARNING"
    return "WARNING"


def classify_room_temperature(room_name, value):
    return classify_temperature_value(value, find_room_threshold_config(room_name))


def find_room_threshold_config(room_name):
    normalized_room = normalize_projection_key(room_name)
    if not normalized_room:
        return None
    matching_key = next(
        (key for key in ROOM_TEMP_THRESHOLDS if normalize_projection_key(key) == normalized_room),
        None,
    )
    if not matching_key:
        matching_key = next(
            (
                key for key, config in ROOM_TEMP_THRESHOLDS.items()
                if normalized_room in {normalize_projection_key(alias) for alias in config.get("aliases", [])}
            ),
            None,
        )
    return normalize_room_threshold_config(ROOM_TEMP_THRESHOLDS.get(matching_key)) if matching_key else None


def find_temperature_energy_mapping(room):
    candidates = [
        room.get("base_room"),
        room.get("room_name"),
        room.get("Room"),
        room.get("Room Name"),
    ]
    normalized_candidates = {normalize_projection_key(value) for value in candidates if value}
    for key, mapping in ROOM_TO_ENERGY_SOURCE_MAP.items():
        if normalize_projection_key(key) in normalized_candidates:
            return mapping or {}
    return None


def load_temperature_energy_source(source_key):
    source_config = (TEMPERATURE_ENERGY_CONFIG.get("sources") or {}).get(source_key)
    if not source_config:
        return pd.DataFrame(columns=["dt", "value", "room_key"])

    file_name = source_config.get("file_name")
    if not file_name:
        return pd.DataFrame(columns=["dt", "value", "room_key"])

    path = file_name if os.path.isabs(file_name) else os.path.join(DATA_DIR, file_name)
    if not os.path.exists(path):
        return pd.DataFrame(columns=["dt", "value", "room_key"])

    timestamp_preferences = [normalize_projection_key(col) for col in source_config.get("timestamp_columns", [])]
    value_preferences = [normalize_projection_key(col) for col in source_config.get("value_columns", [])]
    room_preferences = [normalize_projection_key(col) for col in source_config.get("room_columns", [])]

    for skiprows in (0, 1, 2):
        try:
            df = pd.read_csv(path, skiprows=skiprows, encoding="utf-8-sig")
            df.columns = [str(col).strip().replace("\ufeff", "") for col in df.columns]
        except Exception:
            continue

        normalized = {normalize_projection_key(col): col for col in df.columns if str(col).strip()}
        time_col = next((normalized[key] for key in timestamp_preferences if key in normalized), None)
        if time_col is None:
            time_col = next(
                (
                    original
                    for key, original in normalized.items()
                    if key in {"timestamp", "time", "datetime", "date"} or "timestamp" in key
                ),
                None,
            )

        value_col = next((normalized[key] for key in value_preferences if key in normalized), None)
        if value_col is None:
            value_col = next(
                (
                    original
                    for key, original in normalized.items()
                    if key not in {"timestamp", "time", "datetime", "date", "status", "trendflags"}
                    and "timestamp" not in key
                ),
                None,
            )

        if time_col is None or value_col is None:
            continue

        room_col = next((normalized[key] for key in room_preferences if key in normalized), None)
        working = df[[time_col, value_col] + ([room_col] if room_col else [])].copy()
        working["dt"] = working[time_col].apply(parse_dashboard_timestamp)
        working["value"] = pd.to_numeric(working[value_col], errors="coerce")
        working["room_key"] = working[room_col].apply(normalize_projection_key) if room_col else None
        working = working.dropna(subset=["dt", "value"]).sort_values("dt")
        if not working.empty:
            return working[["dt", "value", "room_key"]].reset_index(drop=True)

    return pd.DataFrame(columns=["dt", "value", "room_key"])


def build_temperature_energy_payload(room):
    mapping = find_temperature_energy_mapping(room)
    if not mapping:
        return {
            "mapped": False,
            "available": False,
            "status": "NORMAL",
            "source_key": None,
            "label": None,
            "unit": None,
            "latest_value": None,
            "latest_timestamp": None,
            "baseline": None,
            "trend": [],
            "insight": None,
        }

    source_key = mapping.get("source_key")
    source_config = (TEMPERATURE_ENERGY_CONFIG.get("sources") or {}).get(source_key, {})
    source_df = load_temperature_energy_source(source_key)
    room_key = normalize_projection_key(room.get("base_room") or room.get("room_name"))
    room_df = source_df
    if not source_df.empty and source_df["room_key"].notna().any():
        mapped_room_keys = {
            normalize_projection_key(value)
            for value in [room.get("base_room"), room.get("room_name"), mapping.get("room_key")]
            if value
        }
        room_df = source_df[source_df["room_key"].isin(mapped_room_keys)]

    if room_df.empty:
        return {
            "mapped": True,
            "available": False,
            "status": "UNAVAILABLE",
            "source_key": source_key,
            "label": mapping.get("label"),
            "unit": mapping.get("unit") or source_config.get("unit"),
            "latest_value": None,
            "latest_timestamp": None,
            "baseline": None,
            "trend": [],
            "insight": "Energy mapping exists, but no valid energy readings are available yet.",
        }

    baseline = recent_value_baseline(
        room_df,
        min_samples=TEMPERATURE_ENERGY_CONFIG.get("minimum_baseline_samples", OVERVIEW_MIN_BASELINE_SAMPLES),
        window=TEMPERATURE_ENERGY_CONFIG.get("history_points", 24),
    )
    latest_value = get_latest_value(room_df)
    energy_status = combine_status(
        classify_high_baseline(latest_value, baseline),
        classify_low_baseline(latest_value, baseline),
        classify_flatline_against_baseline(room_df, baseline),
    )
    history = [
        {"time": pd.Timestamp(row["dt"]).isoformat(), "value": round(float(row["value"]), 3)}
        for _, row in room_df.sort_values("dt").tail(TEMPERATURE_ENERGY_CONFIG.get("history_points", 24)).iterrows()
    ]
    latest_dt = get_latest_timestamp_from_series(room_df)

    return {
        "mapped": True,
        "available": True,
        "status": energy_status,
        "source_key": source_key,
        "label": mapping.get("label") or source_config.get("label"),
        "unit": mapping.get("unit") or source_config.get("unit"),
        "latest_value": round(latest_value, 3) if latest_value is not None else None,
        "latest_timestamp": latest_dt.isoformat() if latest_dt is not None else None,
        "baseline": round(float(baseline), 3) if baseline is not None else None,
        "trend": history,
        "insight": None,
    }


def build_temperature_combined_insight(temp_status, energy_payload):
    energy_status = (energy_payload or {}).get("status")
    energy_available = (energy_payload or {}).get("available")
    if not energy_available:
        return None
    temp_status = str(temp_status or "NORMAL").upper()
    energy_status = str(energy_status or "NORMAL").upper()
    temp_abnormal = temp_status in {"ATTENTION", "WARNING", "CRITICAL"}
    energy_abnormal = energy_status in {"ATTENTION", "WARNING"}
    if not temp_abnormal and energy_abnormal:
        return "Temperature stable while energy is deviating; possible efficiency issue."
    if temp_abnormal and energy_status in {"NORMAL"}:
        return "Temperature is outside expected range while energy appears normal; check load, door, or sensor conditions."
    if temp_abnormal and energy_abnormal:
        return "Temperature and energy are both deviating; check cooling performance."
    return "Temperature and mapped energy are stable."


def temperature_status_to_page_status(status):
    normalized = str(status or "NORMAL").upper()
    if normalized == "WARNING":
        return "CRITICAL"
    if normalized == "ATTENTION":
        return "WARNING"
    return "OK"


def build_metric_card(metric_id, title, value, unit="", subtitle="", status="normal", empty_state="Unavailable"):
    return {
        "id": metric_id,
        "title": title,
        "value": value,
        "unit": unit,
        "subtitle": subtitle,
        "status": status,
        "empty_state": empty_state,
    }


def build_empty_metric_card(metric_id, title, subtitle="", empty_state="Unavailable"):
    return build_metric_card(metric_id, title, None, "", subtitle, "unavailable", empty_state)

# =====================================================
# GENERIC CSV READER (LEGACY SUPPORT)
# =====================================================

def read_csv(file_name, value_key="value"):
    """
    Reads CSV files, skips metadata by searching for the 'Timestamp' header,
    and extracts time and numeric values.
    """
    path = os.path.join(DATA_DIR, file_name)
    data = []

    if not os.path.exists(path):
        print(f"❌ FILE MISSING: {path}")
        return data

    signature = get_file_signature(path)
    cache_key = (file_name, value_key)
    cached = _CSV_READ_CACHE.get(cache_key)
    if cached and cached["signature"] == signature:
        return copy.deepcopy(cached["data"])

    try:
        with open(path, mode="r", encoding="utf-8-sig", errors="ignore") as f:
            lines = f.readlines()

            # Find the header row (contains 'Timestamp')
            header_idx = -1
            for i, line in enumerate(lines):
                if "timestamp" in line.lower():
                    header_idx = i
                    break

            if header_idx == -1:
                print(f"⚠️ HEADER NOT FOUND in {file_name}")
                return data

            # Parse from the header onwards
            content = "".join(lines[header_idx:])
            reader = csv.DictReader(io.StringIO(content))

            # Identify the value column once (first non-Timestamp column)
            fieldnames = reader.fieldnames or []
            value_col = None
            for fn in fieldnames:
                fns = fn.strip()
                if "timestamp" not in fns.lower():
                    # prefer a column with "value" in name, else take first non-timestamp
                    if "value" in fns.lower():
                        value_col = fns
                        break
                    elif value_col is None:
                        value_col = fns

            for row in reader:
                # Clean keys (strip whitespace)
                clean_row = {k.strip(): v for k, v in row.items() if k}

                ts_val = None
                real_val = None

                # Find the Timestamp column dynamically
                for k, v in clean_row.items():
                    kl = k.lower()
                    if "timestamp" in kl:
                        ts_val = v

                # Use the pre-identified value column
                if value_col and value_col in clean_row:
                    real_val = clean_row[value_col]
                else:
                    # fallback: first non-timestamp column
                    for k, v in clean_row.items():
                        if "timestamp" not in k.lower():
                            real_val = v
                            break

                if ts_val and real_val:
                    try:
                        # Extract Time + AM/PM for better dashboard visualization
                        # Input: "20-Dec-25 1:15:00 AM ICT" -> Output: "1:15:00 AM"
                        parts = ts_val.split(" ")
                        time_part = f"{parts[1]} {parts[2]}" if len(parts) > 2 else parts[1]
                        
                        data.append({
                            "time": time_part,
                            value_key: float(real_val)
                        })
                    except (ValueError, IndexError):
                        continue

    except Exception as e:
        print(f"🔥 CSV ERROR ({file_name}): {e}")

    _CSV_READ_CACHE[cache_key] = {
        "signature": signature,
        "data": copy.deepcopy(data)
    }
    return data

def read_sbf_csv(file_path):
    """
    Reads Spiral Blast Freezer CSV files, handles metadata/units,
    and normalizes headers for JSON output.
    """
    if not os.path.exists(file_path):
        print(f"⚠️ Warning: File not found at {file_path}")
        return []

    try:
        # 1. Read CSV using 'latin1' to handle special symbols (², °)
        # Skip row 1 (the units row like 'oC', 'kg/cm2')
        df = pd.read_csv(file_path, skiprows=[1], encoding='latin1')

        # 2. Clean and Normalize Column Names
        # This transforms 'Main Drive' -> 'main_drive', 'TEF01' -> 'tef01', etc.
        df.columns = [c.strip().lower().replace(' ', '_') for c in df.columns]

        # 3. Handle 'Unnamed' columns (often used for Energy in these files)
        # If 'unnamed:_11' exists (where Use kWh is stored), rename it to 'energy_kwh'
        if 'unnamed:_10' in df.columns: df.rename(columns={'unnamed:_10': 'energy_time'}, inplace=True)
        if 'unnamed:_11' in df.columns: df.rename(columns={'unnamed:_11': 'use_kwh'}, inplace=True)

        # Remove any other empty unnamed columns
        df = df.loc[:, ~df.columns.str.contains('^unnamed')]

        # 4. Numeric Conversion
        # Ensure values are floats so they can be graphed/calculated
        numeric_cols = ['tef01', 'tef02', 'pt01', 'pt02', 'main_drive', 'sub_drive', 'freezing_time', 'runtime', 'use_kwh']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        # 5. Drop trailing empty rows (no TIME value), then fill remaining NaNs with None
        if 'time' in df.columns:
            df = df.dropna(subset=['time'])
        df = df.where(pd.notnull(df), None)

        # Return latest data (or all data if needed for charts)
        return df.to_dict(orient='records')

    except Exception as e:
        print(f"🔥 Error reading {file_path}: {e}")
        return []
    
def read_conveyor_csv(filepath):
    if not os.path.exists(filepath):
        return []

    rows = []

    with open(filepath, newline='', encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        headers = next(reader, None)  # Skip header

        for row in reader:
            try:
                # Columns: B C D = pcs/min → total = C + D
                c_val = float(row[2]) if row[2] else 0
                d_val = float(row[3]) if row[3] else 0
                total_min = c_val + d_val

                # Columns: E F G = pcs/day → total = F + G
                f_val = float(row[5]) if row[5] else 0
                g_val = float(row[6]) if row[6] else 0
                total_day = f_val + g_val

                rows.append({
                    "time": row[0],

                    "pcs_min_total": total_min,
                    "pcs_min_1": c_val,
                    "pcs_min_2": d_val,

                    "pcs_day_total": total_day,
                    "pcs_day_1": f_val,
                    "pcs_day_2": g_val
                })

            except (IndexError, ValueError):
                continue

    return rows

# =====================================================
# FRONTEND ROUTES
# =====================================================

@app.route("/")
def root():
    return send_from_directory(os.path.join(FRONTEND_DIR, "Overview"), "index.html")

@app.route("/<path:path>")
def frontend_files(path):
    return send_from_directory(FRONTEND_DIR, path)


# =====================================================
# TEMPERATURE API
# =====================================================

@app.route("/api/temperature/rooms")
def temperature_rooms():
    try:
        db_path = os.path.join(BASE_DIR, "temps.db")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM room_temperature").fetchall()
        conn.close()
        enriched_rows = []
        for row in rows:
            room = dict(row)
            actual_temp = pd.to_numeric(room.get("Actual Temp"), errors="coerce")
            threshold_config = find_room_threshold_config(room.get("room_name")) or find_room_threshold_config(room.get("base_room"))
            threshold_configured = bool(
                threshold_config
                and (
                    threshold_config.get("min_normal") is not None
                    or threshold_config.get("max_normal") is not None
                )
            )
            threshold_status = classify_temperature_value(actual_temp, threshold_config) if threshold_configured else "NORMAL"
            if threshold_configured:
                room["status"] = temperature_status_to_page_status(threshold_status)

            energy_payload = build_temperature_energy_payload(room)
            effective_temp_status = threshold_status if threshold_configured else room.get("status")
            combined_insight = build_temperature_combined_insight(effective_temp_status, energy_payload)

            room["temperature_status"] = effective_temp_status
            room["temperature_threshold_status"] = threshold_status
            room["expected_range"] = {
                "min_normal": threshold_config.get("min_normal") if threshold_config else None,
                "max_normal": threshold_config.get("max_normal") if threshold_config else None,
                "attention_buffer": threshold_config.get("attention_buffer") if threshold_config else None,
                "warning_buffer": threshold_config.get("warning_buffer") if threshold_config else None,
                "label": threshold_config.get("label") if threshold_config else None,
                "area_group": threshold_config.get("area_group") if threshold_config else None,
                "configured": threshold_configured,
            }
            room["energy"] = energy_payload
            room["combined_insight"] = combined_insight
            enriched_rows.append(room)

        return jsonify(enriched_rows)
    except Exception as exc:
        print(f"Temperature rooms API error: {exc}")
        return jsonify([])
    
# =====================================================
# REFRIGERATION API
# =====================================================

@app.route("/api/refrigeration")
def refrigeration():
    return jsonify({
        "energy": read_csv("temp_energy.csv", "energy"),
        "hr": read_csv("temp_HR.csv", "hr"),
        "iw": read_csv("temp_IW.csv", "iw"),
        "lr": read_csv("temp_LR.csv", "lr"),
        "ow": read_csv("temp_OW.csv", "ow")
    })


# =====================================================
# AIR COMPRESSOR API
# =====================================================

@app.route("/api/aircompressor")
def aircompressor():
    return jsonify({
        "energy": read_csv("aircompressor_energy.csv", "energy"),
        "flow": read_csv("airmeter_flow.csv", "flow"),
        "dewpoint": read_csv("air_dewpoint.csv", "dewpoint")
    })


# =====================================================
# BOILER API
# =====================================================

@app.route("/api/boiler")
def boiler():
    return jsonify({
        "boiler_01": {
            "stage_1_runtime": read_csv("boiler01_1_RT.csv", "runtime"),
            "stage_2_runtime": read_csv("boiler01_2_RT.csv", "runtime"),
            "stage_3_runtime": read_csv("boiler01_3_RT.csv", "runtime")
        },
        "boiler_02": {
            "stage_1_runtime": read_csv("boiler02_1_RT.csv", "runtime"),
            "stage_2_runtime": read_csv("boiler02_2_RT.csv", "runtime")
        },
        "consumption": {
            "gas_total_kg": read_csv("boiler_gas_total.csv", "gas"),
            "direct_steam_kg": read_csv("boiler_directsteam_meterflow_total.csv", "steam"),
            "indirect_steam_kg": read_csv("boiler_indirectsteam_meterflow.csv", "steam"),
            "direct_energy_kwh": read_csv("boiler_direct_energy.csv", "energy"),
            "indirect_energy_kwh": read_csv("boiler_indirect_energy.csv", "energy")
        }
    })


# =====================================================
# CCTV API
# =====================================================

@app.route("/api/cctv/log")
def cctv_log():
    file_name = "Resource Online Status Log_2026_02_05_10_21_49.xlsx"
    path = os.path.join(DATA_DIR, file_name)

    if not os.path.exists(path):
        return jsonify([])

    try:
        df = pd.read_excel(path)
        df.columns = df.columns.str.strip()

        return jsonify([
            {
                "name": str(r["Name"]).strip(),
                "status": str(r["Current Status"]).strip(),
                "area": str(r["Area"]).strip(),
                "address": str(r["Address"]).strip(),
                "lastOffline": str(r["Latest Offline Time"]),
                "offlineCount": str(r["Total Offline Times"]),
                "offlineDuration": str(r["Total Offline Duration"])
            }
            for _, r in df.iterrows()
        ])
    except:
        return jsonify([])



# =====================================================
# LIGHTING API
# =====================================================

LIGHTING_REQUIRED_COLUMNS = [
    "Fixture Name",
    "Area Name",
    "Circuit Name",
    "Hours On In Period",
    "Notional Energy",
    "Hours On Running",
    "Lamp Life Remaining"
]

LIGHTING_COLUMN_ALIASES = {
    "Fixture Name": "Fixture Name",
    "Area Name": "Area Name",
    "Circuit Name": "Circuit Name",
    "Hours On In Period": "Hours On In Period",
    "Notional Energy (kWh)": "Notional Energy",
    "Notional Energy": "Notional Energy",
    "Hours On Running Total": "Hours On Running",
    "Hours On Running": "Hours On Running",
    "Lamp Life Remaining": "Lamp Life Remaining"
}

LIGHTING_CSV_FILENAME = "Channel Runtime_Light.csv"
LIGHTING_CSV_PATH = os.path.join(DATA_DIR, LIGHTING_CSV_FILENAME)


def normalize_text(value):
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return None
    return text


def normalize_number(value):
    if value is None or pd.isna(value):
        return None

    text = str(value).strip()
    if not text:
        return None

    lowered = text.lower()
    if lowered in {"nan", "none", "null", "no data", "-"}:
        return None

    text = text.replace(",", "")
    try:
        number = float(text)
    except ValueError:
        return None

    return int(number) if number.is_integer() else round(number, 3)


def find_existing_path(candidates):
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    return None


def detect_lighting_header_row(raw_df):
    for idx, row in raw_df.iterrows():
        values = {
            str(value).strip()
            for value in row.tolist()
            if value is not None and not pd.isna(value) and str(value).strip()
        }
        if "Fixture Name" in values and "Area Name" in values and "Lamp Life Remaining" in values:
            return idx
    return 13


def extract_lighting_metadata(raw_df):
    metadata = {
        "reportGenerationTime": None,
        "site": None,
        "reportingPeriodStart": None,
        "reportingPeriodEnd": None,
        "reportingPeriodDuration": None
    }

    label_map = {
        "Report Generation Time:": "reportGenerationTime",
        "Site:": "site",
        "Reporting Period Start Time:": "reportingPeriodStart",
        "Reporting Period End Time:": "reportingPeriodEnd",
        "Reporting Period Duration:": "reportingPeriodDuration"
    }

    for _, row in raw_df.head(20).iterrows():
        cleaned = [normalize_text(value) for value in row.tolist()]
        cleaned = [value for value in cleaned if value]
        if len(cleaned) < 2:
            continue

        label = cleaned[0]
        if label in label_map:
            metadata[label_map[label]] = cleaned[-1]

    report_ts = pd.to_datetime(metadata["reportGenerationTime"], errors="coerce")
    metadata["generatedAt"] = report_ts.isoformat() if pd.notna(report_ts) else None
    return metadata


def merge_lighting_fixture_records(records):
    merged = None
    for record in records:
        if merged is None:
            merged = dict(record)
            continue

        for key, value in record.items():
            if key in {"Fixture Name", "Area Name", "Circuit Name"}:
                if not merged.get(key) and value:
                    merged[key] = value
                continue

            if merged.get(key) is None and value is not None:
                merged[key] = value
            elif isinstance(value, (int, float)) and value is not None:
                current = merged.get(key)
                if current is None or value > current:
                    merged[key] = value

    return merged or {}


def deduplicate_lighting_fixtures(fixtures):
    grouped = {}
    ordered_keys = []

    for fixture in fixtures:
        key = (
            fixture.get("Fixture Name"),
            fixture.get("Area Name"),
            fixture.get("Circuit Name")
        )
        if key not in grouped:
            grouped[key] = []
            ordered_keys.append(key)
        grouped[key].append(fixture)

    deduped = [merge_lighting_fixture_records(grouped[key]) for key in ordered_keys]
    duplicate_count = max(0, len(fixtures) - len(deduped))
    return deduped, duplicate_count


def calculate_lighting_fixture_health_pct(lamp_life_remaining, max_lamp_life=20000):
    lamp_life = pd.to_numeric(lamp_life_remaining, errors="coerce")
    if pd.isna(lamp_life) or max_lamp_life <= 0:
        return None

    return round(max(0.0, min(100.0, (float(lamp_life) / float(max_lamp_life)) * 100.0)), 1)


def load_lighting_data():
    csv_path = LIGHTING_CSV_PATH if os.path.exists(LIGHTING_CSV_PATH) else None
    if not csv_path:
        return {
            "generatedAt": None,
            "sourcePath": None,
            "fixtures": [],
            "meta": {
                "reportGenerationTime": None,
                "site": None,
                "reportingPeriodStart": None,
                "reportingPeriodEnd": None,
                "reportingPeriodDuration": None
            }
        }

    signature = get_file_signature(csv_path)
    cached = _LIGHTING_DATA_CACHE.get(csv_path)
    if cached and cached["signature"] == signature:
        return copy.deepcopy(cached["data"])

    try:
        raw_df = pd.read_csv(csv_path, header=None, encoding="utf-8-sig")
        header_row = detect_lighting_header_row(raw_df)
        metadata = extract_lighting_metadata(raw_df)

        df = pd.read_csv(csv_path, header=header_row, encoding="utf-8-sig")
        df.columns = [normalize_text(col) or "" for col in df.columns]
        df = df.rename(columns={src: dest for src, dest in LIGHTING_COLUMN_ALIASES.items() if src in df.columns})

        for col in LIGHTING_REQUIRED_COLUMNS:
            if col not in df.columns:
                df[col] = None

        df = df[LIGHTING_REQUIRED_COLUMNS].copy()

        df["Fixture Name"] = df["Fixture Name"].apply(normalize_text)
        df["Area Name"] = df["Area Name"].apply(normalize_text)
        df["Circuit Name"] = df["Circuit Name"].apply(normalize_text)

        for col in ["Hours On In Period", "Notional Energy", "Hours On Running", "Lamp Life Remaining"]:
            df[col] = df[col].apply(normalize_number)

        df = df[df["Fixture Name"].notna() & df["Area Name"].notna()].copy()

        raw_fixtures = [
            {
                "Fixture Name": row["Fixture Name"],
                "Area Name": row["Area Name"],
                "Circuit Name": row["Circuit Name"],
                "Hours On In Period": row["Hours On In Period"],
                "Notional Energy": row["Notional Energy"],
                "Hours On Running": row["Hours On Running"],
                "Lamp Life Remaining": row["Lamp Life Remaining"]
            }
            for _, row in df.iterrows()
        ]
        fixtures, duplicate_count = deduplicate_lighting_fixtures(raw_fixtures)

        result = {
            "generatedAt": metadata.get("generatedAt"),
            "sourcePath": csv_path,
            "fixtures": fixtures,
            "channelRuntimeRows": raw_fixtures,
            "meta": {
                "reportGenerationTime": metadata.get("reportGenerationTime"),
                "site": metadata.get("site"),
                "reportingPeriodStart": metadata.get("reportingPeriodStart"),
                "reportingPeriodEnd": metadata.get("reportingPeriodEnd"),
                "reportingPeriodDuration": metadata.get("reportingPeriodDuration"),
                "sourceRowCount": len(raw_fixtures),
                "uniqueFixtureCount": len(fixtures),
                "duplicateRowsCollapsed": duplicate_count
            }
        }
        _LIGHTING_DATA_CACHE[csv_path] = {
            "signature": signature,
            "data": copy.deepcopy(result)
        }
        return result
    except Exception as exc:
        print(f"Lighting CSV read error: {exc}")
        return {
            "generatedAt": None,
            "sourcePath": csv_path,
            "fixtures": [],
            "meta": {
                "reportGenerationTime": None,
                "site": None,
                "reportingPeriodStart": None,
                "reportingPeriodEnd": None,
                "reportingPeriodDuration": None
            }
        }


@app.route("/api/lighting")
def lighting_data():
    return jsonify(load_lighting_data())


# =====================================================
# WWTP API ROUTES (REFINED)
# =====================================================

@app.route("/api/wwtp/latest")
def wwtp_latest():
    """Provides the most recent data points for KPI cards and dashboard sync"""
    return jsonify({
        "effluent":     read_csv("EffluentPump_Total.csv", "value"),
        "rawPump":      read_csv("_RawWaterWastePump-01_Total.csv", "value"),
        "rawTemp":      read_csv("_RawWasteWater_Temp.csv", "value"),
        "pmgEnergy":    read_csv("PMG-WWTP_Energy.csv", "value"),
        "ctrlEnergy":   read_csv("_PM-WWTP-CONTROL-PANEL_Energy.csv", "value")
    })

@app.route("/api/wwtp/history")
def wwtp_history():
    """Handles date-filtered requests for specific chart categories"""
    date_str = request.args.get('date')
    category = request.args.get('category')
    
    # Mapping logic for different chart sections
    category_files = {
        'energy': [("PMG-WWTP_Energy.csv", "pmg"), ("_PM-WWTP-CONTROL-PANEL_Energy.csv", "ctrl")],
        'flow':   [("EffluentPump_Total.csv", "effluent"), ("_RawWaterWastePump-01_Total.csv", "raw")],
        'temp':   [("_RawWasteWater_Temp.csv", "temp")]
    }

    def get_filtered_data(file_name, key):
        path = os.path.join(DATA_DIR, file_name)
        if not os.path.exists(path): return []
        try:
            df = pd.read_csv(path, encoding='utf-8-sig')
            df.columns = [c.strip() for c in df.columns]
            # Handle metadata-prefixed files (history:SM/... uses 2 header rows)
            if 'Timestamp' not in df.columns:
                df = pd.read_csv(path, skiprows=2, encoding='utf-8-sig')
                df.columns = [c.strip() for c in df.columns]

            df['Timestamp'] = df['Timestamp'].str.replace(' ICT', '', regex=False)
            df['dt'] = pd.to_datetime(df['Timestamp'], format='%d-%b-%y %I:%M:%S %p', errors='coerce')
            df = df.dropna(subset=['dt'])

            # Identify the Value column dynamically (first non-meta column)
            skip = {'timestamp', 'trend flags', 'status'}
            val_col = next((c for c in df.columns if c.lower() not in skip), None)
            if not val_col:
                return []

            df[val_col] = pd.to_numeric(df[val_col], errors='coerce')

            if date_str:
                df = df[df['dt'].dt.strftime('%Y-%m-%d') == date_str]
            else:
                df = df.tail(50)

            return [{
                "time": r['dt'].strftime('%H:%M'),
                "value": float(r[val_col]) if pd.notna(r[val_col]) else 0.0
            } for _, r in df.iterrows()]
        except Exception as e:
            print(f"Error filtering {file_name}: {e}")
            return []

    response_data = {}
    if category in category_files:
        for file_name, key in category_files[category]:
            response_data[key] = get_filtered_data(file_name, key)
            
    return jsonify(response_data)

# =====================================================
# SPIRAL BLAST FREEZER API
# =====================================================

@app.route("/api/spiral_blast_freezer")
def spiral_blast_freezer():
    # Spiral freezer datasets
    data_s1 = read_sbf_csv(os.path.join(DATA_DIR, "sbf_spiral1_Data.csv"))
    data_s2 = read_sbf_csv(os.path.join(DATA_DIR, "sbf_spiral2_Data.csv"))
    data_s3 = read_sbf_csv(os.path.join(DATA_DIR, "sbf_spiral3_Data.csv"))

    # Conveyor datasets (NEW LOGIC)
    data_c1 = read_conveyor_csv(os.path.join(DATA_DIR, "sbf_conveyor1.csv"))
    data_c2 = read_conveyor_csv(os.path.join(DATA_DIR, "sbf_conveyor2.csv"))
    data_c3 = read_conveyor_csv(os.path.join(DATA_DIR, "sbf_conveyor3.csv"))

    # Monthly energy
    energy_file = os.path.join(DATA_DIR, "sbf_power_monthly_ENERGY.csv")
    energy_data = read_sbf_csv(energy_file) if os.path.exists(energy_file) else []

    return jsonify({
        "system": "spiral_blast_freezer",
        "status_data": {
            "spiral_01": { "data": data_s1 },
            "spiral_02": { "data": data_s2 },
            "spiral_03": { "data": data_s3 }
        },
        "conveyor_data": {
            "conveyor_01": { "data": data_c1 },
            "conveyor_02": { "data": data_c2 },
            "conveyor_03": { "data": data_c3 }
        },
        "energy": {
            "monthly_energy": energy_data
        }
    })


# ================================================
# MDB API
# ================================================

def read_mdb_daily_consumption(file_name):
    path = os.path.join(DATA_DIR, file_name)
    if not os.path.exists(path):
        return []

    try:
        # Skip the first 2 lines of metadata
        df = pd.read_csv(path, skiprows=2)
        df.columns = [c.strip() for c in df.columns]

        # Clean the timestamp (Remove ' ICT') and parse
        df['Timestamp'] = df['Timestamp'].str.replace(' ICT', '', regex=False)
        df['dt'] = pd.to_datetime(df['Timestamp'], format='%d-%b-%y %I:%M:%S %p')
        df['date'] = df['dt'].dt.strftime('%d-%b') # Format as "16-Dec"

        # Identify the 'Value' column (could be 'Value (kW-hr)' or 'Value')
        val_col = [c for c in df.columns if 'Value' in c][0]

        # Calculate daily consumption: Max reading - Min reading for that day
        # This gives the total kWh used within that 24-hour window
        daily = df.groupby('date')[val_col].agg(['min', 'max']).reset_index()
        daily['consumption'] = daily['max'] - daily['min']
        

        # Sort by date (pandas grouping might scramble chronological order, 
        # so we ensure it follows the original data sequence)
        return daily.rename(columns={'date': 'time', 'consumption': 'kwh'}).to_dict(orient='records')
    except Exception as e:
        print(f"🔥 Daily Calc Error ({file_name}): {e}")
        return []

def get_latest_csv_timestamp(file_name):
    path = os.path.join(DATA_DIR, file_name)
    if not os.path.exists(path):
        return None

    signature = get_file_signature(path)
    cached = _CSV_TIMESTAMP_CACHE.get(file_name)
    if cached and cached["signature"] == signature:
        return cached["value"]

    try:
        with open(path, mode="r", encoding="utf-8-sig", errors="ignore") as f:
            lines = f.readlines()

        header_idx = next((i for i, line in enumerate(lines) if "timestamp" in line.lower()), -1)
        if header_idx == -1:
            return None

        content = "".join(lines[header_idx:])
        reader = csv.DictReader(io.StringIO(content))
        latest_dt = None

        for row in reader:
            clean_row = {k.strip(): v for k, v in row.items() if k}
            ts_val = next((v for k, v in clean_row.items() if "timestamp" in k.lower()), None)
            if not ts_val:
                continue

            ts_clean = str(ts_val).replace(" ICT", "").strip()
            dt = pd.to_datetime(ts_clean, format="%d-%b-%y %I:%M:%S %p", errors="coerce")
            if pd.isna(dt):
                dt = pd.to_datetime(ts_clean, dayfirst=True, errors="coerce")
            if pd.notna(dt):
                latest_dt = dt

        value = latest_dt.isoformat() if latest_dt is not None else None
        _CSV_TIMESTAMP_CACHE[file_name] = {
            "signature": signature,
            "value": value
        }
        return value
    except Exception as e:
        print(f"MDB latest timestamp error ({file_name}): {e}")
        return None

@app.route("/api/mdb")
def mdb_data():
    return jsonify(collect_mdb_data())


@app.route("/api/mdb/summary")
def mdb_summary():
    def latest_and_previous(file_name, value_key):
        records = read_csv(file_name, value_key)
        latest = records[-1].get(value_key) if records else 0
        previous = records[-2].get(value_key) if len(records) >= 2 else latest
        return {
            "latest": latest,
            "previous": previous,
            "time": records[-1].get("time") if records else None,
        }

    energy_files = {
        "emdb_1": "mdb_emdb.csv",
        "mdb_6": "mdb6_energy.csv",
        "mdb_7": "mdb7_energy.csv",
        "mdb_8": "mdb8_energy.csv",
        "mdb_9": "mdb9_energy.csv",
        "mdb_10": "mdb10_energy.csv",
    }
    generator_files = {
        "gen_1": "mdb_gen1_RT.csv",
        "gen_2": "mdb_gen2_RT.csv",
        "gen_3": "mdb_gen3_RT.csv",
        "gen_4": "mdb_gen4_RT.csv",
    }

    energy = {
        key: latest_and_previous(file_name, "kwh")
        for key, file_name in energy_files.items()
    }
    generators = {
        key: latest_and_previous(file_name, "runtime")
        for key, file_name in generator_files.items()
    }

    return jsonify({
        "energy": energy,
        "generators": generators,
        "meta": {
            "last_synced": max([
                ts for ts in [
                    get_latest_csv_timestamp("mdb_emdb.csv"),
                    get_latest_csv_timestamp("mdb6_energy.csv"),
                    get_latest_csv_timestamp("mdb7_energy.csv"),
                    get_latest_csv_timestamp("mdb8_energy.csv"),
                    get_latest_csv_timestamp("mdb9_energy.csv"),
                    get_latest_csv_timestamp("mdb10_energy.csv"),
                    get_latest_csv_timestamp("mdb_gen1_RT.csv"),
                    get_latest_csv_timestamp("mdb_gen2_RT.csv"),
                    get_latest_csv_timestamp("mdb_gen3_RT.csv"),
                    get_latest_csv_timestamp("mdb_gen4_RT.csv")
                ] if ts
            ], default=None)
        }
    })
@app.route("/api/mdb/history")
def mdb_history():
    date_str = request.args.get('date')
    time_str = request.args.get('time')
    category = request.args.get('category')
    
    def get_filtered_mdb(file_name, value_key, normalize_gen=False):
        path = os.path.join(DATA_DIR, file_name)
        if not os.path.exists(path):
            print(f"⚠️ File missing: {path}")
            return {"date_used": None, "points": []}
            
        try:
            # 1. ATTEMPT TO FIND THE HEADER
            # We try skipping 0 rows, then 1, then 2 to find where 'Timestamp' lives
            df = None
            for s in [2, 1, 0]:
                temp_df = pd.read_csv(path, skiprows=s, nrows=0) # Just read headers
                cols = [c.strip().replace('\ufeff', '') for c in temp_df.columns]
                if any('Time' in c for c in cols):
                    df = pd.read_csv(path, skiprows=s)
                    df.columns = cols
                    break
            
            if df is None:
                # Fallback: If we still can't find it, force read without skipping
                df = pd.read_csv(path)
                df.columns = [c.strip().replace('\ufeff', '') for c in df.columns]

            # 2. DYNAMICALLY FIND COLUMNS
            time_col = [c for c in df.columns if 'Time' in c]
            val_col = [c for c in df.columns if any(x in c.lower() for x in ['value', 'kwh', 'runtime', '4', '177'])]

            if not time_col:
                print(f"❌ Still no Time column in {file_name}. Headers found: {list(df.columns)}")
                return {"date_used": None, "points": []}

            t_name = time_col[0]
            v_name = val_col[0] if val_col else df.columns[-1] # Fallback to last column if 'Value' is missing

            # 3. Process Timestamps
            df[t_name] = df[t_name].astype(str).str.replace(' ICT', '', regex=False)
            df['dt'] = pd.to_datetime(df[t_name], dayfirst=True, errors='coerce')
            df = df.dropna(subset=['dt'])

            # 4. Filtering Logic
            df['date_only'] = df['dt'].dt.strftime('%Y-%m-%d')
            available_dates = df['date_only'].unique()
            if len(available_dates) == 0:
                return {"date_used": None, "points": []}
            
            # Use provided date or the latest one in the file
            target_date = date_str
            if not target_date or target_date not in available_dates:
                target_date = available_dates[-1] 
            
            df_filtered = df[df['date_only'] == target_date].copy()
            
            # 5. Map Data
            multiplier = 1 / 3600 if (normalize_gen and ("/s" in v_name.lower() or "(s)" in v_name.lower())) else 1.0

            return {
                "date_used": target_date,
                "points": [{
                    "time": r['dt'].strftime('%H:%M'), 
                    "value": round(float(r[v_name]) * multiplier, 2)
                } for _, r in df_filtered.iterrows()]
            }
            
        except Exception as e:
            print(f"🔥 Error processing {file_name}: {e}")
            return {"date_used": None, "points": []}

    def filter_points_to_selected_time(result):
        points = result.get("points", [])
        if not points:
            return {"date_used": result.get("date_used"), "time_used": None, "points": []}

        if not time_str:
            return {
                "date_used": result.get("date_used"),
                "time_used": points[-1]["time"],
                "points": points,
            }

        eligible_points = [point for point in points if point["time"] <= time_str]
        if not eligible_points:
            eligible_points = [points[0]]

        return {
            "date_used": result.get("date_used"),
            "time_used": eligible_points[-1]["time"],
            "points": eligible_points,
        }

    response_data = {}
    if category == 'energy':
        res = get_filtered_mdb("mdb_emdb.csv", "kwh")
        response_data['emdb_1'] = res['points']
        response_data['selected_date'] = res['date_used']
    elif category == 'distribution':
        panel_files = {
            'mdb_6': "mdb6_energy.csv",
            'mdb_7': "mdb7_energy.csv",
            'mdb_8': "mdb8_energy.csv",
            'mdb_9': "mdb9_energy.csv",
            'mdb_10': "mdb10_energy.csv",
        }

        panel_results = {
            key: filter_points_to_selected_time(get_filtered_mdb(file_name, "kwh"))
            for key, file_name in panel_files.items()
        }

        selected_date = next(
            (result['date_used'] for result in panel_results.values() if result['date_used']),
            None
        )
        selected_time = next(
            (result['time_used'] for result in panel_results.values() if result['time_used']),
            None
        )

        response_data['distribution'] = {
            key: (result['points'][-1]['value'] if result['points'] else 0)
            for key, result in panel_results.items()
        }
        response_data['selected_date'] = selected_date
        response_data['selected_time'] = selected_time
    elif category == 'gens':
        res1 = get_filtered_mdb("mdb_gen1_RT.csv", "runtime", True)
        response_data['gen_1'] = res1['points']
        response_data['gen_2'] = get_filtered_mdb("mdb_gen2_RT.csv", "runtime", True)['points']
        response_data['gen_3'] = get_filtered_mdb("mdb_gen3_RT.csv", "runtime", True)['points']
        response_data['gen_4'] = get_filtered_mdb("mdb_gen4_RT.csv", "runtime", True)['points']
        response_data['selected_date'] = res1['date_used']
            
    return jsonify(response_data)

# =====================================================
# WATER TREATMENT PLANT (WTP) API
# =====================================================

def get_flow_rate(file_name):
    """Reads current flow rate (m3/hr) directly from a Flow CSV file."""
    path = os.path.join(DATA_DIR, file_name)
    if not os.path.exists(path): return 0
    try:
        df = pd.read_csv(path, encoding='utf-8-sig')
        df.columns = [c.strip() for c in df.columns]
        # Find the flow value column (first non-Timestamp column)
        val_col = next((c for c in df.columns if 'timestamp' not in c.lower()), None)
        if not val_col:
            return 0
        df[val_col] = pd.to_numeric(df[val_col], errors='coerce')
        last = df.dropna(subset=[val_col]).tail(1)
        if not last.empty:
            return round(float(last.iloc[0][val_col]), 2)
    except Exception as e:
        print(f"Flow rate error ({file_name}): {e}")
    return 0

@app.route("/api/wtp/chlorine")
def wtp_chlorine():
    date_str = request.args.get('date')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    source = request.args.get('source', 'ro')
    
    # Map source to CSV file
    file_map = {
        'ro': 'RES102ROWaterSupply_ResCl2.csv',
        'softwater1': 'RES101SoftWaterSupplyNo1_ResCl2.csv',
        'softwater2': 'RES103SoftWaterSupplyNo2_ResCl2.csv'
    }
    
    file_name = file_map.get(source, 'RES102ROWaterSupply_ResCl2.csv')
    path = os.path.join(DATA_DIR, file_name)
    data = []
    
    if not os.path.exists(path): 
        print(f"❌ FILE MISSING: {path}")
        return jsonify([])

    try:
        df = pd.read_csv(path, encoding='utf-8-sig')
        df.columns = [c.strip() for c in df.columns]
        # Handle metadata-prefixed files (history:SM/... header takes 2 rows)
        if 'Timestamp' not in df.columns:
            df = pd.read_csv(path, skiprows=2, encoding='utf-8-sig')
            df.columns = [c.strip() for c in df.columns]
        df['Timestamp'] = df['Timestamp'].str.replace(' ICT', '', regex=False)
        df['dt'] = pd.to_datetime(df['Timestamp'], format='%d-%b-%y %I:%M:%S %p', errors='coerce')
        df = df.dropna(subset=['dt'])

        # Find the value column (mg)
        val_col = next((c for c in df.columns if c.lower() not in ('timestamp', 'trend flags', 'status') and 'timestamp' not in c.lower()), None)

        full_df = df.copy()

        # Filter by date range, single date, or fall back to latest 50.
        # The WTP files are manually inputted/static in some deployments, so a
        # "today" filter can be empty even when the latest valid readings exist.
        if start_date and end_date:
            df = df[(df['dt'].dt.strftime('%Y-%m-%d') >= start_date) &
                    (df['dt'].dt.strftime('%Y-%m-%d') <= end_date)]
        elif date_str:
            df = df[df['dt'].dt.strftime('%Y-%m-%d') == date_str]
        else:
            df = df.tail(50)

        if df.empty:
            df = full_df.tail(50)

        multi_day = (start_date and end_date and start_date != end_date) or (not date_str and not start_date)
        for _, row in df.iterrows():
            data.append({
                "time": row['dt'].strftime('%d %b %H:%M') if multi_day else row['dt'].strftime('%H:%M'),
                "mg": float(row.get('Value (mg)', row.get(val_col, 0) if val_col else 0))
            })
    except Exception as e:
        print(f"Chlorine Filter Error: {e}")
    return jsonify(data)

@app.route("/api/wtp/pressure")
def wtp_pressure():
    date_str = request.args.get('date')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    source = request.args.get('source', 'ro')
    
    # Map source to CSV file
    file_map = {
        'ro': 'PT102ROWaterSupply_Pres.csv',
        'softwater1': 'PT101SoftWaterSupplyNo1_Pres.csv',
        'softwater2': 'PT103SoftWaterSupplyNo2_Pres.csv'
    }

    file_name = file_map.get(source, 'PT102ROWaterSupply_Pres.csv')
    path = os.path.join(DATA_DIR, file_name)
    data = []

    if not os.path.exists(path):
        print(f"❌ FILE MISSING: {path}")
        return jsonify([])

    try:
        df = pd.read_csv(path)
        df.columns = [c.strip() for c in df.columns]
        df['Timestamp'] = df['Timestamp'].str.replace(' ICT', '', regex=False)
        df['dt'] = pd.to_datetime(df['Timestamp'], format='%d-%b-%y %I:%M:%S %p')

        # Find the bar value column dynamically
        bar_col = next((c for c in df.columns if 'bar' in c.lower() or 'pres' in c.lower()), None)
        if not bar_col:
            print(f"Pressure: no bar/pres column found in {file_name}, columns: {list(df.columns)}")
            return jsonify([])

        full_df = df.copy()

        # Filter by date range, single date, or fall back to latest 50.
        # The WTP files are manually inputted/static in some deployments, so a
        # "today" filter can be empty even when the latest valid readings exist.
        if start_date and end_date:
            df = df[(df['dt'].dt.strftime('%Y-%m-%d') >= start_date) &
                    (df['dt'].dt.strftime('%Y-%m-%d') <= end_date)]
        elif date_str:
            df = df[df['dt'].dt.strftime('%Y-%m-%d') == date_str]
        else:
            df = df.tail(50)

        if df.empty:
            df = full_df.tail(50)

        multi_day = (start_date and end_date and start_date != end_date) or (not date_str and not start_date)
        for _, row in df.iterrows():
            data.append({
                "time": row['dt'].strftime('%d %b %H:%M') if multi_day else row['dt'].strftime('%H:%M'),
                "bar": float(row[bar_col])
            })
    except Exception as e:
        print(f"Pressure Filter Error: {e}")
    
    return jsonify(data)

def get_wtp_raw_data():
    return {
        "flow_totals": {
            "deep_well":     read_csv("FIT-101-DeepWellWater_Total.csv", "m3"),
            "soft_water_1":  read_csv("FIT-102-SoftWaterSupply-01_Total.csv", "m3"),
            "soft_water_2":  read_csv("FIT-104-SoftWaterSupply-02_Total.csv", "m3"),
            "ro_water":      read_csv("FIT-103-ROWaterSupply_Total.csv", "m3"),
            "fire_water":    read_csv("FIT-105-FireWaterTank_Total.csv", "m3")
        },
        "flow_rates": {
            "deep_well":    get_flow_rate("FIT101DeepWellWater_Flow.csv"),
            "soft_water_1": get_flow_rate("FIT102SoftWaterSupplyNo1_Flow.csv"),
            "soft_water_2": get_flow_rate("FIT104SoftWaterSupplyNo2_Flow.csv"),
            "ro_water":     get_flow_rate("FIT103ROWaterSupply_Flow.csv"),
            "fire_water":   get_flow_rate("FIT105FireWaterTank_Flow.csv")
        },
        "pressure": {
            "soft_water":    read_csv("PT101SoftWaterSupplyNo1_Pres.csv", "bar"),
            "ro_supply":     read_csv("PT102ROWaterSupply_Pres.csv", "bar")
        },
        "quality": {
            "ro_chlorine":   read_csv("RES102ROWaterSupply_ResCl2.csv", "mg")
        }
    }

# 2. This is the API route for your JS dashboard
@app.route("/api/wtp")
def wtp_api():
    return jsonify(get_wtp_raw_data())


def build_projection_payload():
    risk_items = []

    def add_risk(severity, system, title, message):
        risk_items.append({
            "severity": severity,
            "system": system,
            "title": title,
            "message": message,
        })

    # MDB / Generator
    emdb_projection = calculate_cumulative_projection(
        load_numeric_timeseries("mdb_emdb.csv", ["Value (kW-hr)", "Value", "kWh"])
    )
    mdb_panel_projections = {
        key: calculate_cumulative_projection(load_numeric_timeseries(file_name, ["Value (kW-hr)", "Value", "kWh"]))
        for key, file_name in {
            "MDB-6": "mdb6_energy.csv",
            "MDB-7": "mdb7_energy.csv",
            "MDB-8": "mdb8_energy.csv",
            "MDB-9": "mdb9_energy.csv",
            "MDB-10": "mdb10_energy.csv",
        }.items()
    }
    mdb_total_projected = round(sum(item["projected"] or 0 for item in mdb_panel_projections.values()), 3)
    mdb_total_actual = round(sum(item["actual"] or 0 for item in mdb_panel_projections.values()), 3)
    mdb_previous_day = sum(item["previous_day_total"] or 0 for item in mdb_panel_projections.values()) or None
    mdb_baseline_7d = sum(item["baseline_7d"] or 0 for item in mdb_panel_projections.values()) or None
    generator_summary = mdb_summary().get_json(silent=True) or {"generators": {}}
    active_generators = 0
    for key in ["gen_1", "gen_2", "gen_3", "gen_4"]:
        generator = generator_summary.get("generators", {}).get(key, {})
        latest = generator.get("latest") or 0
        previous = generator.get("previous") or 0
        if latest > previous and previous != 0:
            active_generators += 1

    generator_note = (
        "No projection available from current generator state"
        if active_generators == 0
        else f"Backup status stable under current conditions ({active_generators}/4 active)"
    )

    # Lighting
    lighting_payload = load_lighting_data()
    lighting_fixtures = lighting_payload.get("fixtures", [])
    lighting_total_energy = round(sum((fixture.get("Notional Energy") or 0) for fixture in lighting_fixtures), 3)
    lighting_generated_at = pd.to_datetime(lighting_payload.get("generatedAt"), errors="coerce")
    if pd.isna(lighting_generated_at):
        lighting_generated_at = pd.to_datetime(
            get_source_timestamp(LIGHTING_CSV_FILENAME),
            errors="coerce"
        )
    lighting_elapsed_hours = None
    lighting_projected_energy = None
    if pd.notna(lighting_generated_at):
        day_start = lighting_generated_at.replace(hour=0, minute=0, second=0, microsecond=0)
        lighting_elapsed_hours = max((lighting_generated_at - day_start).total_seconds() / 3600, 0.25)
        lighting_projected_energy = round((lighting_total_energy / lighting_elapsed_hours) * PROJECTION_TARGET_HOURS, 3)

    lighting_warning = 0
    lighting_critical = 0
    replacement_days = []
    for fixture in lighting_fixtures:
        lamp_remaining = pd.to_numeric(fixture.get("Lamp Life Remaining"), errors="coerce")
        hours_on_in_period = pd.to_numeric(fixture.get("Hours On In Period"), errors="coerce")
        if pd.notna(lamp_remaining):
            health_pct = max(0.0, min(100.0, (float(lamp_remaining) / 20000.0) * 100))
            if health_pct < PROJECTION_CRITICAL_HEALTH_PCT:
                lighting_critical += 1
            elif health_pct < PROJECTION_WARNING_HEALTH_PCT:
                lighting_warning += 1

            if pd.notna(hours_on_in_period) and float(hours_on_in_period) > 0:
                replacement_days.append(round(float(lamp_remaining) / float(hours_on_in_period), 1))

    if lighting_critical or lighting_warning:
        add_risk(
            "critical" if lighting_critical else "warning",
            "Lighting",
            "Fixture replacement due soon",
            f"{lighting_critical} critical and {lighting_warning} warning fixtures are approaching replacement thresholds.",
        )
    lighting_health_values = [
        max(0.0, min(100.0, (float(pd.to_numeric(fixture.get("Lamp Life Remaining"), errors="coerce")) / 20000.0) * 100))
        for fixture in lighting_fixtures
        if pd.notna(pd.to_numeric(fixture.get("Lamp Life Remaining"), errors="coerce"))
    ]
    average_lighting_health = round(sum(lighting_health_values) / len(lighting_health_values), 1) if lighting_health_values else None

    # WWTP
    wwtp_effluent = calculate_cumulative_projection(load_numeric_timeseries("EffluentPump_Total.csv", ["Value", "m3"]))
    wwtp_raw = calculate_cumulative_projection(load_numeric_timeseries("_RawWaterWastePump-01_Total.csv", ["Value", "m3"]))
    wwtp_pmg_energy = calculate_cumulative_projection(load_numeric_timeseries("PMG-WWTP_Energy.csv", ["Value", "Energy"]))
    wwtp_ctrl_energy = calculate_cumulative_projection(load_numeric_timeseries("_PM-WWTP-CONTROL-PANEL_Energy.csv", ["Value", "Energy"]))
    wwtp_temp_trend = calculate_trend_projection(load_numeric_timeseries("_RawWasteWater_Temp.csv", ["Value (°C)", "Value", "Temp"]), 1)
    wwtp_total_energy_projected = round((wwtp_pmg_energy["projected"] or 0) + (wwtp_ctrl_energy["projected"] or 0), 3)
    wwtp_treatment_ratio = safe_divide(wwtp_effluent["projected"], wwtp_raw["projected"])
    wwtp_energy_intensity = safe_divide(wwtp_total_energy_projected, wwtp_effluent["projected"])
    if (wwtp_raw["projected"] or 0) > (wwtp_effluent["projected"] or 0) * 1.2 and (wwtp_effluent["projected"] or 0) > 0:
        add_risk(
            "warning",
            "WWTP",
            "Influent exceeds treated output",
            "Projected raw inflow is materially above treated wastewater volume. Review pump loading and process balance.",
        )

    # WTP
    wtp_sources = {
        "RO Water": calculate_cumulative_projection(load_numeric_timeseries("FIT-103-ROWaterSupply_Total.csv", ["m3", "Value"])),
        "Softwater 1": calculate_cumulative_projection(load_numeric_timeseries("FIT-102-SoftWaterSupply-01_Total.csv", ["m3", "Value"])),
        "Softwater 2": calculate_cumulative_projection(load_numeric_timeseries("FIT-104-SoftWaterSupply-02_Total.csv", ["m3", "Value"])),
    }
    wtp_total_projected = round(sum(item["projected"] or 0 for item in wtp_sources.values()), 3)
    wtp_contribution = {
        source: safe_divide(item["projected"], wtp_total_projected, 4)
        for source, item in wtp_sources.items()
    }
    low_sources = [source for source, share in wtp_contribution.items() if share is not None and share < 0.15]
    high_sources = [source for source, share in wtp_contribution.items() if share is not None and share > 0.7]
    if low_sources or high_sources:
        detail_parts = []
        if high_sources:
            detail_parts.append("high share: " + ", ".join(high_sources))
        if low_sources:
            detail_parts.append("low share: " + ", ".join(low_sources))
        add_risk(
            "warning",
            "WTP",
            "Source contribution imbalance",
            "Projected treated-water split is uneven (" + "; ".join(detail_parts) + ").",
        )

    # Boiler
    boiler_gas = calculate_cumulative_projection(load_numeric_timeseries("boiler_gas_total.csv", ["Value (kg)", "Value", "kg"]))
    boiler_direct_steam = calculate_cumulative_projection(load_numeric_timeseries("boiler_directsteam_meterflow_total.csv", ["Value (kg)", "Value", "kg"]))
    boiler_indirect_steam = calculate_cumulative_projection(load_numeric_timeseries("boiler_indirectsteam_meterflow.csv", ["Value (kg)", "Value", "kg"]))
    boiler_direct_energy = calculate_cumulative_projection(load_numeric_timeseries("boiler_direct_energy.csv", ["Value (kW-hr)", "Value", "kWh"]))
    boiler_indirect_energy = calculate_cumulative_projection(load_numeric_timeseries("boiler_indirect_energy.csv", ["Value (kW-hr)", "Value", "kWh"]))
    boiler_total_steam_projected = round((boiler_direct_steam["projected"] or 0) + (boiler_indirect_steam["projected"] or 0), 3)
    boiler_total_energy_projected = round((boiler_direct_energy["projected"] or 0) + (boiler_indirect_energy["projected"] or 0), 3)
    boiler_steam_to_gas = safe_divide(boiler_total_steam_projected, boiler_gas["projected"])
    boiler_kwh_per_steam = safe_divide(boiler_total_energy_projected, boiler_total_steam_projected)
    boiler_direct_share = safe_divide(boiler_direct_energy["projected"], boiler_total_energy_projected, 4)
    boiler_indirect_share = safe_divide(boiler_indirect_energy["projected"], boiler_total_energy_projected, 4)

    # Air compressor
    compressor_energy = calculate_cumulative_projection(load_numeric_timeseries("aircompressor_energy.csv", ["Value", "Energy", "kWh"]))
    compressor_flow = calculate_cumulative_projection(load_numeric_timeseries("airmeter_flow.csv", ["Value (m³)", "Value", "m3"]))
    compressor_dewpoint = calculate_trend_projection(load_numeric_timeseries("air_dewpoint.csv", ["Value (psi)", "Value", "Dewpoint"]), 1)
    compressor_specific_power = safe_divide(compressor_energy["projected"], compressor_flow["projected"])
    compressor_specific_power_baseline = safe_divide(
        compressor_energy["previous_day_total"],
        compressor_flow["previous_day_total"]
    )
    if (
        compressor_specific_power is not None
        and compressor_specific_power_baseline is not None
        and compressor_specific_power > compressor_specific_power_baseline * PROJECTION_COMPRESSOR_SPECIFIC_POWER_WARN
    ):
        add_risk(
            "warning",
            "Air Compressor",
            "Specific power increasing",
            f"Projected specific power is {compressor_specific_power:.2f} kWh/m3 versus a recent baseline of {compressor_specific_power_baseline:.2f}.",
        )

    # Spiral freezer
    freezer_units = []
    for freezer_label, freezer_file in {
        "Spiral 1": "sbf_spiral1_Data.csv",
        "Spiral 2": "sbf_spiral2_Data.csv",
        "Spiral 3": "sbf_spiral3_Data.csv",
    }.items():
        rows = read_sbf_csv(os.path.join(DATA_DIR, freezer_file))
        if not rows:
            freezer_units.append({
                "name": freezer_label,
                "top_temp": None,
                "top_temp_projected": None,
                "bottom_temp": None,
                "bottom_temp_projected": None,
                "pressure": None,
                "pressure_projected": None,
                "runtime_projected": None,
                "threshold_hours": None,
                "status": "unavailable",
                "subtitle": "Insufficient trend data",
            })
            continue

        frame = pd.DataFrame(rows)
        frame["dt"] = pd.to_datetime(frame["time"], format="%H:%M:%S", errors="coerce")
        frame = frame.dropna(subset=["dt"]).sort_values("dt")

        def freezer_trend(column_name):
            if column_name not in frame.columns:
                return {"latest": None, "projected": None, "slope_per_hour": None}
            temp_df = frame[["dt", column_name]].rename(columns={column_name: "value"}).dropna()
            return calculate_trend_projection(temp_df, 1)

        top_trend = freezer_trend("tef01")
        bottom_trend = freezer_trend("tef02")
        pressure_trend = freezer_trend("pt02")
        runtime_trend = None
        if "runtime" in frame.columns:
            runtime_df = frame[["dt", "runtime"]].rename(columns={"runtime": "value"}).dropna()
            if not runtime_df.empty:
                runtime_day = runtime_df.iloc[-1]
                elapsed_hours = max((pd.Timestamp(runtime_day["dt"]) - runtime_df.iloc[0]["dt"]).total_seconds() / 3600, 0.25)
                runtime_projected = round((float(runtime_day["value"]) / elapsed_hours) * PROJECTION_TARGET_HOURS, 2)
                runtime_trend = runtime_projected

        temp_limit_hours = calculate_threshold_forecast(
            top_trend.get("latest"),
            top_trend.get("slope_per_hour"),
            upper_limit=PROJECTION_FREEZER_TEMP_LIMIT
        )
        if temp_limit_hours is not None and temp_limit_hours <= 8:
            add_risk(
                "critical" if temp_limit_hours <= 2 else "warning",
                "Spiral Freezer",
                f"{freezer_label} temperature breach risk",
                f"{freezer_label} is trending toward the {-18} deg C threshold in about {temp_limit_hours:.1f} hours.",
            )

        freezer_units.append({
            "name": freezer_label,
            "top_temp": top_trend.get("latest"),
            "top_temp_projected": top_trend.get("projected"),
            "bottom_temp": bottom_trend.get("latest"),
            "bottom_temp_projected": bottom_trend.get("projected"),
            "pressure": pressure_trend.get("latest"),
            "pressure_projected": pressure_trend.get("projected"),
            "runtime_projected": runtime_trend,
            "threshold_hours": temp_limit_hours,
            "status": "warning" if temp_limit_hours is not None and temp_limit_hours <= 8 else "normal",
            "subtitle": "Projected 1-hour operating drift" if top_trend.get("projected") is not None else "Insufficient trend data",
        })

    energy_cards = [
        build_metric_card(
            "projected-mdb-1",
            "Projected MDB-1 kWh",
            emdb_projection["projected"],
            "kWh",
            (
                f"Vs previous day {calculate_projection_variance(emdb_projection['projected'], emdb_projection['previous_day_total'])}%"
                if calculate_projection_variance(emdb_projection["projected"], emdb_projection["previous_day_total"]) is not None
                else "Previous-day variance unavailable"
            ),
        ),
        build_metric_card(
            "projected-total-mdb",
            "Projected Total MDB kWh",
            mdb_total_projected,
            "kWh",
            (
                f"Vs 7-day baseline {calculate_projection_variance(mdb_total_projected, mdb_baseline_7d)}%"
                if calculate_projection_variance(mdb_total_projected, mdb_baseline_7d) is not None
                else "7-day baseline unavailable"
            ),
        ),
        build_metric_card(
            "projected-lighting-kwh",
            "Projected Lighting kWh",
            lighting_projected_energy,
            "kWh",
            f"{len(lighting_fixtures)} fixtures included" if lighting_fixtures else "Insufficient lighting energy data",
        ) if lighting_fixtures else build_empty_metric_card("projected-lighting-kwh", "Projected Lighting kWh", "Insufficient lighting energy data"),
        build_metric_card(
            "projected-boiler-kwh",
            "Projected Boiler kWh",
            boiler_total_energy_projected,
            "kWh",
            "Direct and indirect boiler panels combined",
        ),
        build_metric_card(
            "projected-air-kwh",
            "Projected Air Compressor kWh",
            compressor_energy["projected"],
            "kWh",
            (
                f"Vs previous day {calculate_projection_variance(compressor_energy['projected'], compressor_energy['previous_day_total'])}%"
                if calculate_projection_variance(compressor_energy["projected"], compressor_energy["previous_day_total"]) is not None
                else "Previous-day variance unavailable"
            ),
        ),
    ]

    water_cards = [
        build_metric_card("projected-wwtp-treated", "Projected WWTP Treated Volume", wwtp_effluent["projected"], "m3", "Effluent pump total"),
        build_metric_card("projected-wwtp-raw", "Projected WWTP Raw Inflow", wwtp_raw["projected"], "m3", "Raw wastewater pump total"),
        build_metric_card("projected-wtp-treated", "Projected WTP Treated Volume", wtp_total_projected, "m3", "RO + Softwater 1 + Softwater 2"),
        build_metric_card("projected-ro", "Projected RO Volume", wtp_sources["RO Water"]["projected"], "m3", "Projected end-of-day"),
        build_metric_card("projected-soft1", "Projected Softwater 1", wtp_sources["Softwater 1"]["projected"], "m3", "Projected end-of-day"),
        build_metric_card("projected-soft2", "Projected Softwater 2", wtp_sources["Softwater 2"]["projected"], "m3", "Projected end-of-day"),
        build_metric_card("projected-air-flow", "Projected Compressed Air Flow", compressor_flow["projected"], "m3", "End-of-day air total"),
    ]

    thermal_cards = [
        build_metric_card(
            "projected-wwtp-temp",
            "WWTP Raw Water Temperature",
            wwtp_temp_trend["projected"],
            "deg C",
            "1-hour trend projection" if wwtp_temp_trend["projected"] is not None else "No trend data",
        ) if wwtp_temp_trend["projected"] is not None else build_empty_metric_card("projected-wwtp-temp", "WWTP Raw Water Temperature", "No trend data"),
        build_metric_card(
            "projected-dewpoint",
            "Air Compressor Dewpoint",
            compressor_dewpoint["projected"],
            "psi",
            "1-hour trend projection" if compressor_dewpoint["projected"] is not None else "No trend data",
        ) if compressor_dewpoint["projected"] is not None else build_empty_metric_card("projected-dewpoint", "Air Compressor Dewpoint", "No trend data"),
        build_metric_card(
            "boiler-efficiency-trend",
            "Boiler Efficiency Trend",
            boiler_steam_to_gas,
            "kg/kg",
            "Steam-to-gas ratio used as current efficiency indicator" if boiler_steam_to_gas is not None else "Insufficient data",
        ) if boiler_steam_to_gas is not None else build_empty_metric_card("boiler-efficiency-trend", "Boiler Efficiency Trend", "Insufficient data"),
    ]

    ratio_cards = [
        build_metric_card("wwtp-treatment-ratio", "WWTP Projected Treatment Ratio", wwtp_treatment_ratio, "", "Treated / raw inflow"),
        build_metric_card("wwtp-kwh-per-m3", "WWTP Projected kWh per m3", wwtp_energy_intensity, "kWh/m3", "PMG + control panel energy"),
        build_metric_card("boiler-steam-gas-ratio", "Boiler Projected Steam-to-Gas Ratio", boiler_steam_to_gas, "kg/kg", "Projected end-of-day ratio"),
        build_metric_card("boiler-kwh-per-steam", "Boiler Projected kWh per kg Steam", boiler_kwh_per_steam, "kWh/kg", "Projected electrical intensity"),
        build_metric_card("air-specific-power", "Air Compressor Projected Specific Power", compressor_specific_power, "kWh/m3", "Projected energy / flow"),
        build_metric_card(
            "lighting-health",
            "Lighting Fixture Health",
            average_lighting_health,
            "%",
            (
                f"Avg {round(sum(replacement_days) / len(replacement_days), 1)} days remaining to replacement"
                if replacement_days
                else "Days remaining unavailable"
            ),
        ) if lighting_fixtures else build_empty_metric_card("lighting-health", "Lighting Fixture Health", "No fixture data"),
    ]

    systems_covered = sum([
        1 if emdb_projection["projected"] is not None or any(item["projected"] is not None for item in mdb_panel_projections.values()) else 0,
        1 if lighting_projected_energy is not None else 0,
        1 if any(unit.get("top_temp_projected") is not None for unit in freezer_units) else 0,
        1 if (wwtp_effluent["projected"] is not None or wwtp_raw["projected"] is not None) else 0,
        1 if any(item["projected"] is not None for item in wtp_sources.values()) else 0,
        1 if boiler_gas["projected"] is not None or boiler_total_energy_projected is not None else 0,
        1 if compressor_energy["projected"] is not None else 0,
    ])

    total_projected_energy = round(
        sum(
            value or 0
            for value in [
                mdb_total_projected,
                lighting_projected_energy,
                boiler_total_energy_projected,
                compressor_energy["projected"],
                wwtp_total_energy_projected,
            ]
        ),
        3,
    )
    total_projected_water = round(
        sum(
            value or 0
            for value in [
                wwtp_effluent["projected"],
                wwtp_raw["projected"],
                wtp_total_projected,
                compressor_flow["projected"],
            ]
        ),
        3,
    )

    latest_timestamps = [
        value
        for value in [
            emdb_projection["latest_dt"],
            *(item["latest_dt"] for item in mdb_panel_projections.values()),
            lighting_generated_at if pd.notna(lighting_generated_at) else None,
            wwtp_effluent["latest_dt"],
            wwtp_raw["latest_dt"],
            boiler_gas["latest_dt"],
            compressor_energy["latest_dt"],
            compressor_flow["latest_dt"],
        ]
        if value is not None and not pd.isna(value)
    ]
    page_last_synced = max(latest_timestamps).isoformat() if latest_timestamps else None

    return {
        "meta": {
            "last_synced": page_last_synced,
            "generator_note": generator_note,
        },
        "top_kpis": {
            "projected_energy_total": total_projected_energy,
            "projected_water_total": total_projected_water,
            "systems_covered": systems_covered,
            "systems_total": 7,
            "risk_count": len(risk_items),
        },
        "energy_forecast": {
            "cards": energy_cards,
            "comparison_chart": {
                "labels": ["MDB-1", "Total MDB", "Lighting", "Boiler", "Air"],
                "actual": [
                    emdb_projection["actual"],
                    mdb_total_actual,
                    lighting_total_energy,
                    round((boiler_direct_energy["actual"] or 0) + (boiler_indirect_energy["actual"] or 0), 3),
                    compressor_energy["actual"],
                ],
                "projected": [
                    emdb_projection["projected"],
                    mdb_total_projected,
                    lighting_projected_energy,
                    boiler_total_energy_projected,
                    compressor_energy["projected"],
                ],
            },
        },
        "water_flow_forecast": {
            "cards": water_cards,
            "contribution_chart": {
                "labels": list(wtp_sources.keys()),
                "values": [wtp_sources[source]["projected"] for source in wtp_sources],
            },
            "wastewater_chart": {
                "labels": ["Treated", "Raw Inflow"],
                "actual": [
                    wwtp_effluent["actual"],
                    wwtp_raw["actual"],
                ],
                "projected": [
                    wwtp_effluent["projected"],
                    wwtp_raw["projected"],
                ],
            },
        },
        "thermal_process_forecast": {
            "cards": thermal_cards,
            "freezer_units": freezer_units,
        },
        "ratio_efficiency_forecast": {
            "cards": ratio_cards,
            "supporting_metrics": {
                "boiler_direct_share": boiler_direct_share,
                "boiler_indirect_share": boiler_indirect_share,
                "lighting_warning_count": lighting_warning,
                "lighting_critical_count": lighting_critical,
            },
        },
        "risk_alert_forecast": {
            "items": risk_items,
            "generator_note": generator_note,
        },
    }


@app.route("/api/projection")
def projection_data():
    period = request.args.get("period")
    return jsonify(build_maintenance_projection_payload("overview", period))


@app.route("/api/projection/freezer")
def projection_freezer_data():
    period = request.args.get("period")
    return jsonify(build_maintenance_projection_payload("freezer", period))


@app.route("/api/projection/water")
def projection_water_data():
    period = request.args.get("period")
    return jsonify(build_maintenance_projection_payload("water", period))


@app.route("/api/projection/mdb")
def projection_mdb_data():
    period = request.args.get("period")
    return jsonify(build_maintenance_projection_payload("mdb", period))


@app.route("/api/projection/boiler")
def projection_boiler_data():
    period = request.args.get("period")
    return jsonify(build_maintenance_projection_payload("boiler", period))


@app.route("/api/downtime")
def downtime_data():
    period = request.args.get("period")
    month = request.args.get("month")
    return jsonify(build_downtime_payload(period, month))


@app.route("/api/maintenance/utility/summary")
def maintenance_utility_summary():
    year = request.args.get("year", type=int)
    return jsonify(build_summary_payload(year))


@app.route("/api/maintenance/overview")
def maintenance_overview():
    return jsonify(
        build_maintenance_overview_payload(
            month_value=request.args.get("month"),
            status=request.args.get("status", "all"),
            category=request.args.get("category", "all"),
            search=request.args.get("search", ""),
            sort=request.args.get("sort", "date_asc"),
            year=request.args.get("year", type=int),
            mix_month_value=request.args.get("mix_month"),
        )
    )


@app.route("/api/maintenance/utility/monthly")
def maintenance_utility_monthly():
    month = request.args.get("month")
    year = request.args.get("year", type=int)
    return jsonify(build_monthly_payload(month, year))


@app.route("/api/maintenance/utility/list")
def maintenance_utility_list():
    return jsonify(
        build_list_payload(
            month_value=request.args.get("month"),
            status=request.args.get("status", "all"),
            category=request.args.get("category", "all"),
            location=request.args.get("location", "all"),
            inspection=request.args.get("inspection", "all"),
            search=request.args.get("search", ""),
            sort=request.args.get("sort", "due_date_asc"),
            year=request.args.get("year", type=int),
            aggregate=request.args.get("aggregate", "occurrence"),
        )
    )


@app.route("/api/maintenance/utility/timeline")
def maintenance_utility_timeline():
    year = request.args.get("year", type=int)
    month = request.args.get("month")
    return jsonify(build_timeline_payload(year, month))


@app.route("/api/maintenance/utility/filters")
def maintenance_utility_filters():
    year = request.args.get("year", type=int)
    return jsonify(build_filter_payload(year))


@app.route("/api/maintenance/equipment/summary")
def maintenance_equipment_summary():
    year = request.args.get("year", type=int)
    return jsonify(build_equipment_summary_payload(year))


@app.route("/api/maintenance/equipment/monthly")
def maintenance_equipment_monthly():
    month = request.args.get("month")
    year = request.args.get("year", type=int)
    return jsonify(build_equipment_monthly_payload(month, year))


@app.route("/api/maintenance/equipment/list")
def maintenance_equipment_list():
    return jsonify(
        build_equipment_list_payload(
            month_value=request.args.get("month"),
            status=request.args.get("status", "all"),
            category=request.args.get("category", "all"),
            location=request.args.get("location", "all"),
            inspection=request.args.get("inspection", "all"),
            search=request.args.get("search", ""),
            sort=request.args.get("sort", "due_date_asc"),
            year=request.args.get("year", type=int),
            aggregate=request.args.get("aggregate", "occurrence"),
            priority=request.args.get("priority", "all"),
            critical=request.args.get("critical", "all"),
            week=request.args.get("week", "all"),
        )
    )


@app.route("/api/maintenance/equipment/timeline")
def maintenance_equipment_timeline():
    year = request.args.get("year", type=int)
    month = request.args.get("month")
    return jsonify(build_equipment_timeline_payload(year, month))


@app.route("/api/maintenance/equipment/filters")
def maintenance_equipment_filters():
    year = request.args.get("year", type=int)
    return jsonify(build_equipment_filter_payload(year))


@app.route("/api/maintenance/non_scheduled/summary")
def maintenance_non_scheduled_summary():
    year = request.args.get("year", type=int)
    return jsonify(build_non_scheduled_summary_payload(year))


@app.route("/api/maintenance/non_scheduled/monthly")
def maintenance_non_scheduled_monthly():
    month = request.args.get("month")
    year = request.args.get("year", type=int)
    return jsonify(build_non_scheduled_monthly_payload(month, year))


@app.route("/api/maintenance/non_scheduled/list")
def maintenance_non_scheduled_list():
    return jsonify(
        build_non_scheduled_list_payload(
            month_value=request.args.get("month"),
            status=request.args.get("status", "all"),
            priority=request.args.get("priority", "all"),
            area=request.args.get("area", "all"),
            search=request.args.get("search", ""),
            year=request.args.get("year", type=int),
            sort=request.args.get("sort", "due_date_asc"),
        )
    )


@app.route("/api/maintenance/non_scheduled/filters")
def maintenance_non_scheduled_filters():
    year = request.args.get("year", type=int)
    return jsonify(build_non_scheduled_filter_payload(year))


@app.route("/api/maintenance/spare_parts")
def maintenance_spare_parts():
    return jsonify(build_spare_parts_payload())


def get_page_last_synced(page_key):
    mdb_files = [
        "mdb_emdb.csv",
        "mdb6_energy.csv",
        "mdb7_energy.csv",
        "mdb8_energy.csv",
        "mdb9_energy.csv",
        "mdb10_energy.csv",
        "mdb_gen1_RT.csv",
        "mdb_gen2_RT.csv",
        "mdb_gen3_RT.csv",
        "mdb_gen4_RT.csv",
    ]
    boiler_files = [
        "boiler01_1_RT.csv",
        "boiler01_2_RT.csv",
        "boiler01_3_RT.csv",
        "boiler02_1_RT.csv",
        "boiler02_2_RT.csv",
        "boiler_gas_total.csv",
        "boiler_directsteam_meterflow_total.csv",
        "boiler_indirectsteam_meterflow.csv",
        "boiler_direct_energy.csv",
        "boiler_indirect_energy.csv",
    ]
    aircompressor_files = [
        "aircompressor_energy.csv",
        "airmeter_flow.csv",
        "air_dewpoint.csv",
    ]
    wtp_files = [
        "FIT-101-DeepWellWater_Total.csv",
        "FIT-102-SoftWaterSupply-01_Total.csv",
        "FIT-104-SoftWaterSupply-02_Total.csv",
        "FIT-103-ROWaterSupply_Total.csv",
        "FIT-105-FireWaterTank_Total.csv",
        "FIT101DeepWellWater_Flow.csv",
        "FIT102SoftWaterSupplyNo1_Flow.csv",
        "FIT104SoftWaterSupplyNo2_Flow.csv",
        "FIT103ROWaterSupply_Flow.csv",
        "FIT105FireWaterTank_Flow.csv",
        "PT101SoftWaterSupplyNo1_Pres.csv",
        "PT102ROWaterSupply_Pres.csv",
        "PT103SoftWaterSupplyNo2_Pres.csv",
        "RES101SoftWaterSupplyNo1_ResCl2.csv",
        "RES102ROWaterSupply_ResCl2.csv",
        "RES103SoftWaterSupplyNo2_ResCl2.csv",
    ]
    wwtp_files = [
        "EffluentPump_Total.csv",
        "_RawWaterWastePump-01_Total.csv",
        "_RawWasteWater_Temp.csv",
        "PMG-WWTP_Energy.csv",
        "_PM-WWTP-CONTROL-PANEL_Energy.csv",
    ]
    spiral_files = [
        "sbf_spiral1_Data.csv",
        "sbf_spiral2_Data.csv",
        "sbf_spiral3_Data.csv",
        "sbf_conveyor1.csv",
        "sbf_conveyor2.csv",
        "sbf_conveyor3.csv",
        "sbf_power_monthly_ENERGY.csv",
    ]

    page_sources = {
        "overview": [
            "mdb_emdb.csv",
            "RES102ROWaterSupply_ResCl2.csv",
            "_RawWasteWater_Temp.csv",
            "boiler_direct_energy.csv",
            "boiler_indirect_energy.csv",
            "airmeter_flow.csv",
        ],
        "mdb": mdb_files,
        "boiler": boiler_files,
        "aircompressor": aircompressor_files,
        "wtp": wtp_files,
        "wwtp": wwtp_files,
        "ro_water": [
            "FIT-103-ROWaterSupply_Total.csv",
            "FIT103ROWaterSupply_Flow.csv",
            "PT102ROWaterSupply_Pres.csv",
            "RES102ROWaterSupply_ResCl2.csv",
        ],
        "softwater1": [
            "FIT-102-SoftWaterSupply-01_Total.csv",
            "FIT102SoftWaterSupplyNo1_Flow.csv",
            "PT101SoftWaterSupplyNo1_Pres.csv",
            "RES101SoftWaterSupplyNo1_ResCl2.csv",
        ],
        "softwater2": [
            "FIT-104-SoftWaterSupply-02_Total.csv",
            "FIT104SoftWaterSupplyNo2_Flow.csv",
            "PT103SoftWaterSupplyNo2_Pres.csv",
            "RES103SoftWaterSupplyNo2_ResCl2.csv",
        ],
        "spiral_blast_freezer": spiral_files,
        "projection": mdb_files + boiler_files + aircompressor_files + wtp_files + wwtp_files + spiral_files + [
            "Resource Online Status Log_2026_02_05_10_21_49.xlsx"
        ],
        "projection_mdb": mdb_files,
        "projection_boiler": boiler_files,
        "projection_cctv": ["Resource Online Status Log_2026_02_05_10_21_49.xlsx"],
        "projection_freezer": spiral_files,
        "projection_water": wtp_files + wwtp_files,
        "cctv": ["Resource Online Status Log_2026_02_05_10_21_49.xlsx"],
    }

    if page_key in {"temperature", "temperature_history"}:
        return get_temperature_last_synced()

    if page_key == "lighting":
        lighting_payload = load_lighting_data()
        return lighting_payload.get("generatedAt") or get_source_timestamp(LIGHTING_CSV_FILENAME)

    if page_key == "maintenance":
        return max(
            [ts for ts in [get_maintenance_last_synced(), get_equipment_maintenance_last_synced()] if ts],
            default=None,
        )

    if page_key == "downtime":
        return datetime.fromtimestamp(os.path.getmtime(DOWNTIME_CACHE_OUTPUT_FILE)).isoformat() if os.path.exists(DOWNTIME_CACHE_OUTPUT_FILE) else datetime.now().isoformat()

    if page_key in {"kitchen", "hobart", "steambox", "xray", "checkweigher"}:
        return datetime.now().isoformat()

    if page_key not in page_sources:
        return None

    return get_latest_timestamp_from_files(page_sources[page_key])


@app.route("/api/page-sync/<page_key>")
def page_sync(page_key):
    return jsonify({
        "page": page_key,
        "last_synced": get_page_last_synced(page_key)
    })


@app.route("/api/overview/health")
def overview_health():
    # Helper to get the latest value from any CSV
    def get_latest(file, col_key="Value"):
        path = os.path.join(DATA_DIR, file)
        if not os.path.exists(path): return None
        try:
            df = pd.read_csv(path, skiprows=1) # Adjust skiprows based on your file
            df.columns = [c.strip().replace('\ufeff', '') for c in df.columns]
            val_col = [c for c in df.columns if any(x in c.lower() for x in ['value', col_key.lower()])]
            return float(df[val_col[0]].iloc[-1]) if val_col else None
        except: return None

    # Define thresholds and current values
    health_data = [
        {
            "id": "wtp",
            "name": "Water Treatment",
            "metric": "Residual Chlorine",
            "value": get_latest("RES102ROWaterSupply_ResCl2.csv"),
            "unit": "mg",
            "status": "NORMAL" if (get_latest("RES102ROWaterSupply_ResCl2.csv") or 0) > 0.2 else "CRITICAL",
            "link": "/WTP"
        },
        {
            "id": "mdb",
            "name": "Power Systems",
            "metric": "Main Load (EMDB-1)",
            "value": get_latest("mdb_emdb.csv"),
            "unit": "kWh",
            "status": "NORMAL" if (get_latest("mdb_emdb.csv") or 0) < 250000 else "WARNING",
            "link": "/MDB"
        },
        {
            "id": "wwtp",
            "name": "Waste Water",
            "metric": "Inflow Temp",
            "value": get_latest("_RawWasteWater_Temp.csv"),
            "unit": "°C",
            "status": "NORMAL" if (get_latest("_RawWasteWater_Temp.csv") or 0) < 35 else "WARNING",
            "link": "/WWTP"
        }
    ]
    return jsonify(health_data)


@app.route("/api/overview/health-fast")
def overview_health_fast():
    def latest_point(file_name, value_key="value"):
        records = read_csv(file_name, value_key)
        return records[-1] if records else None

    def latest_value(file_name, value_key="value"):
        point = latest_point(file_name, value_key)
        return point.get(value_key) if point else None

    def build_system(id, name, path, status, message, value):
        return {
            "id": id,
            "name": name,
            "path": path,
            "status": status,
            "message": message,
            "value": value,
        }

    systems = []

    emdb_series = load_numeric_timeseries("mdb_emdb.csv", ["Value (KWh)", "Value (kW-hr)", "Value", "kWh"])
    emdb_projection = calculate_cumulative_projection(emdb_series)
    emdb_load = emdb_projection.get("current_value")
    if emdb_load is None:
        systems.append(build_system("mdb", "Power Systems (MDB)", "/Utilities/MDB/index.html", "OFFLINE", "System Unreachable", "Check Data Source"))
    else:
        mdb_status = classify_deviation_from_baseline(
            emdb_projection.get("projected"),
            emdb_projection.get("baseline_7d"),
        )
        mdb_message = {
            "WARNING": "MDB load changed abruptly from recent baseline",
            "ATTENTION": "MDB load showing a notable shift from recent baseline",
        }.get(mdb_status, "System Operational")
        systems.append(build_system("mdb", "Power Systems (MDB)", "/Utilities/MDB/index.html", mdb_status, mdb_message, f"{emdb_load:,.0f} kWh"))

    ro_water_total = latest_value("FIT-103-ROWaterSupply_Total.csv", "m3")
    soft_water_1_total = latest_value("FIT-102-SoftWaterSupply-01_Total.csv", "m3")
    soft_water_2_total = latest_value("FIT-104-SoftWaterSupply-02_Total.csv", "m3")
    treated_water_total = sum(value or 0 for value in [ro_water_total, soft_water_1_total, soft_water_2_total])
    if ro_water_total is None and soft_water_1_total is None and soft_water_2_total is None:
        systems.append(build_system("wtp", "Water Treatment", "/Utilities/Water%20Treatment%20Plant/index.html", "OFFLINE", "System Unreachable", "Check Data Source"))
    else:
        chlorine_statuses = [
            classify_chlorine_overview(get_latest_value(load_numeric_timeseries(file_name, ["mg", "Value"])))
            for file_name in ["RES102ROWaterSupply_ResCl2.csv", "RES101SoftWaterSupplyNo1_ResCl2.csv", "RES103SoftWaterSupplyNo2_ResCl2.csv"]
        ]
        pressure_statuses = []
        for file_name in ["PT102ROWaterSupply_Pres.csv", "PT101SoftWaterSupplyNo1_Pres.csv", "PT103SoftWaterSupplyNo2_Pres.csv"]:
            pressure_series = load_numeric_timeseries(file_name, ["bar", "Value"])
            pressure_statuses.append(classify_deviation_from_baseline(get_latest_value(pressure_series), recent_value_baseline(pressure_series)))

        flow_projections = [
            calculate_cumulative_projection(load_numeric_timeseries(file_name, ["m3", "Value"]))
            for file_name in ["FIT-103-ROWaterSupply_Total.csv", "FIT-102-SoftWaterSupply-01_Total.csv", "FIT-104-SoftWaterSupply-02_Total.csv"]
        ]
        flow_projected = sum(item.get("projected") or 0 for item in flow_projections)
        flow_baseline = sum(item.get("baseline_7d") or 0 for item in flow_projections)
        flow_status = classify_low_baseline(flow_projected, flow_baseline) if flow_baseline > 0 else "NORMAL"
        wtp_status = combine_status(*(chlorine_statuses + pressure_statuses + [flow_status]))
        wtp_message = {
            "WARNING": "Water treatment KPI outside operating threshold",
            "ATTENTION": "Water treatment KPI needs monitoring",
        }.get(wtp_status, "System Operational")
        systems.append(build_system("wtp", "Water Treatment", "/Utilities/Water%20Treatment%20Plant/index.html", wtp_status, wtp_message, f"{treated_water_total:,.0f} m³"))

    raw_temp = latest_value("_RawWasteWater_Temp.csv", "value")
    effluent_pump = latest_value("EffluentPump_Total.csv", "value")
    raw_pump = latest_value("_RawWaterWastePump-01_Total.csv", "value")
    active_wwtp_pumps = (1 if (effluent_pump or 0) > 0 else 0) + (1 if (raw_pump or 0) > 0 else 0)
    active_wwtp_pumps_label = f"{active_wwtp_pumps} Active {'Pump' if active_wwtp_pumps == 1 else 'Pumps'}"
    if raw_temp is None and effluent_pump is None and raw_pump is None:
        systems.append(build_system("wwtp", "Wastewater Plant", "/Utilities/Wastewater%20Plant/index.html", "OFFLINE", "System Unreachable", "Check Data Source"))
    elif raw_temp is not None and raw_temp >= 35:
        systems.append(build_system("wwtp", "Wastewater Plant", "/Utilities/Wastewater%20Plant/index.html", "WARNING", "Wastewater inflow temperature elevated", active_wwtp_pumps_label))
    elif raw_temp is not None and raw_temp >= 30:
        systems.append(build_system("wwtp", "Wastewater Plant", "/Utilities/Wastewater%20Plant/index.html", "ATTENTION", "Wastewater inflow temperature rising", active_wwtp_pumps_label))
    elif raw_temp is not None and (effluent_pump is None or raw_pump is None):
        systems.append(build_system("wwtp", "Wastewater Plant", "/Utilities/Wastewater%20Plant/index.html", "ATTENTION", "One wastewater pump signal unavailable", active_wwtp_pumps_label))
    elif raw_temp is not None and active_wwtp_pumps == 0:
        systems.append(build_system("wwtp", "Wastewater Plant", "/Utilities/Wastewater%20Plant/index.html", "WARNING", "Wastewater pump movement not detected", active_wwtp_pumps_label))
    else:
        systems.append(build_system("wwtp", "Wastewater Plant", "/Utilities/Wastewater%20Plant/index.html", "NORMAL", "System Operational", active_wwtp_pumps_label))

    try:
        db_path = os.path.join(BASE_DIR, "temps.db")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        room_rows = [dict(row) for row in conn.execute("SELECT * FROM room_temperature").fetchall()]
        conn.close()
        room_count = len(room_rows)
        temp_statuses = []
        for row in room_rows:
            room_name = next(
                (row.get(col) for col in row.keys() if normalize_projection_key(col) in {"baseroom", "room", "roomname", "name", "area", "zonename", "zone"}),
                None,
            )
            temp_value = next(
                (
                    pd.to_numeric(row.get(col), errors="coerce")
                    for col in row.keys()
                    if any(token in normalize_projection_key(col) for token in ["temp", "temperature", "value"])
                ),
                None,
            )
            if room_name is not None and pd.notna(temp_value):
                threshold_config = find_room_threshold_config(row.get("base_room")) or find_room_threshold_config(room_name)
                temp_statuses.append(classify_temperature_value(temp_value, threshold_config))
        temp_status = combine_status(*temp_statuses)
        temp_message = {
            "WARNING": "Room temperature outside configured threshold",
            "ATTENTION": "Room temperature nearing configured threshold",
        }.get(temp_status, "System Operational")
        systems.append(build_system("temp", "Room Temperatures", "/Temperature/index.html", temp_status, temp_message, f"{room_count} Rooms Monitored"))
    except Exception:
        systems.append(build_system("temp", "Room Temperatures", "/Temperature/index.html", "OFFLINE", "System Unreachable", "Check Data Source"))

    spiral_files = [
        os.path.join(DATA_DIR, "sbf_spiral1_Data.csv"),
        os.path.join(DATA_DIR, "sbf_spiral2_Data.csv"),
        os.path.join(DATA_DIR, "sbf_spiral3_Data.csv"),
    ]
    spiral_online = sum(1 for path in spiral_files if os.path.exists(path))
    if spiral_online == 0:
        systems.append(build_system("sbf", "Spiral Blast Freezer", "/Spiral%20Blast%20Freezer/index.html", "OFFLINE", "System Unreachable", "Check Data Source"))
    else:
        freezer_statuses = []
        for path in spiral_files:
            rows = read_sbf_csv(path)
            if not rows:
                continue
            latest_row = rows[-1]
            temps = [
                pd.to_numeric(latest_row.get(key), errors="coerce")
                for key in ["tef01", "tef02"]
                if latest_row.get(key) is not None
            ]
            valid_temps = [float(value) for value in temps if pd.notna(value)]
            if not valid_temps:
                continue
            warmest_temp = max(valid_temps)
            if warmest_temp > -18:
                freezer_statuses.append("WARNING")
            elif warmest_temp > -22:
                freezer_statuses.append("ATTENTION")
            else:
                freezer_statuses.append("NORMAL")
        sbf_status = combine_status(*freezer_statuses)
        sbf_message = {
            "WARNING": "Freezer temperature above critical threshold",
            "ATTENTION": "Freezer temperature approaching threshold",
        }.get(sbf_status, "System Operational")
        systems.append(build_system("sbf", "Spiral Blast Freezer", "/Spiral%20Blast%20Freezer/index.html", sbf_status, sbf_message, f"{spiral_online} Lines Online"))

    cctv_path = os.path.join(DATA_DIR, "Resource Online Status Log_2026_02_05_10_21_49.xlsx")
    try:
        cctv_df = pd.read_excel(cctv_path)
        cctv_df.columns = cctv_df.columns.str.strip()
        total_cams = len(cctv_df)
        offline_cams = len(cctv_df[cctv_df["Current Status"].astype(str).str.lower() != "online"])
        offline_ratio = (offline_cams / total_cams) if total_cams else 0
        if offline_ratio >= 0.10:
            systems.append(build_system("cctv", "CCTV Monitoring", "/CCTV/index.html", "WARNING", f"{offline_cams} camera(s) offline", f"{total_cams - offline_cams} / {total_cams} Online"))
        elif offline_ratio >= 0.05:
            systems.append(build_system("cctv", "CCTV Monitoring", "/CCTV/index.html", "ATTENTION", f"{offline_cams} camera(s) offline", f"{total_cams - offline_cams} / {total_cams} Online"))
        elif offline_cams > 0:
            systems.append(build_system("cctv", "CCTV Monitoring", "/CCTV/index.html", "NORMAL", f"{offline_cams} camera(s) offline", f"{total_cams - offline_cams} / {total_cams} Online"))
        else:
            systems.append(build_system("cctv", "CCTV Monitoring", "/CCTV/index.html", "NORMAL", "System Operational", f"{total_cams} / {total_cams} Online"))
    except Exception:
        systems.append(build_system("cctv", "CCTV Monitoring", "/CCTV/index.html", "OFFLINE", "System Unreachable", "Check Data Source"))

    try:
        lighting_payload = load_lighting_data()
        lighting_rows = lighting_payload.get("fixtures", [])
        total_fixtures = len(lighting_rows)
        critical_fixtures = 0
        warning_fixtures = 0
        health_scores = []
        total_energy = 0.0

        for row in lighting_rows:
            notional_energy = pd.to_numeric(row.get("Notional Energy"), errors="coerce")
            health = calculate_lighting_fixture_health_pct(row.get("Lamp Life Remaining"))

            if pd.notna(notional_energy):
                total_energy += float(notional_energy)

            if health is not None:
                health_scores.append(health)
                critical_area = any(
                    normalize_projection_key(key) in {"criticalarea", "critical", "risklevel", "risk"}
                    and str(row.get(key, "")).strip().lower() in {"true", "yes", "1", "critical", "high", "high risk"}
                    for key in row.keys()
                )
                if health < 40 or (critical_area and health < 60):
                    critical_fixtures += 1
                elif health < 70:
                    warning_fixtures += 1

        average_health = round(sum(health_scores) / len(health_scores), 1) if health_scores else 0
        if total_fixtures == 0:
            systems.append(build_system("lighting", "Lighting Control", "/Lighting/index.html", "OFFLINE", "System Unreachable", "Check Data Source"))
        elif critical_fixtures > 0:
            systems.append(build_system("lighting", "Lighting Control", "/Lighting/index.html", "WARNING", f"{critical_fixtures} critical fixture(s) across {total_fixtures} monitored lights", f"{total_energy:,.0f} kWh"))
        elif warning_fixtures > 0:
            systems.append(build_system("lighting", "Lighting Control", "/Lighting/index.html", "ATTENTION", f"{warning_fixtures} fixture(s) approaching maintenance threshold", f"{average_health}% Avg Health"))
        else:
            systems.append(build_system("lighting", "Lighting Control", "/Lighting/index.html", "NORMAL", f"{total_fixtures} fixtures monitored", f"{average_health}% Avg Health"))
    except Exception:
        systems.append(build_system("lighting", "Lighting Control", "/Lighting/index.html", "OFFLINE", "System Unreachable", "Check Data Source"))

    boiler_direct_series = load_numeric_timeseries("boiler_direct_energy.csv", ["Value (kW-hr)", "Value", "kWh", "energy"])
    boiler_indirect_series = load_numeric_timeseries("boiler_indirect_energy.csv", ["Value (kW-hr)", "Value", "kWh", "energy"])
    boiler_direct_projection = calculate_cumulative_projection(boiler_direct_series)
    boiler_indirect_projection = calculate_cumulative_projection(boiler_indirect_series)
    direct_energy = boiler_direct_projection.get("current_value")
    indirect_energy = boiler_indirect_projection.get("current_value")
    if direct_energy is None and indirect_energy is None:
        systems.append(build_system("boiler", "Boiler Systems", "/Utilities/Boiler/index.html", "OFFLINE", "System Unreachable", "Check Data Source"))
    else:
        total_boiler_energy = (direct_energy or 0) + (indirect_energy or 0)
        boiler_projected = (boiler_direct_projection.get("projected") or 0) + (boiler_indirect_projection.get("projected") or 0)
        boiler_baseline = (boiler_direct_projection.get("baseline_7d") or 0) + (boiler_indirect_projection.get("baseline_7d") or 0)
        boiler_status = combine_status(
            classify_high_baseline(boiler_projected, boiler_baseline) if boiler_baseline > 0 else "NORMAL",
            classify_flatline_against_baseline(boiler_direct_series, boiler_direct_projection.get("baseline_7d")),
            classify_flatline_against_baseline(boiler_indirect_series, boiler_indirect_projection.get("baseline_7d")),
        )
        boiler_message = {
            "WARNING": "Boiler energy outside expected baseline",
            "ATTENTION": "Boiler energy needs monitoring",
        }.get(boiler_status, "System Operational")
        systems.append(build_system("boiler", "Boiler Systems", "/Utilities/Boiler/index.html", boiler_status, boiler_message, f"{total_boiler_energy:,.0f} kWh"))

    air_flow_series = load_numeric_timeseries("airmeter_flow.csv", ["Value (m³)", "Value (m3)", "Value", "flow"])
    air_flow_projection = calculate_cumulative_projection(air_flow_series)
    air_flow = air_flow_projection.get("current_value")
    if air_flow is None:
        systems.append(build_system("air", "Air Compressor", "/Utilities/Air%20Compressor/index.html", "OFFLINE", "System Unreachable", "Check Data Source"))
    else:
        air_flow_status = classify_low_baseline(air_flow_projection.get("projected"), air_flow_projection.get("baseline_7d"))
        air_flow_message = {
            "WARNING": "Air flow dropped below recent baseline",
            "ATTENTION": "Air flow below expected baseline",
        }.get(air_flow_status, "System Operational")
        systems.append(build_system("air", "Air Compressor", "/Utilities/Air%20Compressor/index.html", air_flow_status, air_flow_message, f"{air_flow:,.2f} Flow"))

    last_synced = max(
        [ts for ts in [
            get_latest_csv_timestamp("mdb_emdb.csv"),
            get_latest_csv_timestamp("RES102ROWaterSupply_ResCl2.csv"),
            get_latest_csv_timestamp("FIT-103-ROWaterSupply_Total.csv"),
            get_latest_csv_timestamp("FIT-102-SoftWaterSupply-01_Total.csv"),
            get_latest_csv_timestamp("FIT-104-SoftWaterSupply-02_Total.csv"),
            get_latest_csv_timestamp("_RawWasteWater_Temp.csv"),
            get_latest_csv_timestamp("EffluentPump_Total.csv"),
            get_latest_csv_timestamp("_RawWaterWastePump-01_Total.csv"),
            get_latest_csv_timestamp("boiler_direct_energy.csv"),
            get_latest_csv_timestamp("boiler_indirect_energy.csv"),
            get_latest_csv_timestamp("airmeter_flow.csv"),
            get_latest_csv_timestamp("Channel Runtime_Light.csv"),
            get_maintenance_last_synced(),
            get_equipment_maintenance_last_synced(),
            get_page_last_synced("downtime"),
        ] if ts],
        default=None
    )

    return jsonify({"systems": systems, "last_synced": last_synced})


# =====================================================
# PDF CLASS DEFINITION
# =====================================================
class SATS_Report(FPDF):
    def header(self):
        found_logo = None
        for loc in LOGO_LOCATIONS:
            if os.path.exists(loc):
                found_logo = loc
                break
        
        if found_logo:
            self.image(found_logo, 10, 8, 33)
            self.set_x(50) 
        else:
            self.set_x(10)

        self.set_font('helvetica', 'B', 12)
        self.set_text_color(15, 23, 42)
        self.cell(0, 10, 'STAGE 2 INDUSTRIAL SYSTEMS MASTER REPORT', 
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='L')
        
        self.set_draw_color(59, 130, 246)
        self.line(10, 22, 200, 22)
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font('helvetica', 'I', 8)
        self.set_text_color(128)
        self.cell(0, 10, f'Page {self.page_no()} | CONFIDENTIAL INDUSTRIAL DATA', 
                  new_x=XPos.RIGHT, new_y=YPos.TOP, align='C')

# =====================================================
# HELPERS
# =====================================================
def save_wtp_chart(data_list, val_key, title, ylabel, filename, color='#f59e0b'):
    """Generates a line chart for WTP metrics."""
    if not data_list:
        return None
    df = pd.DataFrame(data_list)
    df = df.tail(24)
    plt.figure(figsize=(6, 3))
    plt.plot(df['time'], df[val_key], color=color, linewidth=2, marker='o', markersize=4)
    plt.title(title, fontsize=10, fontweight='bold')
    plt.ylabel(ylabel, fontsize=8)
    plt.xticks(rotation=45, fontsize=7)
    plt.grid(True, linestyle='--', alpha=0.6)
    plt.tight_layout()
    path = os.path.join(BASE_DIR, filename)
    plt.savefig(path, dpi=150)
    plt.close()
    return path

def load_wtp_pressure_data(source):
    """Load all pressure data for a source. Returns list of {time, bar}."""
    file_map = {
        'ro':         'PT102ROWaterSupply_Pres.csv',
        'softwater1': 'PT101SoftWaterSupplyNo1_Pres.csv',
        'softwater2': 'PT103SoftWaterSupplyNo2_Pres.csv'
    }
    path = os.path.join(DATA_DIR, file_map.get(source, ''))
    if not os.path.exists(path):
        return []
    try:
        df = pd.read_csv(path)
        df.columns = [c.strip() for c in df.columns]
        df['Timestamp'] = df['Timestamp'].str.replace(' ICT', '', regex=False)
        df['dt'] = pd.to_datetime(df['Timestamp'], format='%d-%b-%y %I:%M:%S %p')
        bar_col = next((c for c in df.columns if 'bar' in c.lower() or 'pres' in c.lower()), None)
        if not bar_col:
            return []
        return [{'time': row['dt'].strftime('%d %b %H:%M'), 'bar': float(row[bar_col])} for _, row in df.iterrows()]
    except Exception as e:
        print(f"load_wtp_pressure_data error ({source}): {e}")
        return []

def load_wtp_chlorine_data(source):
    """Load all chlorine data for a source. Returns list of {time, mg}."""
    file_map = {
        'ro':         'RES102ROWaterSupply_ResCl2.csv',
        'softwater1': 'RES101SoftWaterSupplyNo1_ResCl2.csv',
        'softwater2': 'RES103SoftWaterSupplyNo2_ResCl2.csv'
    }
    path = os.path.join(DATA_DIR, file_map.get(source, ''))
    if not os.path.exists(path):
        return []
    try:
        df = pd.read_csv(path, skiprows=2)
        df.columns = [c.strip() for c in df.columns]
        df['Timestamp'] = df['Timestamp'].str.replace(' ICT', '', regex=False)
        df['dt'] = pd.to_datetime(df['Timestamp'], format='%d-%b-%y %I:%M:%S %p')
        return [{'time': row['dt'].strftime('%d %b %H:%M'), 'mg': float(row.get('Value (mg)', row.get('Value', 0)))} for _, row in df.iterrows()]
    except Exception as e:
        print(f"load_wtp_chlorine_data error ({source}): {e}")
        return []

def save_wtp_line_chart(data_list, val_key, title, ylabel, filename, color='#3b82f6'):
    """Single-source line chart showing full date range with period label."""
    if not data_list:
        return None
    labels = [p['time'] for p in data_list]
    vals   = [p[val_key] for p in data_list]
    n = len(labels)
    tick_step = max(1, n // 14)
    date_range = f"{labels[0]}   to   {labels[-1]}" if n > 1 else (labels[0] if labels else '')
    fig, ax = plt.subplots(figsize=(15, 3.8))
    ax.plot(range(n), vals, color=color, linewidth=1.8,
            marker='o' if n <= 48 else None, markersize=3)
    ax.fill_between(range(n), vals, alpha=0.08, color=color)
    ax.set_xticks(range(0, n, tick_step))
    ax.set_xticklabels([labels[i] for i in range(0, n, tick_step)],
                       rotation=40, fontsize=7, ha='right')
    ax.set_title(title, fontsize=10, fontweight='bold')
    ax.set_ylabel(ylabel, fontsize=9)
    ax.set_xlabel(f"Period: {date_range}", fontsize=8, color='#64748b')
    ax.grid(True, linestyle='--', alpha=0.4)
    if vals:
        ax.annotate(f'Latest: {vals[-1]:.2f}', xy=(n - 1, vals[-1]),
                    xytext=(-40, 8), textcoords='offset points',
                    fontsize=8, color=color, fontweight='bold')
    plt.tight_layout()
    path = os.path.join(BASE_DIR, filename)
    plt.savefig(path, dpi=150, bbox_inches='tight')
    plt.close()
    return path

def save_wtp_multi_line_chart(datasets, title, ylabel, filename):
    """
    Multi-source line chart for the WTP summary page.
    datasets: list of {label, data (list of {time, value}), val_key, color}
    """
    if not any(d['data'] for d in datasets):
        return None
    base = max(datasets, key=lambda d: len(d['data']))
    labels = [p['time'] for p in base['data']]
    n = len(labels)
    if n == 0:
        return None
    tick_step = max(1, n // 14)
    date_range = f"{labels[0]}   to   {labels[-1]}" if n > 1 else labels[0]
    fig, ax = plt.subplots(figsize=(15, 4.5))
    for d in datasets:
        if not d['data']:
            continue
        vals = [p[d['val_key']] for p in d['data']]
        ax.plot(range(len(vals)), vals, label=d['label'],
                color=d['color'], linewidth=1.8)
    ax.set_xticks(range(0, n, tick_step))
    ax.set_xticklabels([labels[i] for i in range(0, n, tick_step)],
                       rotation=40, fontsize=7, ha='right')
    ax.set_title(title, fontsize=11, fontweight='bold')
    ax.set_ylabel(ylabel, fontsize=9)
    ax.set_xlabel(f"Period: {date_range}", fontsize=8, color='#64748b')
    ax.legend(fontsize=9, loc='upper right', framealpha=0.8)
    ax.grid(True, linestyle='--', alpha=0.4)
    plt.tight_layout()
    path = os.path.join(BASE_DIR, filename)
    plt.savefig(path, dpi=150, bbox_inches='tight')
    plt.close()
    return path

def render_temperature_table(pdf, df, generated_time=None):
    # ---------- TABLE CONFIG ----------
    headers = [
        "Cold Room",
        "Expected (°C)",
        "Set Point (°C)",
        "Latest Temp (°C)",
        "Deviation (°C)",
        "Within Tolerance"
    ]

    col_widths = [48, 28, 28, 30, 26, 30]
    row_height = 7
    header_height = 8

    def draw_header():
        pdf.set_font('helvetica', 'B', 9)
        pdf.set_fill_color(226, 232, 240)  # light gray
        pdf.set_text_color(15, 23, 42)

        for h, w in zip(headers, col_widths):
            pdf.cell(w, header_height, h, border=1, align='C', fill=True)
        pdf.ln()

    def draw_timestamp_header():
        if generated_time:
            pdf.set_font('helvetica', '', 10)
            pdf.set_text_color(0, 0, 0)
            pdf.cell(0, 8, f"Temperature data as of {generated_time}", 
                     new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(2)

    # ---------- INITIAL TIMESTAMP HEADER ----------
    draw_timestamp_header()

    # ---------- INITIAL TABLE HEADER ----------
    draw_header()

    pdf.set_font('helvetica', '', 9)
    pdf.set_text_color(0)

    fill = False  # for alternating row colour

    for _, r in df.iterrows():
        # ---------- PAGE BREAK ----------
        if pdf.get_y() > 265:
            pdf.add_page()
            draw_timestamp_header()
            draw_header()
            pdf.set_font('helvetica', '', 9)

        # ---------- DATA SAFETY ----------
        room = r.get("room_name") or r.get("base_room", "N/A")

        try:
            expected = float(r.get("Requirement", 0))
            actual = float(r.get("Actual Temp", 0))
            diff = float(r.get("temp_diff", 0))
            status = str(r.get("status", "")).upper()
        except:
            expected, actual, diff, status = 0.0, 0.0, 0.0, "UNKNOWN"

        ok = "YES" if status == "OK" else "NO"

        # ---------- ROW BACKGROUND ----------
        if fill:
            pdf.set_fill_color(248, 250, 252)  # very light gray
        else:
            pdf.set_fill_color(255, 255, 255)

        # ---------- ROW CELLS ----------
        pdf.cell(col_widths[0], row_height, str(room)[:32], border=1, fill=True)
        pdf.cell(col_widths[1], row_height, f"{expected:.2f}", border=1, align='C', fill=True)
        pdf.cell(col_widths[2], row_height, f"{expected:.2f}", border=1, align='C', fill=True)
        pdf.cell(col_widths[3], row_height, f"{actual:.2f}", border=1, align='C', fill=True)
        pdf.cell(col_widths[4], row_height, f"{diff:.2f}", border=1, align='C', fill=True)

        # ---------- STATUS BADGE ----------
        if ok == "YES":
            pdf.set_text_color(22, 101, 52)
            pdf.set_fill_color(220, 252, 231)
        else:
            pdf.set_text_color(220, 38, 38)
            pdf.set_fill_color(254, 226, 226)

        pdf.cell(
            col_widths[5],
            row_height,
            ok,
            border=1,
            align='C',
            fill=True,
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT
        )

        pdf.set_text_color(0)
        fill = not fill

def get_mdb_period(file_name):
    """Return 'DD Mon YYYY – DD Mon YYYY (N days)' for an MDB CSV file."""
    path = os.path.join(DATA_DIR, file_name)
    if not os.path.exists(path):
        return "N/A"
    try:
        with open(path, mode="r", encoding="utf-8-sig", errors="ignore") as f:
            lines = f.readlines()
        header_idx = next((i for i, l in enumerate(lines) if "timestamp" in l.lower()), -1)
        if header_idx == -1:
            return "N/A"
        data_lines = [l.strip() for l in lines[header_idx + 1:] if l.strip()]
        if not data_lines:
            return "N/A"
        fmt = "%d-%b-%y %I:%M:%S %p"
        def parse_ts(line):
            raw = line.split(",")[0].replace(" ICT", "").strip()
            return datetime.strptime(raw, fmt)
        dt_first = parse_ts(data_lines[0])
        dt_last  = parse_ts(data_lines[-1])
        days = (dt_last.date() - dt_first.date()).days
        return f"{dt_first.strftime('%d %b %Y')} - {dt_last.strftime('%d %b %Y')} ({days}d)"
    except Exception:
        return "N/A"


def render_mdb_energy_table(pdf, energy_data, periods=None):
    pdf.set_font('helvetica', 'B', 12)
    pdf.cell(0, 8, "MDB Energy Distribution (Latest Reading)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)

    if periods:
        col_widths = [45, 40, 95]
        headers = ["MDB Panel", "Energy (kWh)", "Data Period"]
    else:
        col_widths = [60, 60]
        headers = ["MDB Panel", "Energy (kWh)"]

    pdf.set_font('helvetica', 'B', 10)
    for h, w in zip(headers, col_widths):
        pdf.cell(w, 8, h, border=1)
    pdf.ln()

    pdf.set_font('helvetica', '', 10)
    for panel, value in energy_data.items():
        pdf.cell(col_widths[0], 8, panel, border=1)
        pdf.cell(col_widths[1], 8, f"{value:.2f}", border=1)
        if periods:
            pdf.cell(col_widths[2], 8, periods.get(panel, "N/A"), border=1)
        pdf.ln()

    pdf.ln(4)


def render_emdb_summary(pdf, emdb_value):
    pdf.set_font('helvetica', 'B', 12)
    pdf.cell(0, 8, "Emergency MDB (EMDB-1) Summary", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)

    pdf.set_font('helvetica', '', 11)
    pdf.multi_cell(
        0, 7,
        f"The Emergency Main Distribution Board (EMDB-1) recorded a latest energy "
        f"consumption of {emdb_value:.2f} kWh. This value represents the most recent "
        f"captured reading from the emergency power line."
    )

    pdf.ln(4)


def render_generator_status_table(pdf, generators):
    pdf.set_font('helvetica', 'B', 12)
    pdf.cell(0, 8, "Generator Runtime and Status", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)

    col_widths = [50, 60, 40]
    headers = ["Generator", "Runtime (hrs)", "Status"]

    pdf.set_font('helvetica', 'B', 10)
    for h, w in zip(headers, col_widths):
        pdf.cell(w, 8, h, border=1)
    pdf.ln()

    pdf.set_font('helvetica', '', 10)
    for gen_id, data in generators.items():
        latest = data[-1]["runtime"] if len(data) else 0
        prev = data[-2]["runtime"] if len(data) > 1 else 0
        status = "RUNNING" if latest > prev and prev != 0 else "STANDBY"

        pdf.cell(col_widths[0], 8, gen_id.replace("_", "-").upper(), border=1)
        pdf.cell(col_widths[1], 8, f"{latest:.1f}", border=1)
        pdf.cell(col_widths[2], 8, status, border=1)
        pdf.ln()

    pdf.ln(4)

def collect_mdb_data():
    """
    Core MDB data loader.
    Returns Python dict ONLY (no jsonify, no request).
    """
    raw_data = {
        "energy": {
            "emdb_1_daily": read_mdb_daily_consumption("mdb_emdb.csv"),
            "emdb_1": read_csv("mdb_emdb.csv", "kwh"),
            "mdb_6":  read_csv("mdb6_energy.csv", "kwh"),
            "mdb_7":  read_csv("mdb7_energy.csv", "kwh"),
            "mdb_8":  read_csv("mdb8_energy.csv", "kwh"),
            "mdb_9":  read_csv("mdb9_energy.csv", "kwh"),
            "mdb_10": read_csv("mdb10_energy.csv", "kwh")
        },
        "generators": {
            "gen_1": read_csv("mdb_gen1_RT.csv", "runtime"),
            "gen_2": read_csv("mdb_gen2_RT.csv", "runtime"),
            "gen_3": read_csv("mdb_gen3_RT.csv", "runtime"),
            "gen_4": read_csv("mdb_gen4_RT.csv", "runtime")
        },
        "meta": {
            "last_synced": max([
                ts for ts in [
                    get_latest_csv_timestamp("mdb_emdb.csv"),
                    get_latest_csv_timestamp("mdb6_energy.csv"),
                    get_latest_csv_timestamp("mdb7_energy.csv"),
                    get_latest_csv_timestamp("mdb8_energy.csv"),
                    get_latest_csv_timestamp("mdb9_energy.csv"),
                    get_latest_csv_timestamp("mdb10_energy.csv"),
                    get_latest_csv_timestamp("mdb_gen1_RT.csv"),
                    get_latest_csv_timestamp("mdb_gen2_RT.csv"),
                    get_latest_csv_timestamp("mdb_gen3_RT.csv"),
                    get_latest_csv_timestamp("mdb_gen4_RT.csv")
                ] if ts
            ], default=None)
        }
    }

    # Clean NaN → None (JSON + PDF safe)
    def clean_nan(obj):
        if isinstance(obj, list):
            return [clean_nan(i) for i in obj]
        if isinstance(obj, dict):
            return {k: clean_nan(v) for k, v in obj.items()}
        if isinstance(obj, float) and pd.isna(obj):
            return None
        return obj

    return clean_nan(raw_data)

def render_simple_table(pdf, headers, rows, col_widths):
    pdf.set_font('helvetica', 'B', 9)
    pdf.set_fill_color(226, 232, 240)

    for h, w in zip(headers, col_widths):
        pdf.cell(w, 8, h, border=1, fill=True)
    pdf.ln()

    pdf.set_font('helvetica', '', 9)
    for row in rows:
        for val, w in zip(row, col_widths):
            pdf.cell(w, 7, str(val), border=1)
        pdf.ln()

def get_cctv_raw_data():
    file_name = "Resource Online Status Log_2026_02_05_10_21_49.xlsx"
    path = os.path.join(DATA_DIR, file_name)
    if not os.path.exists(path):
        return []
    try:
        df = pd.read_excel(path)
        df.columns = df.columns.str.strip()
        return df
    except:
        return []
    
def render_cctv_table(pdf, df):
    # Table header
    pdf.set_font('helvetica', 'B', 8)
    pdf.set_fill_color(30, 41, 59)
    pdf.set_text_color(255)

    # Simplified columns to fit on one page
    cols = [
        ("Camera Name", 60),
        ("Area", 40),
        ("Status", 25),
        ("Offline Count", 25),
        ("Latest Offline", 40)
    ]

    for header, width in cols:
        pdf.cell(width, 8, header, border=1, align='C', fill=True)
    pdf.ln()

    # Table rows
    pdf.set_text_color(0)
    pdf.set_font('helvetica', '', 7)

    for _, r in df.iterrows():
        # Page break safety
        if pdf.get_y() > 260:
            pdf.add_page()
            # Re-render header on new page
            pdf.set_font('helvetica', 'B', 8)
            pdf.set_fill_color(30, 41, 59)
            pdf.set_text_color(255)
            for header, width in cols:
                pdf.cell(width, 8, header, border=1, align='C', fill=True)
            pdf.ln()
            pdf.set_text_color(0)
            pdf.set_font('helvetica', '', 7)

        status = str(r.get("Current Status", "Unknown")).strip()
        
        # Color logic for Status
        if status.lower() == 'online':
            pdf.set_text_color(22, 101, 52) # Green
        else:
            pdf.set_text_color(220, 38, 38) # Red

        pdf.cell(60, 7, str(r.get("Name", ""))[:35], border=1)
        pdf.set_text_color(0) # Reset to black for other columns
        pdf.cell(40, 7, str(r.get("Area", ""))[:25], border=1)
        
        # Highlight status cell
        if status.lower() != 'online':
            pdf.set_fill_color(254, 226, 226)
            pdf.cell(25, 7, status, border=1, align='C', fill=True)
        else:
            pdf.cell(25, 7, status, border=1, align='C')

        pdf.cell(25, 7, str(r.get("Total Offline Times", "0")), border=1, align='C')
        pdf.cell(40, 7, str(r.get("Latest Offline Time", "--")), border=1, align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)

def get_wwtp_raw_data():
    categories = {
        'energy': [("PMG-WWTP_Energy.csv", "pmg"), ("_PM-WWTP-CONTROL-PANEL_Energy.csv", "ctrl")],
        'flow':   [("EffluentPump_Total.csv", "effluent"), ("_RawWaterWastePump-01_Total.csv", "raw")],
        'temp':   [("_RawWasteWater_Temp.csv", "temp")]
    }
    
    results = {}
    for cat, files in categories.items():
        results[cat] = {}
        for file_name, key in files:
            path = os.path.join(DATA_DIR, file_name)
            if os.path.exists(path):
                # Standard read: skip metadata
                df = pd.read_csv(path, skiprows=2)
                df.columns = [c.strip() for c in df.columns]
                
                # Identify 'Value' column
                val_col = [c for c in df.columns if 'Value' in c][0]
                
                # 🔑 THE FIX: Force numeric conversion and strip any weird characters
                # This handles the "{ }" or empty strings that are crashing your float conversion.
                df[val_col] = pd.to_numeric(df[val_col], errors='coerce').fillna(0.0)
                
                df['Timestamp'] = df['Timestamp'].astype(str).str.replace(' ICT', '', regex=False)
                df['dt'] = pd.to_datetime(df['Timestamp'], format='%d-%b-%y %I:%M:%S %p', errors='coerce')
                df = df.dropna(subset=['dt'])
                results[cat][key] = df
            else:
                results[cat][key] = pd.DataFrame()
    return results

def get_wwtp_report_data():
    """Load WWTP CSVs for PDF export using the generic read_csv helper,
    which handles both plain (no metadata) and metadata-prefixed files."""
    file_map = {
        "effluent":    "EffluentPump_Total.csv",
        "raw_pump":    "_RawWaterWastePump-01_Total.csv",
        "raw_temp":    "_RawWasteWater_Temp.csv",
        "pmg_energy":  "PMG-WWTP_Energy.csv",
        "ctrl_energy": "_PM-WWTP-CONTROL-PANEL_Energy.csv",
    }
    data_output = {}
    for key, file_name in file_map.items():
        records = read_csv(file_name, "value")
        if records:
            df = pd.DataFrame(records)
            df.rename(columns={"time": "Timestamp", "value": "Value"}, inplace=True)
            df["Value"] = pd.to_numeric(df["Value"], errors="coerce").fillna(0.0)
            df["Timestamp"] = df["Timestamp"].astype(str).str.replace(" ICT", "", regex=False)
            # read_csv strips dates to time-only strings (e.g. "6:45:00 PM")
            # Try full datetime first, fall back to time-only
            df["dt"] = pd.to_datetime(df["Timestamp"], format="%d-%b-%y %I:%M:%S %p", errors="coerce")
            if df["dt"].isna().all():
                df["dt"] = pd.to_datetime(df["Timestamp"], format="%I:%M:%S %p", errors="coerce")
            data_output[key] = df.dropna(subset=["dt"])
        else:
            data_output[key] = pd.DataFrame()
    return data_output

def safe_float(df):
    """Safely extracts the last numeric value from a DataFrame's second column."""
    if df is None or df.empty:
        return 0.0
    try:
        # Extract the last row, second column (the 'Value' column)
        val = df.iloc[-1].iloc[1]
        return float(val)
    except (ValueError, TypeError, IndexError):
        return 0.0

def format_pdf_downtime_hours(hours):
    try:
        value = float(hours or 0)
    except (TypeError, ValueError):
        return "--"

    if value <= 0:
        return "0 min"
    if value < 1:
        return f"{round(value * 60)} min"
    if value >= 24:
        days = max(1, round(value / 24))
        return f"{days} {'day' if days == 1 else 'days'}"

    whole_hours = int(value)
    minutes = round((value - whole_hours) * 60)
    if minutes == 60:
        return f"{whole_hours + 1} hr"
    if minutes > 0:
        return f"{whole_hours} hr {minutes} min"
    return f"{whole_hours} hr"

def load_downtime_overview_payload(period="ytd"):
    try:
        if os.path.exists(DOWNTIME_CACHE_OUTPUT_FILE):
            with open(DOWNTIME_CACHE_OUTPUT_FILE, "r", encoding="utf-8") as handle:
                cached = json.load(handle)
            payload = (cached.get("payloads") or {}).get(period)
            if payload:
                return payload
    except Exception as exc:
        print(f"Downtime overview cache read failed: {exc}")

    return build_downtime_payload(period)
    
def load_aircompressor_data():
    try:
        energy = read_csv("aircompressor_energy.csv", "energy")
        flow = read_csv("airmeter_flow.csv", "flow")
        dew = read_csv("air_dewpoint.csv", "dewpoint")

        if not energy or not flow or not dew:
            return None

        return {
            "energy": energy,
            "flow": flow,
            "dewpoint": dew
        }
    except Exception as e:
        print("Air Compressor Load Error:", e)
        return None

def generate_aircompressor_charts(data):
    img_paths = {}

    # Use last 24 points
    energy = data["energy"][-24:]
    flow = data["flow"][-24:]
    dew = data["dewpoint"][-24:]

    labels = [d["time"] for d in energy]
    energy_vals = [d["energy"] for d in energy]
    flow_vals = [d["flow"] for d in flow]
    dew_vals = [d["dewpoint"] for d in dew]

    tmp_dir = tempfile.gettempdir()

    step = _xtick_step(len(labels))
    tick_pos = range(0, len(labels), step)

    # --- Efficiency Chart ---
    fig, ax1 = plt.subplots(figsize=(9, 3.5))
    ax2 = ax1.twinx()
    ax1.plot(range(len(labels)), flow_vals,   color='#3b82f6', label="Flow (m³)",   linewidth=2)
    ax2.plot(range(len(labels)), energy_vals, color='#f59e0b', label="Energy (kWh)", linewidth=2)
    ax1.set_xticks(list(tick_pos))
    ax1.set_xticklabels([labels[i] for i in tick_pos], rotation=35, fontsize=7, ha='right')
    ax1.set_ylabel("Flow (m³)"); ax2.set_ylabel("Energy (kWh)")
    ax1.set_title("Air Compressor — Flow vs Energy Consumption")
    l1, n1 = ax1.get_legend_handles_labels(); l2, n2 = ax2.get_legend_handles_labels()
    ax1.legend(l1 + l2, n1 + n2, fontsize=7); ax1.grid(True, alpha=0.3); fig.tight_layout()
    eff_path = os.path.join(tmp_dir, "air_efficiency.png")
    plt.savefig(eff_path, dpi=150, bbox_inches='tight')
    plt.close()
    img_paths["efficiency"] = eff_path

    # --- Dewpoint Chart ---
    fig, ax = plt.subplots(figsize=(9, 3))
    ax.plot(range(len(labels)), dew_vals, color='#10b981', linewidth=2, label="Dewpoint (°C)")
    ax.fill_between(range(len(labels)), dew_vals, alpha=0.12, color='#10b981')
    ax.set_xticks(list(tick_pos))
    ax.set_xticklabels([labels[i] for i in tick_pos], rotation=35, fontsize=7, ha='right')
    ax.set_ylabel("Dewpoint (°C)"); ax.set_title("Compressed Air Dewpoint Trend")
    ax.legend(fontsize=7); ax.grid(True, alpha=0.3); fig.tight_layout()
    dew_path = os.path.join(tmp_dir, "air_dewpoint.png")
    plt.savefig(dew_path, dpi=150, bbox_inches='tight')
    plt.close()
    img_paths["dewpoint"] = dew_path

    return img_paths

def calculate_aircompressor_kpis(data):
    last_flow = data["flow"][-1]["flow"]
    last_energy = data["energy"][-1]["energy"]
    last_dew = data["dewpoint"][-1]["dewpoint"]

    efficiency = round(last_energy / last_flow, 3) if last_flow > 0 else 0

    return {
        "flow": last_flow,
        "energy": last_energy,
        "dewpoint": last_dew,
        "efficiency": efficiency
    }






# =====================================================
# KITCHEN EQUIPMENT APIs (SIMULATED DATA)
# =====================================================

@app.route("/api/hobart")
def api_hobart():
    now = datetime.now()
    hours = [(now.replace(hour=h, minute=0, second=0)).strftime("%I:%M %p") for h in range(6, now.hour + 1)]
    if not hours:
        hours = [now.strftime("%I:%M %p")]
    return jsonify({
        "summary": {
            "cycles_today": random.randint(40, 80),
            "water_usage_L": round(random.uniform(80, 160), 1),
            "tank_level_pct": round(random.uniform(40, 95), 1),
            "detergent_ml": round(random.uniform(100, 300), 0),
            "avg_cycle_min": round(random.uniform(3, 6), 1)
        },
        "diagnostics": {
            "unit_01": {
                "wash_arm": True,
                "rinse_pump": True,
                "dose_pump": random.random() > 0.1,
                "door_seal": random.random() > 0.05
            },
            "unit_02": {
                "wash_arm": True,
                "rinse_pump": random.random() > 0.05,
                "dose_pump": True,
                "door_seal": random.random() > 0.05
            }
        },
        "readings": [
            {
                "time": h,
                "wash_temp": round(random.uniform(60, 68), 1),
                "rinse_temp": round(random.uniform(82, 90), 1),
                "sanitizer_ppm": round(random.uniform(200, 400), 0)
            }
            for h in hours
        ],
        "hourly_cycles": [
            {"hour": h, "cycles": random.randint(3, 9)} for h in hours
        ]
    })

@app.route("/api/steambox")
def api_steambox():
    now = datetime.now()
    hours = [(now.replace(hour=h, minute=0, second=0)).strftime("%I:%M %p") for h in range(6, now.hour + 1)]
    if not hours:
        hours = [now.strftime("%I:%M %p")]
    return jsonify({
        "summary": {
            "units_today": random.randint(20, 60),
            "avg_cook_min": round(random.uniform(8, 15), 1),
            "door_opens_today": random.randint(30, 120)
        },
        "diagnostics": {
            "sb01": {
                "heating_element": True,
                "steam_generator": True,
                "pressure_valve": random.random() > 0.05,
                "door_seal": random.random() > 0.05
            },
            "sb02": {
                "heating_element": True,
                "steam_generator": random.random() > 0.05,
                "pressure_valve": True,
                "door_seal": random.random() > 0.05
            },
            "sb03": {
                "heating_element": random.random() > 0.05,
                "steam_generator": True,
                "pressure_valve": True,
                "door_seal": True
            }
        },
        "readings": [
            {
                "time": h,
                "avg_chamber_temp": round(random.uniform(95, 105), 1),
                "pressure_bar": round(random.uniform(2.0, 3.5), 2),
                "sb01_temp": round(random.uniform(95, 105), 1),
                "sb02_temp": round(random.uniform(95, 105), 1),
                "sb03_temp": round(random.uniform(95, 105), 1)
            }
            for h in hours
        ],
        "hourly_throughput": [
            {"hour": h, "units": random.randint(5, 20)} for h in hours
        ]
    })

@app.route("/api/xray")
def api_xray():
    now = datetime.now()
    hours = [(now.replace(hour=h, minute=0, second=0)).strftime("%I:%M %p") for h in range(6, now.hour + 1)]
    if not hours:
        hours = [now.strftime("%I:%M %p")]
    inspected = random.randint(1800, 3000)
    rejects = random.randint(5, 30)
    reject_rate = round((rejects / inspected) * 100, 2)
    tube_hours = random.randint(3000, 8500)
    tube_max = 10000
    return jsonify({
        "summary": {
            "inspected_today": inspected,
            "rejects_today": rejects,
            "reject_rate_pct": reject_rate,
            "uptime_pct": round(random.uniform(95, 100), 1)
        },
        "machine": {
            "sensitivity_mm": round(random.uniform(0.8, 1.5), 1),
            "tube_hours": tube_hours,
            "tube_max_hours": tube_max,
            "days_since_calibration": random.randint(1, 25)
        },
        "diagnostics": {
            "xray_tube": True,
            "conveyor_belt": True,
            "detection_algo": random.random() > 0.05,
            "reject_mech": True,
            "shielding_ok": True
        },
        "readings": [
            {"time": h, "reject_rate_pct": round(random.uniform(0.1, 1.5), 2)} for h in hours
        ],
        "hourly_throughput": [
            {"hour": h, "inspected": random.randint(150, 350), "rejected": random.randint(0, 5)} for h in hours
        ],
        "reject_log": [
            {
                "time": now.replace(hour=random.randint(6, max(6, now.hour)), minute=random.randint(0, 59)).strftime("%I:%M %p"),
                "product": random.choice(["Chicken Fillet", "Fish Cake", "Spring Roll", "Prawn Dumpling"]),
                "detection_type": random.choice(["Metal Fragment", "Bone Fragment", "Foreign Object"])
            }
            for _ in range(rejects if rejects <= 8 else 8)
        ]
    })

@app.route("/api/checkweigher")
def api_checkweigher():
    now = datetime.now()
    hours = [(now.replace(hour=h, minute=0, second=0)).strftime("%I:%M %p") for h in range(6, now.hour + 1)]
    if not hours:
        hours = [now.strftime("%I:%M %p")]
    target_g = 250.0
    tol_g = 5.0
    lower_g = target_g - tol_g
    upper_g = target_g + tol_g
    total = random.randint(1500, 2500)
    under = random.randint(5, 40)
    over = random.randint(3, 25)
    passed = total - under - over
    pass_rate = round((passed / total) * 100, 1)
    avg_weight = round(random.uniform(248, 252), 1)
    weights_sample = [random.gauss(target_g, 3) for _ in range(50)]
    mean_s = sum(weights_sample) / len(weights_sample)
    std_dev = round((sum((x - mean_s) ** 2 for x in weights_sample) / len(weights_sample)) ** 0.5, 2)
    shift_hours = max(1, now.hour - 6)
    throughput_per_min = round(total / (shift_hours * 60), 1)
    bins = []
    for low in range(235, 270, 5):
        high = low + 5
        zone = "under" if high <= lower_g else "over" if low >= upper_g else "pass"
        bins.append({"label": f"{low}-{high}g", "count": random.randint(0, 80 if zone == "pass" else 15), "zone": zone})
    products = ["Nasi Lemak", "Chicken Rice", "Mee Goreng", "Char Kway Teow", "Laksa"]
    shift_product = random.choice(products)
    return jsonify({
        "spec": {"target_g": target_g, "tolerance_g": tol_g, "lower_g": lower_g, "upper_g": upper_g},
        "summary": {
            "total_today": total,
            "under_rejects": under,
            "over_rejects": over,
            "avg_weight_g": avg_weight,
            "pass_rate_pct": pass_rate,
            "std_dev_g": std_dev,
            "throughput_per_min": throughput_per_min,
            "shift_product": shift_product
        },
        "diagnostics": {
            "cw01": {
                "status": random.choices(["running", "running", "running", "idle", "fault"], weights=[80, 80, 80, 10, 5])[0],
                "speed_mpm": round(random.uniform(28, 35), 1),
                "last_cal_days": random.randint(1, 14),
                "items_checked": total // 2
            },
            "cw02": {
                "status": random.choices(["running", "running", "running", "idle", "fault"], weights=[80, 80, 80, 10, 5])[0],
                "speed_mpm": round(random.uniform(28, 35), 1),
                "last_cal_days": random.randint(1, 14),
                "items_checked": total - total // 2
            }
        },
        "distribution": bins,
        "readings": [
            {"time": h, "pass_rate_pct": round(random.uniform(96, 99.5), 1), "avg_weight_g": round(random.gauss(avg_weight, 1.5), 1)} for h in hours
        ],
        "recent_log": [
            {
                "time": now.replace(hour=random.randint(6, max(6, now.hour)), minute=random.randint(0, 59)).strftime("%I:%M %p"),
                "product": shift_product,
                "weight_g": round(random.gauss(target_g, 3), 1)
            }
            for _ in range(20)
        ]
    })


# =====================================================
# KITCHEN EQUIPMENT SUMMARY
# =====================================================
@app.route("/api/kitchen")
def api_kitchen():
    equipment = [
        {"id": "hobart",      "name": "Hobart Sanitizer"},
        {"id": "steambox",    "name": "Steambox"},
        {"id": "xray",        "name": "X-Ray Inspection"},
        {"id": "checkweigher","name": "Checkweigher"},
    ]
    results = []
    for eq in equipment:
        try:
            with app.test_request_context():
                fn_map = {
                    "hobart": api_hobart,
                    "steambox": api_steambox,
                    "xray": api_xray,
                    "checkweigher": api_checkweigher,
                }
                resp = fn_map[eq["id"]]()
                data = resp.get_json()
                online = True
        except Exception:
            data = None
            online = False
        results.append({"id": eq["id"], "name": eq["name"], "online": online})
    online_count = sum(1 for r in results if r["online"])
    return jsonify({"total": len(results), "online": online_count, "equipment": results})


# =====================================================
# PDF CHART HELPERS
# =====================================================

def _save_chart(fig, filename):
    path = os.path.join(tempfile.gettempdir(), filename)
    fig.savefig(path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    return path

def _xtick_step(n, max_ticks=8):
    return max(1, n // max_ticks)

def generate_sbf_tef_chart(sbf_dict):
    try:
        fig, ax = plt.subplots(figsize=(9, 3.5))
        colors = ['#3b82f6', '#ef4444', '#f59e0b']
        ref_times = []
        for (name, records), color in zip(sbf_dict.items(), colors):
            tail = records[-100:]
            times = [str(r.get('energy_time') or r.get('time') or '') for r in tail]
            vals  = [float(r['tef01']) if r.get('tef01') is not None else None for r in tail]
            if any(v is not None for v in vals):
                ax.plot(range(len(vals)), vals, label=name, color=color, linewidth=1.5)
            if len(times) > len(ref_times):
                ref_times = times
        if ref_times:
            step = _xtick_step(len(ref_times))
            ax.set_xticks(range(0, len(ref_times), step))
            ax.set_xticklabels([ref_times[i] for i in range(0, len(ref_times), step)],
                                rotation=35, fontsize=7, ha='right')
        ax.set_ylabel("Temperature (°C)")
        ax.set_title("Freezer Temperature Performance Trend (TEF01)")
        ax.legend(fontsize=8); ax.grid(True, alpha=0.3); fig.tight_layout()
        return _save_chart(fig, "tmp_sbf_tef.png")
    except Exception as e:
        print(f"SBF TEF chart error: {e}"); plt.close(); return None

def generate_boiler_runtime_chart(boiler_data):
    try:
        datasets = [
            ("B1 Stage 1", boiler_data["boiler_01"]["stage_1_runtime"], "#10b981"),
            ("B1 Stage 2", boiler_data["boiler_01"]["stage_2_runtime"], "#34d399"),
            ("B1 Stage 3", boiler_data["boiler_01"]["stage_3_runtime"], "#6ee7b7"),
            ("B2 Stage 1", boiler_data["boiler_02"]["stage_1_runtime"], "#3b82f6"),
            ("B2 Stage 2", boiler_data["boiler_02"]["stage_2_runtime"], "#60a5fa"),
        ]
        fig, ax = plt.subplots(figsize=(9, 3.5))
        times = []
        for label, records, color in datasets:
            tail = records[-50:]
            times = [str(r.get('time', '')) for r in tail]
            vals  = [r.get('runtime') for r in tail]
            if any(v is not None for v in vals):
                ax.plot(range(len(vals)), vals, label=label, color=color, linewidth=1.5)
        if times:
            step = _xtick_step(len(times))
            ax.set_xticks(range(0, len(times), step))
            ax.set_xticklabels([times[i] for i in range(0, len(times), step)], rotation=30, fontsize=7)
        ax.set_ylabel("Hours"); ax.set_title("Boiler Runtime by Stage")
        ax.legend(fontsize=7); ax.grid(True, alpha=0.3); fig.tight_layout()
        return _save_chart(fig, "tmp_boiler_runtime.png")
    except Exception as e:
        print(f"Boiler runtime chart error: {e}"); plt.close(); return None

def generate_boiler_consumption_chart(boiler_data):
    try:
        gas_rec = boiler_data["consumption"]["gas_total_kg"][-50:]
        d_rec   = boiler_data["consumption"]["direct_steam_kg"][-50:]
        i_rec   = boiler_data["consumption"]["indirect_steam_kg"][-50:]
        times   = [str(r.get('time', '')) for r in gas_rec]
        gas_v   = [r.get('gas') for r in gas_rec]
        steam_v = [(d.get('steam') or 0) + (i.get('steam') or 0) for d, i in zip(d_rec, i_rec)]
        fig, ax1 = plt.subplots(figsize=(9, 3.5))
        ax2 = ax1.twinx()
        ax1.plot(range(len(times)), gas_v,   color='#f59e0b', label='Gas (kg)',   linewidth=1.5)
        ax2.plot(range(len(times)), steam_v, color='#6366f1', label='Steam (kg)', linewidth=1.5)
        if times:
            step = _xtick_step(len(times))
            ax1.set_xticks(range(0, len(times), step))
            ax1.set_xticklabels([times[i] for i in range(0, len(times), step)], rotation=30, fontsize=7)
        ax1.set_ylabel("Gas (kg)"); ax2.set_ylabel("Steam (kg)")
        ax1.set_title("Boiler Gas & Steam Consumption")
        l1, n1 = ax1.get_legend_handles_labels(); l2, n2 = ax2.get_legend_handles_labels()
        ax1.legend(l1+l2, n1+n2, fontsize=7); ax1.grid(True, alpha=0.3); fig.tight_layout()
        return _save_chart(fig, "tmp_boiler_consumption.png")
    except Exception as e:
        print(f"Boiler consumption chart error: {e}"); plt.close(); return None

def generate_hobart_charts(data):
    paths = {}
    readings = data.get("readings", [])
    hourly   = data.get("hourly_cycles", [])
    try:
        times = [r["time"] for r in readings]
        fig, ax = plt.subplots(figsize=(9, 3))
        ax.plot(times, [r["wash_temp"]  for r in readings], color='#3b82f6', label='Wash Temp (°C)',  linewidth=1.5)
        ax.plot(times, [r["rinse_temp"] for r in readings], color='#10b981', label='Rinse Temp (°C)', linewidth=1.5)
        ax.axhline(60, color='#3b82f6', linestyle='--', linewidth=0.8, alpha=0.6, label='Wash Target (60°C)')
        ax.axhline(82, color='#10b981', linestyle='--', linewidth=0.8, alpha=0.6, label='Rinse Target (82°C)')
        step = _xtick_step(len(times))
        ax.set_xticks(range(0, len(times), step))
        ax.set_xticklabels([times[i] for i in range(0, len(times), step)], rotation=30, fontsize=7)
        ax.set_ylabel("Temperature (°C)"); ax.set_ylim(40, None)
        ax.set_title("Hobart Wash & Rinse Temperature Trend")
        ax.legend(fontsize=7); ax.grid(True, alpha=0.3); fig.tight_layout()
        paths["temp"] = _save_chart(fig, "tmp_hobart_temp.png")
    except Exception as e:
        print(f"Hobart temp chart error: {e}"); plt.close()
    try:
        hrs  = [r["hour"] for r in hourly]
        cycs = [r["cycles"] for r in hourly]
        fig, ax = plt.subplots(figsize=(9, 2.5))
        ax.bar(range(len(hrs)), cycs, color='#8b5cf6')
        ax.set_xticks(range(len(hrs))); ax.set_xticklabels(hrs, rotation=30, fontsize=7)
        ax.set_ylabel("Cycles"); ax.set_title("Hobart Hourly Cycles")
        ax.grid(True, alpha=0.3, axis='y'); fig.tight_layout()
        paths["cycles"] = _save_chart(fig, "tmp_hobart_cycles.png")
    except Exception as e:
        print(f"Hobart cycles chart error: {e}"); plt.close()
    return paths

def generate_steambox_charts(data):
    paths = {}
    readings = data.get("readings", [])
    hourly   = data.get("hourly_throughput", [])
    try:
        times = [r["time"] for r in readings]
        fig, ax = plt.subplots(figsize=(9, 3))
        for key, label, color in [("sb01_temp","SB-01","#3b82f6"),("sb02_temp","SB-02","#10b981"),("sb03_temp","SB-03","#8b5cf6")]:
            ax.plot(times, [r.get(key) for r in readings], label=label, color=color, linewidth=1.5)
        ax.axhline(95, color='#ef4444', linestyle='--', linewidth=0.8, label='Min Target (95°C)')
        step = _xtick_step(len(times))
        ax.set_xticks(range(0, len(times), step))
        ax.set_xticklabels([times[i] for i in range(0, len(times), step)], rotation=30, fontsize=7)
        ax.set_ylabel("Temp (°C)"); ax.set_ylim(80, None)
        ax.set_title("Steambox Chamber Temperature Profile")
        ax.legend(fontsize=7); ax.grid(True, alpha=0.3); fig.tight_layout()
        paths["temp"] = _save_chart(fig, "tmp_steambox_temp.png")
    except Exception as e:
        print(f"Steambox temp chart error: {e}"); plt.close()
    try:
        times = [r["time"] for r in readings]
        pres  = [r.get("pressure_bar") for r in readings]
        fig, ax = plt.subplots(figsize=(9, 2.5))
        ax.plot(times, pres, color='#f59e0b', linewidth=1.5, label='Steam Pressure (bar)')
        ax.axhline(3.5, color='#ef4444', linestyle='--', linewidth=0.8, label='Max Safe (3.5)')
        ax.axhline(2.0, color='#94a3b8', linestyle='--', linewidth=0.8, label='Min Oper. (2.0)')
        step = _xtick_step(len(times))
        ax.set_xticks(range(0, len(times), step))
        ax.set_xticklabels([times[i] for i in range(0, len(times), step)], rotation=30, fontsize=7)
        ax.set_ylabel("Pressure (bar)"); ax.set_ylim(0, 5)
        ax.set_title("Steambox Pressure Trend")
        ax.legend(fontsize=7); ax.grid(True, alpha=0.3); fig.tight_layout()
        paths["pressure"] = _save_chart(fig, "tmp_steambox_pressure.png")
    except Exception as e:
        print(f"Steambox pressure chart error: {e}"); plt.close()
    try:
        hrs   = [r["hour"] for r in hourly]
        units = [r["units"] for r in hourly]
        fig, ax = plt.subplots(figsize=(9, 2.5))
        ax.bar(range(len(hrs)), units, color='#10b981')
        ax.set_xticks(range(len(hrs))); ax.set_xticklabels(hrs, rotation=30, fontsize=7)
        ax.set_ylabel("Trays"); ax.set_title("Steambox Hourly Throughput")
        ax.grid(True, alpha=0.3, axis='y'); fig.tight_layout()
        paths["throughput"] = _save_chart(fig, "tmp_steambox_throughput.png")
    except Exception as e:
        print(f"Steambox throughput chart error: {e}"); plt.close()
    return paths

def generate_xray_charts(data):
    paths = {}
    hourly   = data.get("hourly_throughput", [])
    readings = data.get("readings", [])
    try:
        hrs       = [r["hour"] for r in hourly]
        inspected = [r["inspected"] for r in hourly]
        rejected  = [r["rejected"]  for r in hourly]
        fig, ax1 = plt.subplots(figsize=(9, 3))
        ax2 = ax1.twinx()
        ax1.bar(range(len(hrs)), inspected, color='#2563eb', alpha=0.7, label='Inspected')
        ax2.plot(range(len(hrs)), rejected, color='#ef4444', linewidth=1.5, marker='o', markersize=3, label='Rejected')
        ax1.set_xticks(range(len(hrs))); ax1.set_xticklabels(hrs, rotation=30, fontsize=7)
        ax1.set_ylabel("Inspected Packs"); ax2.set_ylabel("Rejects")
        ax1.set_title("X-Ray Hourly Throughput & Rejects")
        l1,n1 = ax1.get_legend_handles_labels(); l2,n2 = ax2.get_legend_handles_labels()
        ax1.legend(l1+l2, n1+n2, fontsize=7); ax1.grid(True, alpha=0.3, axis='y'); fig.tight_layout()
        paths["throughput"] = _save_chart(fig, "tmp_xray_throughput.png")
    except Exception as e:
        print(f"X-Ray throughput chart error: {e}"); plt.close()
    try:
        times = [r["time"] for r in readings]
        rates = [r["reject_rate_pct"] for r in readings]
        fig, ax = plt.subplots(figsize=(9, 2.5))
        ax.plot(times, rates, color='#ef4444', linewidth=1.5, label='Reject Rate (%)')
        step = _xtick_step(len(times))
        ax.set_xticks(range(0, len(times), step))
        ax.set_xticklabels([times[i] for i in range(0, len(times), step)], rotation=30, fontsize=7)
        ax.set_ylabel("Reject Rate (%)"); ax.set_title("X-Ray Reject Rate Trend")
        ax.legend(fontsize=7); ax.grid(True, alpha=0.3); fig.tight_layout()
        paths["reject_rate"] = _save_chart(fig, "tmp_xray_rejectrate.png")
    except Exception as e:
        print(f"X-Ray reject rate chart error: {e}"); plt.close()
    return paths

def generate_checkweigher_charts(data):
    paths = {}
    dist     = data.get("distribution", [])
    readings = data.get("readings", [])
    try:
        from matplotlib.patches import Patch
        labels     = [d["label"] for d in dist]
        counts     = [d["count"] for d in dist]
        color_map  = {"under": "#ef4444", "over": "#f59e0b", "pass": "#10b981"}
        bar_colors = [color_map.get(d.get("zone", "pass"), "#10b981") for d in dist]
        fig, ax = plt.subplots(figsize=(9, 3))
        ax.bar(range(len(labels)), counts, color=bar_colors)
        ax.set_xticks(range(len(labels))); ax.set_xticklabels(labels, rotation=45, fontsize=7)
        ax.set_ylabel("Count"); ax.set_title("Checkweigher Weight Distribution")
        legend_els = [Patch(color='#ef4444', label='Under'), Patch(color='#10b981', label='Pass'), Patch(color='#f59e0b', label='Over')]
        ax.legend(handles=legend_els, fontsize=7); ax.grid(True, alpha=0.3, axis='y'); fig.tight_layout()
        paths["distribution"] = _save_chart(fig, "tmp_cw_dist.png")
    except Exception as e:
        print(f"Checkweigher dist chart error: {e}"); plt.close()
    try:
        times = [r["time"] for r in readings]
        rates = [r["pass_rate_pct"] for r in readings]
        fig, ax = plt.subplots(figsize=(9, 2.5))
        ax.plot(times, rates, color='#8b5cf6', linewidth=1.5, label='Pass Rate (%)')
        ax.axhline(97, color='#ef4444', linestyle='--', linewidth=0.8, label='Min Target (97%)')
        step = _xtick_step(len(times))
        ax.set_xticks(range(0, len(times), step))
        ax.set_xticklabels([times[i] for i in range(0, len(times), step)], rotation=30, fontsize=7)
        ax.set_ylabel("Pass Rate (%)"); ax.set_ylim(90, 100)
        ax.set_title("Checkweigher Pass Rate Trend")
        ax.legend(fontsize=7); ax.grid(True, alpha=0.3); fig.tight_layout()
        paths["pass_rate"] = _save_chart(fig, "tmp_cw_passrate.png")
    except Exception as e:
        print(f"Checkweigher pass rate chart error: {e}"); plt.close()
    return paths


# ─── MDB Charts ───────────────────────────────────────────────────────────────
def generate_mdb_charts(mdb_data):
    paths = {}
    energy = mdb_data.get("energy", {})
    generators = mdb_data.get("generators", {})

    # 1. Bar chart — latest kWh per MDB panel + EMDB-1
    try:
        panel_keys   = ["emdb_1", "mdb_6", "mdb_7", "mdb_8", "mdb_9", "mdb_10"]
        panel_labels = ["EMDB-1", "MDB-6", "MDB-7", "MDB-8", "MDB-9", "MDB-10"]
        panel_colors = ["#f59e0b", "#3b82f6", "#6366f1", "#10b981", "#ef4444", "#8b5cf6"]
        kwh_vals = []
        for key in panel_keys:
            readings = energy.get(key, [])
            val = readings[-1].get("kwh") if readings else 0
            kwh_vals.append(val if val is not None else 0)

        fig, ax = plt.subplots(figsize=(9, 3.5))
        bars = ax.bar(panel_labels, kwh_vals, color=panel_colors, edgecolor='white', linewidth=0.5)
        for bar, val in zip(bars, kwh_vals):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + max(kwh_vals) * 0.01,
                    f"{val:,.0f}", ha='center', va='bottom', fontsize=8, fontweight='bold')
        ax.set_ylabel("Energy (kWh)")
        ax.set_title("MDB Energy Distribution — Latest Reading per Panel")
        ax.grid(True, alpha=0.3, axis='y')
        fig.tight_layout()
        paths["energy_bar"] = _save_chart(fig, "tmp_mdb_energy_bar.png")
    except Exception as e:
        print(f"MDB energy bar chart error: {e}"); plt.close()

    # 2. Line chart — EMDB-1 trend (last 50 readings)
    try:
        emdb_records = energy.get("emdb_1", [])[-50:]
        if emdb_records:
            times = [str(r.get("time", "")) for r in emdb_records]
            vals  = [r.get("kwh") for r in emdb_records]
            fig, ax = plt.subplots(figsize=(9, 3))
            ax.plot(range(len(vals)), vals, color="#f59e0b", linewidth=2, label="EMDB-1 (kWh)")
            ax.fill_between(range(len(vals)), vals, alpha=0.15, color="#f59e0b")
            step = _xtick_step(len(times))
            ax.set_xticks(range(0, len(times), step))
            ax.set_xticklabels([times[i] for i in range(0, len(times), step)], rotation=30, fontsize=7)
            ax.set_ylabel("kWh"); ax.set_title("EMDB-1 Consumption Trend")
            ax.legend(fontsize=8); ax.grid(True, alpha=0.3); fig.tight_layout()
            paths["emdb_trend"] = _save_chart(fig, "tmp_mdb_emdb_trend.png")
    except Exception as e:
        print(f"MDB EMDB trend chart error: {e}"); plt.close()

    # 3. Bar chart — Generator total runtime hours
    try:
        gen_labels, gen_vals, gen_colors = [], [], ['#10b981', '#3b82f6', '#f59e0b', '#6366f1']
        for gid in ["gen_1", "gen_2", "gen_3", "gen_4"]:
            records = generators.get(gid, [])
            total = sum(r.get("runtime") or 0 for r in records)
            gen_labels.append(gid.replace("_", " ").upper())
            gen_vals.append(total)
        fig, ax = plt.subplots(figsize=(9, 3))
        bars = ax.bar(gen_labels, gen_vals, color=gen_colors[:len(gen_labels)], edgecolor='white', linewidth=0.5)
        for bar, val in zip(bars, gen_vals):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + max(gen_vals, default=1) * 0.01,
                    f"{val:.1f} h", ha='center', va='bottom', fontsize=8, fontweight='bold')
        ax.set_ylabel("Total Runtime (hrs)")
        ax.set_title("Generator Cumulative Runtime")
        ax.grid(True, alpha=0.3, axis='y'); fig.tight_layout()
        paths["gen_runtime"] = _save_chart(fig, "tmp_mdb_gen_runtime.png")
    except Exception as e:
        print(f"MDB generator chart error: {e}"); plt.close()

    return paths


# ─── Downtime mock data (matches frontend JS) ──────────────────────────────────
def generate_downtime_data():
    """Replicates the frontend mock downtime dataset for PDF reporting."""
    from datetime import datetime, timedelta
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    MINUTES_IN_DAY = 24 * 60

    def ev(sh, sm, dur):
        s = today + timedelta(hours=sh, minutes=sm)
        return {"start": s, "end": s + timedelta(minutes=dur), "dur": dur}

    equipment_raw = [
        {"name": "CCTV C.16",           "cat": "CCTV",       "events": [ev(1,15,12),ev(4,30,8),ev(7,45,20),ev(11,0,15),ev(14,20,9),ev(18,5,11)], "rec": [5,4,7,6,4,6]},
        {"name": "CCTV C.08",           "cat": "CCTV",       "events": [ev(3,10,10),ev(9,45,25),ev(16,30,8)],                                      "rec": [6,12,5]},
        {"name": "Spiral Blast Freezer","cat": "Freezer",    "events": [ev(2,0,45),ev(13,30,30)],                                                   "rec": [20,18]},
        {"name": "Boiler 01",           "cat": "Boiler",     "events": [ev(6,15,25)],                                                               "rec": [15]},
        {"name": "Boiler 02",           "cat": "Boiler",     "events": [],                                                                          "rec": []},
        {"name": "Air Compressor",      "cat": "Utilities",  "events": [ev(8,0,15),ev(17,45,20)],                                                   "rec": [10,12]},
        {"name": "MDB Generator",       "cat": "MDB",        "events": [ev(5,30,10)],                                                               "rec": [8]},
        {"name": "Wastewater Pump",     "cat": "Wastewater", "events": [ev(10,0,35),ev(19,15,20)],                                                  "rec": [18,12]},
        {"name": "Hobart Dishwasher",   "cat": "Kitchen",    "events": [ev(7,0,10),ev(12,30,8)],                                                    "rec": [5,4]},
        {"name": "X-Ray Inspector",     "cat": "Kitchen",    "events": [ev(9,15,5)],                                                                "rec": [3]},
    ]

    results = []
    for eq in equipment_raw:
        total_down = sum(e["dur"] for e in eq["events"])
        n_events   = len(eq["events"])
        uptime_pct = max(0, (MINUTES_IN_DAY - total_down) / MINUTES_IN_DAY * 100)
        avg_dur    = total_down / n_events if n_events else 0
        avg_rec    = sum(eq["rec"]) / len(eq["rec"]) if eq["rec"] else 0
        mtbf       = (MINUTES_IN_DAY - total_down) / n_events if n_events else MINUTES_IN_DAY
        status     = ("CRITICAL" if n_events >= 4 or total_down >= 180
                      else "WARNING" if total_down >= 60
                      else "OK")
        results.append({
            "name": eq["name"], "cat": eq["cat"],
            "events": n_events, "total_down": total_down,
            "avg_dur": avg_dur, "avg_rec": avg_rec,
            "uptime_pct": uptime_pct, "mtbf": mtbf, "status": status,
        })
    return results


def generate_downtime_reliability_chart(dt_data):
    """Horizontal bar chart of system reliability %."""
    try:
        names  = [d["name"] for d in dt_data]
        uptimes = [d["uptime_pct"] for d in dt_data]
        colors = ["#10b981" if u >= 90 else "#f59e0b" if u >= 80 else "#ef4444" for u in uptimes]
        fig, ax = plt.subplots(figsize=(9, max(3, len(names) * 0.45)))
        bars = ax.barh(range(len(names)), uptimes, color=colors, edgecolor='white', linewidth=0.4)
        for bar, val in zip(bars, uptimes):
            ax.text(min(val + 0.3, 99.5), bar.get_y() + bar.get_height() / 2,
                    f"{val:.1f}%", va='center', ha='left', fontsize=8, fontweight='bold')
        ax.set_yticks(range(len(names))); ax.set_yticklabels(names, fontsize=8)
        ax.set_xlim(0, 105); ax.axvline(90, color='#f59e0b', linestyle='--', linewidth=0.8, label='90% threshold')
        ax.set_xlabel("Uptime (%)"); ax.set_title("System Reliability Scores")
        ax.legend(fontsize=7); ax.grid(True, alpha=0.3, axis='x'); fig.tight_layout()
        return _save_chart(fig, "tmp_downtime_reliability.png")
    except Exception as e:
        print(f"Downtime reliability chart error: {e}"); plt.close(); return None


# =====================================================
# MASTER EXPORT ROUTE
# =====================================================
@app.route("/api/export/report")
def export_report():
    report_signature = build_pdf_report_signature()
    cached_report = get_cached_pdf_report(report_signature)
    if cached_report is not None:
        return make_pdf_report_response(cached_report, "HIT")

    temp_files = []
    generated_time = datetime.now().strftime('%d %b %Y, %I:%M %p')

    try:
        pdf = SATS_Report()
        pdf.set_auto_page_break(auto=True, margin=20)

        # 1. Initialize Links
        lnk_mdb     = pdf.add_link()
        lnk_tmp     = pdf.add_link()
        lnk_util    = pdf.add_link()
        lnk_cctv    = pdf.add_link()
        lnk_wwtp    = pdf.add_link()
        lnk_ac      = pdf.add_link()
        lnk_sbf     = pdf.add_link()
        lnk_boiler  = pdf.add_link()
        lnk_kitchen = pdf.add_link()
        lnk_downtime = pdf.add_link()

        pdf.set_link(lnk_mdb,     page=1)
        pdf.set_link(lnk_tmp,     page=1)
        pdf.set_link(lnk_util,    page=1)
        pdf.set_link(lnk_cctv,    page=1)
        pdf.set_link(lnk_wwtp,    page=1)
        pdf.set_link(lnk_ac,      page=1)
        pdf.set_link(lnk_sbf,     page=1)
        pdf.set_link(lnk_boiler,  page=1)
        pdf.set_link(lnk_kitchen, page=1)
        pdf.set_link(lnk_downtime, page=1)

        # --- PAGE 1: COVER ---
        pdf.add_page()
        pdf.ln(80)
        pdf.set_font('helvetica', 'B', 32)
        pdf.cell(0, 20, "SFST STAGE 2", align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.cell(0, 20, "SYSTEMS MASTER REPORT", align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(10)
        pdf.set_font('helvetica', '', 14)
        pdf.cell(
            0, 10,
            f"Generated: {generated_time}",
            align='C',
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT
        )

        # --- PAGE 2: MASTER HEALTH OVERVIEW ---
        pdf.add_page()
        pdf.set_font('helvetica', 'B', 20)
        pdf.cell(0, 15, "Master System Status Overview", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font('helvetica', '', 10)
        pdf.cell(
            0, 5,
            "Click any system name to jump to its deep-dive section.",
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT
        )
        pdf.ln(8)

        pdf.set_font('helvetica', 'B', 10)
        pdf.set_fill_color(30, 41, 59)
        pdf.set_text_color(255)
        pdf.cell(70, 12, " Industrial System", 1, fill=True)
        pdf.cell(40, 12, "Status", 1, align='C', fill=True)
        pdf.cell(80, 12, "Key Metric / Observation", 1, align='C', fill=True,
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(0)

        def add_row(name, link, status, metric):
            pdf.set_font('helvetica', '', 10)
            pdf.set_text_color(37, 99, 235)
            pdf.cell(70, 12, f" {name}", 1, link=link)
            pdf.set_text_color(0)

            if status == "ATTENTION":
                pdf.set_fill_color(254, 226, 226); pdf.set_text_color(220, 38, 38)
            elif status == "WARNING":
                pdf.set_fill_color(255, 247, 237); pdf.set_text_color(194, 65, 12)
            else:
                pdf.set_fill_color(240, 253, 244); pdf.set_text_color(22, 101, 52)

            pdf.cell(40, 12, status, 1, align='C', fill=True)
            pdf.set_text_color(0)
            pdf.cell(80, 12, f" {metric}", 1,
                     new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # --- Temperature ---
        try:
            conn = sqlite3.connect(os.path.join(BASE_DIR, "temps.db"))
            df_temp = pd.read_sql("SELECT status FROM room_temperature", conn)
            conn.close()
            total_out = int((df_temp["status"] == "CRITICAL").sum())
            add_row("Cold Chain (Temp)", lnk_tmp,
                    "ATTENTION" if total_out > 0 else "NORMAL",
                    f"{total_out} Alarms Found")
        except:
            add_row("Cold Chain (Temp)", lnk_tmp, "OFFLINE", "Data Error")

        # --- MDB (live) ---
        try:
            mdb_live = collect_mdb_data()
            emdb_latest = mdb_live["energy"].get("emdb_1", [{}])[-1].get("kwh", 0)
            add_row("Power Systems (MDB)", lnk_mdb, "NORMAL", f"{emdb_latest:,.0f} kWh (EMDB-1)")
        except:
            add_row("Power Systems (MDB)", lnk_mdb, "OFFLINE", "Data Error")

        # --- WTP (live) ---
        try:
            wtp_live = get_wtp_raw_data()
            flow_totals = wtp_live.get("flow_totals", {})
            ro_total = flow_totals.get("ro_water", [{}])[-1].get("m3", 0) if flow_totals.get("ro_water") else 0
            soft1_total = flow_totals.get("soft_water_1", [{}])[-1].get("m3", 0) if flow_totals.get("soft_water_1") else 0
            soft2_total = flow_totals.get("soft_water_2", [{}])[-1].get("m3", 0) if flow_totals.get("soft_water_2") else 0
            treated_total = ro_total + soft1_total + soft2_total
            add_row("Water Treatment (WTP)", lnk_util, "NORMAL", f"{treated_total:,.0f} m3 Treated Water")
        except:
            add_row("Water Treatment (WTP)", lnk_util, "OFFLINE", "Data Error")

        # --- WWTP (live) ---
        try:
            wwtp_live = get_wwtp_report_data()
            temp_val = safe_float(wwtp_live.get('raw_temp', pd.DataFrame()))
            effluent_latest = safe_float(wwtp_live.get('effluent', pd.DataFrame()))
            raw_latest = safe_float(wwtp_live.get('raw_pump', pd.DataFrame()))
            active_pumps = sum(1 for value in [effluent_latest, raw_latest] if value > 0)
            wwtp_status = "WARNING" if temp_val >= 35 else "NORMAL"
            add_row("Wastewater (WWTP)", lnk_wwtp, wwtp_status, f"{active_pumps} Active {'Pump' if active_pumps == 1 else 'Pumps'}")
        except:
            add_row("Wastewater (WWTP)", lnk_wwtp, "OFFLINE", "Data Error")

        # --- Downtime (live) ---
        try:
            downtime_payload = load_downtime_overview_payload("ytd")
            downtime_summary = downtime_payload.get("summary") or {}
            downtime_hours = downtime_summary.get("total_hours")
            downtime_events = downtime_summary.get("event_count", 0)
            add_row(
                "Downtime",
                lnk_downtime,
                "NORMAL",
                f"{format_pdf_downtime_hours(downtime_hours)} | {downtime_events} Events Year-To-Date"
            )
        except:
            add_row("Downtime", lnk_downtime, "OFFLINE", "Data Error")

        # --- SBF (live) ---
        try:
            sbf_live = read_sbf_csv(os.path.join(DATA_DIR, "sbf_spiral1_Data.csv"))
            if sbf_live:
                latest = sbf_live[-1]
                tef = latest.get("tef01") or latest.get("tef02")
                tef_str = f"{tef:.1f} °C (TEF01)" if tef is not None else "Online"
                add_row("Spiral Blast Freezer", lnk_sbf, "NORMAL", tef_str)
            else:
                add_row("Spiral Blast Freezer", lnk_sbf, "OFFLINE", "No Data")
        except:
            add_row("Spiral Blast Freezer", lnk_sbf, "OFFLINE", "Data Error")

        # --- Boiler (live) ---
        try:
            gas_data = read_csv("boiler_gas_total.csv", "gas")
            if gas_data:
                gas_latest = gas_data[-1]["gas"]
                add_row("Boiler Systems", lnk_boiler, "NORMAL", f"{gas_latest:,.0f} kg Gas Total")
            else:
                add_row("Boiler Systems", lnk_boiler, "OFFLINE", "No Data")
        except:
            add_row("Boiler Systems", lnk_boiler, "OFFLINE", "Data Error")

        # --- CCTV (live) ---
        try:
            cctv_live = get_cctv_raw_data()
            if not cctv_live.empty:
                total_c = len(cctv_live)
                offline_c = len(cctv_live[cctv_live['Current Status'].str.lower() != 'online'])
                cctv_status = "ATTENTION" if offline_c > 0 else "NORMAL"
                add_row("CCTV Monitoring", lnk_cctv, cctv_status, f"{offline_c}/{total_c} Cameras Offline")
            else:
                add_row("CCTV Monitoring", lnk_cctv, "OFFLINE", "Data Error")
        except:
            add_row("CCTV Monitoring", lnk_cctv, "OFFLINE", "Data Error")

        # --- Air Compressor (live) ---
        try:
            ac_live = load_aircompressor_data()
            if ac_live:
                ac_kpi = calculate_aircompressor_kpis(ac_live)
                add_row("Air Compressor", lnk_ac, "NORMAL", f"{ac_kpi['flow']:.2f} m³ Flow")
            else:
                add_row("Air Compressor", lnk_ac, "OFFLINE", "No Data")
        except:
            add_row("Air Compressor", lnk_ac, "OFFLINE", "Data Error")

        # --- Kitchen Equipment (live) ---
        try:
            kit_apis = [
                ("Hobart Sanitizer", api_hobart),
                ("Steambox", api_steambox),
                ("X-Ray Inspection", api_xray),
                ("Checkweigher", api_checkweigher),
            ]
            kit_online = 0
            for _, fn in kit_apis:
                try:
                    fn()
                    kit_online += 1
                except:
                    pass
            kit_status = "NORMAL" if kit_online == 4 else "ATTENTION"
            add_row("Kitchen Equipment", lnk_kitchen, kit_status, f"{kit_online}/4 Units Online")
        except:
            add_row("Kitchen Equipment", lnk_kitchen, "OFFLINE", "Data Error")

        # --- PAGE 3: TEMPERATURE TABLE ---
        pdf.add_page()
        pdf.set_link(lnk_tmp, page=pdf.page_no())

        pdf.set_font('helvetica', 'B', 16)
        pdf.cell(0, 10, "1. Temperature Monitoring - Cold Rooms",
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        try:
            conn = sqlite3.connect(os.path.join(BASE_DIR, "temps.db"))
            df_temp = pd.read_sql("SELECT * FROM room_temperature", conn)
            conn.close()
            render_temperature_table(pdf, df_temp, generated_time)
        except:
            pdf.cell(0, 10, "Temperature data unavailable",
                     new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # --- PAGE 4: MDB ---
        pdf.add_page()
        pdf.set_link(lnk_mdb, page=pdf.page_no())

        pdf.set_font('helvetica', 'B', 16)
        pdf.cell(0, 10, "2. Power Systems (MDB)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        pdf.set_font('helvetica', '', 11)
        pdf.multi_cell(
            0, 8,
            "This section presents an operational overview of the Main Distribution Board (MDB) "
            "and Emergency Main Distribution Board (EMDB) systems. Data reflects the most recent "
            "readings captured from the live power monitoring infrastructure."
        )
        pdf.ln(4)

        try:
            # Fetch MDB data from internal API or function
            mdb_data = collect_mdb_data() # MUST already exist (used by /api/mdb)

            # --- MDB Energy Distribution ---
            mdb_panels = ["mdb_6", "mdb_7", "mdb_8", "mdb_9", "mdb_10"]
            mdb_energy = {}
            mdb_periods = {}
            panel_files = {
                "mdb_6":  "mdb6_energy.csv",
                "mdb_7":  "mdb7_energy.csv",
                "mdb_8":  "mdb8_energy.csv",
                "mdb_9":  "mdb9_energy.csv",
                "mdb_10": "mdb10_energy.csv",
            }

            for key in mdb_panels:
                label = key.upper().replace("_", "-")
                readings = mdb_data["energy"].get(key, [])
                mdb_energy[label] = readings[-1]["kwh"] if readings else 0
                mdb_periods[label] = get_mdb_period(panel_files[key])

            render_mdb_energy_table(pdf, mdb_energy, periods=mdb_periods)

            # --- EMDB Summary ---
            emdb_list = mdb_data["energy"].get("emdb_1", [])
            emdb_latest = emdb_list[-1]["kwh"] if emdb_list else 0
            render_emdb_summary(pdf, emdb_latest)

            # --- Generator Status ---
            render_generator_status_table(pdf, mdb_data["generators"])

            # --- MDB Charts ---
            pdf.ln(4)
            pdf.set_font('helvetica', 'B', 12)
            pdf.cell(0, 8, "2.2  MDB Energy & Generator Charts", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(1)
            try:
                mdb_charts = generate_mdb_charts(mdb_data)
                for chart_key, chart_label in [
                    ("energy_bar",  "Energy Distribution by Panel (Latest Reading)"),
                    ("emdb_trend",  "EMDB-1 Consumption Trend"),
                    ("gen_runtime", "Generator Cumulative Runtime (hrs)"),
                ]:
                    cp = mdb_charts.get(chart_key)
                    if cp:
                        temp_files.append(cp)
                        pdf.set_font('helvetica', 'B', 10)
                        pdf.cell(0, 7, chart_label, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                        pdf.image(cp, x=10, w=190)
                        pdf.ln(3)
            except Exception as ce:
                pdf.set_font('helvetica', 'I', 9)
                pdf.cell(0, 7, f"Charts unavailable: {ce}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        except Exception as e:
            pdf.set_font('helvetica', '', 11)
            pdf.cell(
                0, 10,
                "Power system data unavailable for reporting",
                new_x=XPos.LMARGIN,
                new_y=YPos.NEXT
            )


        # =====================================================
        # --- PAGE 5: WTP MAIN SUMMARY ---
        # =====================================================
        pdf.add_page()
        pdf.set_link(lnk_util, page=pdf.page_no())
        pdf.set_font('helvetica', 'B', 16)
        pdf.cell(0, 10, "3. Water Treatment Plant (WTP)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font('helvetica', '', 9)
        pdf.set_text_color(100, 116, 139)
        pdf.cell(0, 5, f"Report generated: {datetime.now().strftime('%d %b %Y  %H:%M')}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(0)
        pdf.ln(3)

        try:
            wtp = get_wtp_raw_data()
            ft  = wtp["flow_totals"]

            # --- Load per-source data ---
            ro_pres_data  = load_wtp_pressure_data('ro')
            sw1_pres_data = load_wtp_pressure_data('softwater1')
            sw2_pres_data = load_wtp_pressure_data('softwater2')
            ro_cl_data    = load_wtp_chlorine_data('ro')
            sw1_cl_data   = load_wtp_chlorine_data('softwater1')
            sw2_cl_data   = load_wtp_chlorine_data('softwater2')

            # Latest values
            last_well  = ft.get("deep_well",   [{}])[-1].get("m3", 0) if ft.get("deep_well")   else 0
            last_soft1 = ft.get("soft_water_1",[{}])[-1].get("m3", 0) if ft.get("soft_water_1") else 0
            last_soft2 = ft.get("soft_water_2",[{}])[-1].get("m3", 0) if ft.get("soft_water_2") else 0
            last_ro    = ft.get("ro_water",    [{}])[-1].get("m3", 0) if ft.get("ro_water")    else 0
            last_fire  = ft.get("fire_water",  [{}])[-1].get("m3", 0) if ft.get("fire_water")  else 0

            fr = wtp.get("flow_rates", {})

            ro_pres_val  = ro_pres_data[-1]["bar"]  if ro_pres_data  else None
            sw1_pres_val = sw1_pres_data[-1]["bar"] if sw1_pres_data else None
            sw2_pres_val = sw2_pres_data[-1]["bar"] if sw2_pres_data else None
            ro_cl_val    = ro_cl_data[-1]["mg"]     if ro_cl_data    else None
            sw1_cl_val   = sw1_cl_data[-1]["mg"]    if sw1_cl_data   else None
            sw2_cl_val   = sw2_cl_data[-1]["mg"]    if sw2_cl_data   else None

            def fmt(v, decimals=2): return f"{v:.{decimals}f}" if v is not None else "--"
            def cl_status(v):       return ("ATTENTION" if v < 0.1 else "NORMAL") if v is not None else "UNAVAILABLE"

            # ── 3.1 Water Source Flow Summary ───────────────────────────────
            pdf.set_font('helvetica', 'B', 12)
            pdf.cell(0, 8, "3.1  Water Source Flow Summary", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(1)
            render_simple_table(
                pdf,
                ["Water Source", "Total Accumulation (m\xb3)", "Flow Rate (m\xb3/hr)"],
                [
                    ["Deep Well",       f"{last_well:,.0f}",  fmt(fr.get('deep_well'), 2)],
                    ["Softwater No. 1", f"{last_soft1:,.0f}", fmt(fr.get('soft_water_1'), 2)],
                    ["Softwater No. 2", f"{last_soft2:,.0f}", fmt(fr.get('soft_water_2'), 2)],
                    ["RO Water",        f"{last_ro:,.0f}",    fmt(fr.get('ro_water'), 2)],
                    ["Fire Water Tank", f"{last_fire:,.0f}",  fmt(fr.get('fire_water'), 2)],
                ],
                [70, 60, 60]
            )
            pdf.ln(6)

            # ── 3.2 Pressure & Chlorine Status ──────────────────────────────
            pdf.set_font('helvetica', 'B', 12)
            pdf.cell(0, 8, "3.2  Pressure & Water Quality Status", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(1)
            render_simple_table(
                pdf,
                ["Source", "Latest Pressure (bar)", "Latest Chlorine (mg)", "Chlorine Status"],
                [
                    ["RO Water",        fmt(ro_pres_val,  1), fmt(ro_cl_val),  cl_status(ro_cl_val)],
                    ["Softwater No. 1", fmt(sw1_pres_val, 1), fmt(sw1_cl_val), cl_status(sw1_cl_val)],
                    ["Softwater No. 2", fmt(sw2_pres_val, 1), fmt(sw2_cl_val), cl_status(sw2_cl_val)],
                ],
                [50, 50, 50, 45]
            )
            pdf.ln(6)

            # ── 3.3 Pressure Trend (all 3 sources) ──────────────────────────
            pdf.set_font('helvetica', 'B', 12)
            pdf.cell(0, 8, "3.3  System Pressure Trends (bar)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(1)
            pres_chart = save_wtp_multi_line_chart(
                [
                    {'label': 'RO Water',        'data': ro_pres_data,  'val_key': 'bar', 'color': '#10b981'},
                    {'label': 'Softwater No. 1', 'data': sw1_pres_data, 'val_key': 'bar', 'color': '#3b82f6'},
                    {'label': 'Softwater No. 2', 'data': sw2_pres_data, 'val_key': 'bar', 'color': '#f59e0b'},
                ],
                "System Pressure Trends  to  All Sources", "bar", "tmp_wtp_pres_multi.png"
            )
            if pres_chart:
                temp_files.append(pres_chart)
                pdf.image(pres_chart, x=10, w=190)
            else:
                pdf.set_font('helvetica', 'I', 9)
                pdf.cell(0, 7, "No pressure data available.", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(4)

            # ── 3.4 Chlorine Trend (all 3 sources) ──────────────────────────
            pdf.set_font('helvetica', 'B', 12)
            pdf.cell(0, 8, "3.4  Chlorine Monitoring (mg)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(1)
            cl_chart = save_wtp_multi_line_chart(
                [
                    {'label': 'RO Water',        'data': ro_cl_data,  'val_key': 'mg', 'color': '#10b981'},
                    {'label': 'Softwater No. 1', 'data': sw1_cl_data, 'val_key': 'mg', 'color': '#3b82f6'},
                    {'label': 'Softwater No. 2', 'data': sw2_cl_data, 'val_key': 'mg', 'color': '#f59e0b'},
                ],
                "Residual Chlorine Trends  to  All Sources", "mg/L", "tmp_wtp_cl_multi.png"
            )
            if cl_chart:
                temp_files.append(cl_chart)
                pdf.image(cl_chart, x=10, w=190)
            else:
                pdf.set_font('helvetica', 'I', 9)
                pdf.cell(0, 7, "No chlorine data available.", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        except Exception as e:
            import traceback
            print(f"PDF WTP Main Error: {e}\n{traceback.format_exc()}")
            pdf.cell(0, 10, f"WTP data error: {e}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # =====================================================
        # --- PAGE 6: RO WATER ---
        # =====================================================
        pdf.add_page()
        pdf.set_font('helvetica', 'B', 16)
        pdf.cell(0, 10, "3.A  RO Water Supply", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font('helvetica', '', 9)
        pdf.set_text_color(100, 116, 139)
        pdf.cell(0, 5, f"Report generated: {datetime.now().strftime('%d %b %Y  %H:%M')}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(0)
        pdf.ln(3)

        try:
            wtp_ro     = get_wtp_raw_data()
            ro_pres    = load_wtp_pressure_data('ro')
            ro_cl      = load_wtp_chlorine_data('ro')

            ro_total   = wtp_ro["flow_totals"].get("ro_water", [{}])[-1].get("m3", 0) if wtp_ro["flow_totals"].get("ro_water") else 0
            ro_pv      = ro_pres[-1]["bar"] if ro_pres else None
            ro_cv      = ro_cl[-1]["mg"]    if ro_cl   else None

            cl_vals    = [p["mg"] for p in ro_cl] if ro_cl else []
            avg_cl     = sum(cl_vals) / len(cl_vals) if cl_vals else None
            max_cl     = max(cl_vals) if cl_vals else None
            min_cl     = min(cl_vals) if cl_vals else None
            cl_period  = f"{ro_cl[0]['time']}   to   {ro_cl[-1]['time']}" if ro_cl else "--"
            pr_period  = f"{ro_pres[0]['time']}   to   {ro_pres[-1]['time']}" if ro_pres else "--"

            # KPI table
            pdf.set_font('helvetica', 'B', 12)
            pdf.cell(0, 8, "Key Performance Indicators", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(1)
            render_simple_table(
                pdf,
                ["Metric", "Value"],
                [
                    ["RO Water Supply Total (m\xb3)",     f"{ro_total:,.0f}"],
                    ["Latest Supply Pressure (bar)",        fmt(ro_pv, 1)],
                    ["Pressure Data Period",                pr_period],
                    ["Latest Chlorine (mg)",               fmt(ro_cv)],
                    ["Average Chlorine (mg)",              fmt(avg_cl)],
                    ["Maximum Chlorine (mg)",              fmt(max_cl)],
                    ["Minimum Chlorine (mg)",              fmt(min_cl)],
                    ["Chlorine Data Period",               cl_period],
                    ["System Status",                      cl_status(ro_cv)],
                ],
                [100, 85]
            )
            pdf.ln(5)

            # Pressure chart
            pdf.set_font('helvetica', 'B', 12)
            pdf.cell(0, 8, "Supply Pressure Trend (bar)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(1)
            p = save_wtp_line_chart(ro_pres, 'bar', "RO Water  to  Supply Pressure", "bar", "tmp_ro_pres_sub.png", '#3b82f6')
            if p:
                temp_files.append(p)
                pdf.image(p, x=10, w=190)
            else:
                pdf.set_font('helvetica', 'I', 9); pdf.cell(0, 7, "No pressure data.", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(4)

            # Chlorine chart
            pdf.set_font('helvetica', 'B', 12)
            pdf.cell(0, 8, "Residual Chlorine Monitoring (mg)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(1)
            p = save_wtp_line_chart(ro_cl, 'mg', "RO Water  to  Residual Chlorine", "mg/L", "tmp_ro_cl_sub.png", '#f59e0b')
            if p:
                temp_files.append(p)
                pdf.image(p, x=10, w=190)
            else:
                pdf.set_font('helvetica', 'I', 9); pdf.cell(0, 7, "No chlorine data.", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        except Exception as e:
            import traceback
            print(f"PDF RO Error: {e}\n{traceback.format_exc()}")
            pdf.cell(0, 10, f"RO data error: {e}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # =====================================================
        # --- PAGE 7: SOFTWATER NO. 1 ---
        # =====================================================
        pdf.add_page()
        pdf.set_font('helvetica', 'B', 16)
        pdf.cell(0, 10, "3.B  Softwater Supply No. 1", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font('helvetica', '', 9)
        pdf.set_text_color(100, 116, 139)
        pdf.cell(0, 5, f"Report generated: {datetime.now().strftime('%d %b %Y  %H:%M')}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(0)
        pdf.ln(3)

        try:
            wtp_s1    = get_wtp_raw_data()
            sw1_pres  = load_wtp_pressure_data('softwater1')
            sw1_cl    = load_wtp_chlorine_data('softwater1')

            sw1_total = wtp_s1["flow_totals"].get("soft_water_1", [{}])[-1].get("m3", 0) if wtp_s1["flow_totals"].get("soft_water_1") else 0
            sw1_pv    = sw1_pres[-1]["bar"] if sw1_pres else None
            sw1_cv    = sw1_cl[-1]["mg"]    if sw1_cl   else None

            cl_vals   = [p["mg"] for p in sw1_cl] if sw1_cl else []
            avg_cl    = sum(cl_vals) / len(cl_vals) if cl_vals else None
            max_cl    = max(cl_vals) if cl_vals else None
            min_cl    = min(cl_vals) if cl_vals else None
            cl_period = f"{sw1_cl[0]['time']}   to   {sw1_cl[-1]['time']}" if sw1_cl else "--"
            pr_period = f"{sw1_pres[0]['time']}   to   {sw1_pres[-1]['time']}" if sw1_pres else "--"

            pdf.set_font('helvetica', 'B', 12)
            pdf.cell(0, 8, "Key Performance Indicators", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(1)
            render_simple_table(
                pdf,
                ["Metric", "Value"],
                [
                    ["Softwater 1 Supply Total (m\xb3)",  f"{sw1_total:,.0f}"],
                    ["Latest Supply Pressure (bar)",        fmt(sw1_pv, 1)],
                    ["Pressure Data Period",                pr_period],
                    ["Latest Chlorine (mg)",               fmt(sw1_cv)],
                    ["Average Chlorine (mg)",              fmt(avg_cl)],
                    ["Maximum Chlorine (mg)",              fmt(max_cl)],
                    ["Minimum Chlorine (mg)",              fmt(min_cl)],
                    ["Chlorine Data Period",               cl_period],
                    ["System Status",                      cl_status(sw1_cv)],
                ],
                [100, 85]
            )
            pdf.ln(5)

            pdf.set_font('helvetica', 'B', 12)
            pdf.cell(0, 8, "Supply Pressure Trend (bar)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(1)
            p = save_wtp_line_chart(sw1_pres, 'bar', "Softwater No. 1  to  Supply Pressure", "bar", "tmp_sw1_pres_sub.png", '#3b82f6')
            if p:
                temp_files.append(p)
                pdf.image(p, x=10, w=190)
            else:
                pdf.set_font('helvetica', 'I', 9); pdf.cell(0, 7, "No pressure data.", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(4)

            pdf.set_font('helvetica', 'B', 12)
            pdf.cell(0, 8, "Residual Chlorine Monitoring (mg)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(1)
            p = save_wtp_line_chart(sw1_cl, 'mg', "Softwater No. 1  to  Residual Chlorine", "mg/L", "tmp_sw1_cl_sub.png", '#f59e0b')
            if p:
                temp_files.append(p)
                pdf.image(p, x=10, w=190)
            else:
                pdf.set_font('helvetica', 'I', 9); pdf.cell(0, 7, "No chlorine data.", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        except Exception as e:
            import traceback
            print(f"PDF SW1 Error: {e}\n{traceback.format_exc()}")
            pdf.cell(0, 10, f"Softwater 1 data error: {e}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # =====================================================
        # --- PAGE 8: SOFTWATER NO. 2 ---
        # =====================================================
        pdf.add_page()
        pdf.set_font('helvetica', 'B', 16)
        pdf.cell(0, 10, "3.C  Softwater Supply No. 2", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font('helvetica', '', 9)
        pdf.set_text_color(100, 116, 139)
        pdf.cell(0, 5, f"Report generated: {datetime.now().strftime('%d %b %Y  %H:%M')}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(0)
        pdf.ln(3)

        try:
            wtp_s2    = get_wtp_raw_data()
            sw2_pres  = load_wtp_pressure_data('softwater2')
            sw2_cl    = load_wtp_chlorine_data('softwater2')

            sw2_total = wtp_s2["flow_totals"].get("soft_water_2", [{}])[-1].get("m3", 0) if wtp_s2["flow_totals"].get("soft_water_2") else 0
            sw2_pv    = sw2_pres[-1]["bar"] if sw2_pres else None
            sw2_cv    = sw2_cl[-1]["mg"]    if sw2_cl   else None

            cl_vals   = [p["mg"] for p in sw2_cl] if sw2_cl else []
            avg_cl    = sum(cl_vals) / len(cl_vals) if cl_vals else None
            max_cl    = max(cl_vals) if cl_vals else None
            min_cl    = min(cl_vals) if cl_vals else None
            cl_period = f"{sw2_cl[0]['time']}   to   {sw2_cl[-1]['time']}" if sw2_cl else "--"
            pr_period = f"{sw2_pres[0]['time']}   to   {sw2_pres[-1]['time']}" if sw2_pres else "No data yet"

            pdf.set_font('helvetica', 'B', 12)
            pdf.cell(0, 8, "Key Performance Indicators", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(1)
            render_simple_table(
                pdf,
                ["Metric", "Value"],
                [
                    ["Softwater 2 Supply Total (m\xb3)",  f"{sw2_total:,.0f}"],
                    ["Latest Supply Pressure (bar)",        fmt(sw2_pv, 1)],
                    ["Pressure Data Period",                pr_period],
                    ["Latest Chlorine (mg)",               fmt(sw2_cv)],
                    ["Average Chlorine (mg)",              fmt(avg_cl)],
                    ["Maximum Chlorine (mg)",              fmt(max_cl)],
                    ["Minimum Chlorine (mg)",              fmt(min_cl)],
                    ["Chlorine Data Period",               cl_period],
                    ["System Status",                      cl_status(sw2_cv)],
                ],
                [100, 85]
            )
            pdf.ln(5)

            pdf.set_font('helvetica', 'B', 12)
            pdf.cell(0, 8, "Supply Pressure Trend (bar)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(1)
            p = save_wtp_line_chart(sw2_pres, 'bar', "Softwater No. 2  to  Supply Pressure", "bar", "tmp_sw2_pres_sub.png", '#f59e0b')
            if p:
                temp_files.append(p)
                pdf.image(p, x=10, w=190)
            else:
                pdf.set_font('helvetica', 'I', 9); pdf.cell(0, 7, "No pressure data available yet.", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(4)

            pdf.set_font('helvetica', 'B', 12)
            pdf.cell(0, 8, "Residual Chlorine Monitoring (mg)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(1)
            p = save_wtp_line_chart(sw2_cl, 'mg', "Softwater No. 2  to  Residual Chlorine", "mg/L", "tmp_sw2_cl_sub.png", '#f59e0b')
            if p:
                temp_files.append(p)
                pdf.image(p, x=10, w=190)
            else:
                pdf.set_font('helvetica', 'I', 9); pdf.cell(0, 7, "No chlorine data available yet.", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        except Exception as e:
            import traceback
            print(f"PDF SW2 Error: {e}\n{traceback.format_exc()}")
            pdf.cell(0, 10, f"Softwater 2 data error: {e}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)


        # --- PAGE 6: WWTP ---
        pdf.add_page()
        pdf.set_link(lnk_wwtp, page=pdf.page_no()) 

        pdf.set_font('helvetica', 'B', 16)
        pdf.cell(0, 10, "4. Waste Water Treatment Plant (WWTP)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        
        pdf.set_font('helvetica', '', 11)
        pdf.multi_cell(0, 8, "Operational report for Effluent and Raw Waste Water systems.")
        pdf.ln(5)

        try:
            # 1. Fetch the data using the helper
            wwtp_data = get_wwtp_report_data()

            # 2. Update these lines to use the correct keys from get_wwtp_report_data()
            l_temp = safe_float(wwtp_data.get('raw_temp', pd.DataFrame()))
            l_eff  = safe_float(wwtp_data.get('effluent', pd.DataFrame()))
            l_raw  = safe_float(wwtp_data.get('raw_pump', pd.DataFrame()))

            # 3. Render Table
            render_simple_table(
                pdf,
                ["Parameter", "Latest Reading", "Unit"],
                [
                    ["Inflow Waste Water Temp", f"{l_temp:.1f}", "deg C"],
                    ["Effluent Pump Total", f"{l_eff:,.0f}", "m3"],
                    ["Raw Waste Water Pump", f"{l_raw:,.0f}", "m3"],
                    ["System Status", "NORMAL" if l_temp < 35 else "WARNING", "Status"]
                ],
                [80, 40, 30]
            )


            # -------------------------------
            # 4.2 Waste Water Temperature Trend
            # -------------------------------
            pdf.set_font('helvetica', 'B', 12)
            pdf.cell(0, 10, "4.2 Waste Water Temperature Trend", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

            # KPI summary row (mirrors the dashboard cards)
            df_ctrl   = wwtp_data.get('ctrl_energy')
            df_pmg    = wwtp_data.get('pmg_energy')
            total_kwh = 0.0
            if df_pmg is not None and not df_pmg.empty:
                total_kwh += float(df_pmg.iloc[-1]['Value'])
            if df_ctrl is not None and not df_ctrl.empty:
                total_kwh += float(df_ctrl.iloc[-1]['Value'])

            df_eff = wwtp_data.get('effluent')
            df_raw = wwtp_data.get('raw_pump')
            eff_latest = float(df_eff.iloc[-1]['Value']) if df_eff is not None and not df_eff.empty else 0.0
            raw_latest = float(df_raw.iloc[-1]['Value']) if df_raw is not None and not df_raw.empty else 0.0
            pump_eff   = round(((raw_latest - eff_latest) / raw_latest * 100), 1) if raw_latest > 0 else 0.0
            active_pumps = sum(1 for v in [eff_latest, raw_latest] if v > 0)

            pdf.ln(2)
            kpi_items_wwtp = [
                ("TOTAL ENERGY", f"{total_kwh:,.0f}", "kWh"),
                ("ACTIVE PUMPS", str(active_pumps), ""),
                ("RAW WATER TEMP", f"{l_temp:.1f}", "deg C"),
                ("PUMP EFFICIENCY", f"{pump_eff:.1f}", "%"),
            ]
            card_w = 44; card_h = 20; card_y = pdf.get_y()
            for i, (label, val, unit) in enumerate(kpi_items_wwtp):
                x = pdf.l_margin + i * (card_w + 3)
                pdf.set_draw_color(220, 230, 240)
                pdf.set_fill_color(248, 250, 252)
                pdf.rect(x, card_y, card_w, card_h, style='FD')
                pdf.set_font('helvetica', 'B', 6); pdf.set_text_color(100, 116, 139)
                pdf.set_xy(x + 2, card_y + 2)
                pdf.cell(card_w - 4, 5, label)
                pdf.set_font('helvetica', 'B', 12); pdf.set_text_color(15, 23, 42)
                pdf.set_xy(x + 2, card_y + 8)
                pdf.cell(card_w - 4, 7, f"{val} {unit}".strip())
            pdf.set_text_color(0); pdf.set_xy(pdf.l_margin, card_y + card_h + 4)
            pdf.ln(2)

            df_temp = wwtp_data.get('raw_temp')
            if df_temp is not None and not df_temp.empty:
                chart_df = df_temp.tail(24).copy()
                chart_df['time'] = chart_df['dt'].dt.strftime('%H:%M')
                temp_path = save_wtp_chart(
                    chart_df.to_dict('records'), 'Value',
                    "Inflow Temperature Trend (deg C)",
                    "deg C", "tmp_wwtp_temp.png", color='#f59e0b'
                )
                if temp_path:
                    temp_files.append(temp_path)
                    pdf.set_font('helvetica', 'B', 10)
                    pdf.cell(0, 7, "Inflow Temperature Trend", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                    pdf.image(temp_path, x=15, w=170)
                    pdf.ln(3)

            # -------------------------------
            # 4.3 Effluent Flow & Energy
            # -------------------------------
            df_energy   = wwtp_data.get('pmg_energy')
            df_effluent = wwtp_data.get('effluent')
            has_43_data = (df_energy is not None and not df_energy.empty) or \
                          (df_effluent is not None and not df_effluent.empty)

            if has_43_data:
                pdf.set_font('helvetica', 'B', 12)
                pdf.cell(0, 10, "4.3 Effluent Flow & Energy Consumption", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

                if df_effluent is not None and not df_effluent.empty:
                    chart_df = df_effluent.tail(24).copy()
                    chart_df['time'] = chart_df['dt'].dt.strftime('%H:%M')
                    eff_path = save_wtp_chart(
                        chart_df.to_dict('records'), 'Value',
                        "Effluent Pump Total (m3)", "m3", "tmp_wwtp_effluent.png", color='#10b981'
                    )
                    if eff_path:
                        temp_files.append(eff_path)
                        pdf.set_font('helvetica', 'B', 10)
                        pdf.cell(0, 7, "Effluent Pump Total", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                        pdf.image(eff_path, x=15, w=170)
                        pdf.ln(4)

                if df_energy is not None and not df_energy.empty:
                    chart_df = df_energy.tail(24).copy()
                    chart_df['time'] = chart_df['dt'].dt.strftime('%H:%M')
                    energy_path = save_wtp_chart(
                        chart_df.to_dict('records'), 'Value',
                        "Main WWTP Energy (kWh)", "kWh", "tmp_wwtp_energy.png", color='#3b82f6'
                    )
                    if energy_path:
                        temp_files.append(energy_path)
                        pdf.set_font('helvetica', 'B', 10)
                        pdf.cell(0, 7, "WWTP Energy Consumption", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                        pdf.image(energy_path, x=15, w=170)
                        pdf.ln(4)

        except Exception as e:
            print(f"🔥 PDF WWTP Error: {e}")
            pdf.set_text_color(220, 38, 38)
            pdf.cell(0, 10, f"WWTP Data Error: {str(e)}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_text_color(0)

        # --- SBF PAGE ---
        pdf.add_page()
        pdf.set_link(lnk_sbf, page=pdf.page_no())
        pdf.set_font('helvetica', 'B', 16)
        pdf.cell(0, 10, "5. Spiral Blast Freezer Monitoring", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font('helvetica', '', 9)
        pdf.set_text_color(100, 116, 139)
        pdf.cell(0, 5, f"Report generated: {datetime.now().strftime('%d %b %Y  %H:%M')}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(0)
        pdf.ln(4)

        try:
            raw = {
                "Spiral 01": read_sbf_csv(os.path.join(DATA_DIR, "sbf_spiral1_Data.csv")),
                "Spiral 02": read_sbf_csv(os.path.join(DATA_DIR, "sbf_spiral2_Data.csv")),
                "Spiral 03": read_sbf_csv(os.path.join(DATA_DIR, "sbf_spiral3_Data.csv")),
            }

            def sbf_last(records):
                return records[-1] if records else {}

            def sbf_avg_runtime(records):
                if not records: return 0.0
                return sum(float(r.get('runtime') or 0) for r in records) / len(records) / 60

            def sbf_runtime_hrs(r):
                return float(r.get('runtime') or 0) / 60

            def sbf_status(r):
                return "RUNNING" if float(r.get('runtime') or 0) > 0 else "STOPPED"

            s = {k: sbf_last(v) for k, v in raw.items()}

            # ── KPI SUMMARY ROW ─────────────────────────────────────────────
            active = sum(1 for r in s.values() if float(r.get('runtime') or 0) > 0)
            kpi_items = [
                ("ACTIVE FREEZERS", f"{active} / 3", "System Running Status"),
                ("SPIRAL 01 AVG RUNTIME", f"{sbf_avg_runtime(raw['Spiral 01']):.2f}", "Hours"),
                ("SPIRAL 02 AVG RUNTIME", f"{sbf_avg_runtime(raw['Spiral 02']):.2f}", "Hours"),
                ("SPIRAL 03 AVG RUNTIME", f"{sbf_avg_runtime(raw['Spiral 03']):.2f}", "Hours"),
            ]
            card_w = 46
            card_h = 24
            card_y = pdf.get_y()   # lock Y for all 4 cards
            for i, (label, value, sub) in enumerate(kpi_items):
                x = pdf.l_margin + i * (card_w + 2)
                pdf.set_draw_color(220, 230, 240)
                pdf.set_fill_color(240, 255, 250) if i == 0 else pdf.set_fill_color(255, 255, 255)
                pdf.rect(x, card_y, card_w, card_h, style='FD')
                # Label
                pdf.set_xy(x + 2, card_y + 2)
                pdf.set_font('helvetica', '', 6)
                pdf.set_text_color(100, 116, 139)
                pdf.cell(card_w - 4, 4, label)
                # Value
                pdf.set_xy(x + 2, card_y + 7)
                pdf.set_font('helvetica', 'B', 14)
                pdf.set_text_color(16, 185, 129) if i == 0 else pdf.set_text_color(30, 41, 59)
                pdf.cell(card_w - 4, 9, value)
                # Sub label
                pdf.set_xy(x + 2, card_y + 17)
                pdf.set_font('helvetica', '', 7)
                pdf.set_text_color(100, 116, 139)
                pdf.cell(card_w - 4, 4, sub)
            pdf.set_text_color(0)
            pdf.set_draw_color(0)
            # Advance cursor past the cards
            pdf.set_xy(pdf.l_margin, card_y + card_h + 6)

            # ── TEMPERATURE TREND CHART ──────────────────────────────────────
            pdf.set_font('helvetica', 'B', 12)
            pdf.cell(0, 8, "Freezer Temperature Performance Trend (TEF01)",
                     new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(1)
            tef_chart = generate_sbf_tef_chart(raw)
            if tef_chart:
                temp_files.append(tef_chart)
                pdf.image(tef_chart, x=10, w=190)
            else:
                pdf.set_font('helvetica', 'I', 9)
                pdf.cell(0, 7, "No temperature trend data available.",
                         new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(5)

            # ── OPERATIONAL PERFORMANCE SUMMARY TABLE ────────────────────────
            pdf.set_font('helvetica', 'B', 12)
            pdf.cell(0, 8, "Operational Performance Summary",
                     new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(1)
            perf_rows = []
            for unit_name, r in s.items():
                tef01 = float(r.get('tef01') or 0)
                tef02 = float(r.get('tef02') or 0)
                pt01  = float(r.get('pt01')  or 0)
                pt02  = float(r.get('pt02')  or 0)
                ft    = float(r.get('freezing_time') or 0)
                rt    = sbf_runtime_hrs(r)
                perf_rows.append([
                    unit_name,
                    f"{tef01:.1f} / {tef02:.1f}",
                    f"{pt01:.2f} / {pt02:.2f}",
                    f"{ft:.0f} min",
                    f"{rt:.2f} hrs",
                    sbf_status(r),
                ])
            render_simple_table(pdf,
                ["Unit", "Temp T/B (°C)", "Pressure (kg/cm²)", "Freezing Time", "Runtime", "Status"],
                perf_rows, [30, 35, 40, 32, 28, 25])

        except Exception as e:
            import traceback
            print(f"PDF SBF Error: {e}\n{traceback.format_exc()}")
            pdf.cell(0, 10, f"SBF data error: {e}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # --- BOILER PAGE ---
        pdf.add_page()
        pdf.set_link(lnk_boiler, page=pdf.page_no())
        pdf.set_font('helvetica', 'B', 16)
        pdf.cell(0, 10, "6. Boiler System Monitoring", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font('helvetica', '', 9)
        pdf.set_text_color(100, 116, 139)
        pdf.cell(0, 5, f"Report generated: {datetime.now().strftime('%d %b %Y  %H:%M')}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(0)
        pdf.ln(4)

        try:
            boiler_data = boiler().get_json()
            gas_data  = boiler_data["consumption"]["gas_total_kg"]
            d_steam   = boiler_data["consumption"]["direct_steam_kg"]
            i_steam   = boiler_data["consumption"]["indirect_steam_kg"]
            d_energy  = boiler_data["consumption"]["direct_energy_kwh"]
            i_energy  = boiler_data["consumption"]["indirect_energy_kwh"]

            def lv(lst, key): return lst[-1][key] if lst else 0
            def fv(v, decimals=0):
                return f"{v:,.{decimals}f}" if isinstance(v, (int, float)) else "--"

            # Derived KPIs (matching dashboard logic)
            gas_latest    = lv(gas_data, "gas")
            gas_first     = gas_data[0]["gas"] if gas_data else 0
            delta_gas     = gas_latest - gas_first
            ds_latest     = lv(d_steam, "steam")
            is_latest     = lv(i_steam, "steam")
            ds_first      = d_steam[0]["steam"] if d_steam else 0
            is_first      = i_steam[0]["steam"] if i_steam else 0
            delta_direct  = ds_latest - ds_first
            delta_indirect= is_latest - is_first
            b1_energy     = lv(i_energy, "energy")
            b2_energy     = lv(d_energy, "energy")
            total_energy  = b1_energy + b2_energy
            eff_b1 = round(delta_indirect / (delta_gas * 0.5), 2) if delta_gas > 0 else 0
            eff_b2 = round(delta_direct   / (delta_gas * 0.5), 2) if delta_gas > 0 else 0

            # Stage running status: running if last runtime > second-to-last
            def stage_running(records):
                if len(records) >= 2:
                    return records[-1]["runtime"] > records[-2]["runtime"]
                return False

            stages_b01 = {
                "Stage 1 (Main)":  stage_running(boiler_data["boiler_01"]["stage_1_runtime"]),
                "Stage 2 (Boost)": stage_running(boiler_data["boiler_01"]["stage_2_runtime"]),
                "Stage 3 (Aux)":   stage_running(boiler_data["boiler_01"]["stage_3_runtime"]),
            }
            stages_b02 = {
                "Stage 1 (Main)": stage_running(boiler_data["boiler_02"]["stage_1_runtime"]),
                "Stage 2 (Aux)":  stage_running(boiler_data["boiler_02"]["stage_2_runtime"]),
            }
            b1_active = any(stages_b01.values())
            b2_active = any(stages_b02.values())

            # ── KPI CARDS ────────────────────────────────────────────────────
            kpi_items = [
                ("TOTAL GAS CONSUMPTION", fv(gas_latest), "Main Meter (kg)",      "#3b82f6"),
                ("TOTAL STEAM OUTPUT",    fv(ds_latest + is_latest), "Combined Path (kg)",   "#8b5cf6"),
                ("TOTAL ELECTRICAL",      fv(total_energy), "Combined Panels (kWh)", "#8b5cf6"),
                ("BOILER 1 EFFICIENCY",   fv(eff_b1, 2),  "Indirect Path Ratio",   "#10b981"),
                ("BOILER 2 EFFICIENCY",   fv(eff_b2, 2),  "Direct Path Ratio",     "#10b981"),
            ]
            card_w = 37
            card_h = 24
            card_gap = 1.5
            card_y = pdf.get_y()
            for i, (label, value, sub, color) in enumerate(kpi_items):
                x = pdf.l_margin + i * (card_w + card_gap)
                r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
                pdf.set_draw_color(220, 230, 240)
                pdf.set_fill_color(255, 255, 255)
                pdf.rect(x, card_y, card_w, card_h, style='FD')
                # Top accent line
                pdf.set_fill_color(r, g, b)
                pdf.rect(x, card_y, card_w, 1.2, style='F')
                # Label
                pdf.set_xy(x + 2, card_y + 3)
                pdf.set_font('helvetica', '', 5.5)
                pdf.set_text_color(100, 116, 139)
                pdf.cell(card_w - 4, 3.5, label)
                # Value
                pdf.set_xy(x + 2, card_y + 7.5)
                pdf.set_font('helvetica', 'B', 13)
                pdf.set_text_color(r, g, b)
                pdf.cell(card_w - 4, 8, value)
                # Sub label
                pdf.set_xy(x + 2, card_y + 17)
                pdf.set_font('helvetica', '', 6)
                pdf.set_text_color(100, 116, 139)
                pdf.cell(card_w - 4, 4, sub)
            pdf.set_text_color(0)
            pdf.set_draw_color(0)
            pdf.set_xy(pdf.l_margin, card_y + card_h + 5)

            # ── SUB-UNIT DIAGNOSTIC STATUS  +  ENERGY ANALYSIS (side by side) ─
            section_y = pdf.get_y()
            left_w  = 95
            right_w = 95
            right_x = pdf.l_margin + left_w + 4

            # -- Left: Sub-Unit Diagnostics --
            pdf.set_xy(pdf.l_margin, section_y)
            pdf.set_font('helvetica', 'B', 10)
            pdf.set_text_color(37, 99, 235)
            pdf.cell(2, 7, "")
            pdf.set_text_color(0)
            pdf.set_font('helvetica', 'B', 10)
            pdf.cell(left_w - 2, 7, "Sub-Unit Diagnostic Status", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

            def draw_diag_block(boiler_label, stages_dict, active, start_x, w):
                status_label = "ONLINE" if active else "STANDBY"
                # Header
                pdf.set_xy(start_x, pdf.get_y())
                pdf.set_fill_color(248, 250, 252)
                pdf.set_draw_color(226, 232, 240)
                pdf.set_font('helvetica', 'B', 9)
                pdf.cell(w - 30, 8, f"  {boiler_label}", border=1, fill=True)
                if active:
                    pdf.set_fill_color(209, 250, 229); pdf.set_text_color(6, 95, 70)
                else:
                    pdf.set_fill_color(255, 247, 237); pdf.set_text_color(146, 64, 14)
                pdf.cell(30, 8, status_label, border=1, fill=True, align='C',
                         new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                pdf.set_text_color(0)
                # Stage rows
                for stage_name, running in stages_dict.items():
                    pdf.set_xy(start_x, pdf.get_y())
                    pdf.set_fill_color(255, 255, 255)
                    pdf.set_font('helvetica', '', 8)
                    pdf.cell(w - 12, 7, f"    {stage_name}", border='LRB', fill=True)
                    # Dot indicator
                    dot_x = start_x + w - 10
                    dot_y = pdf.get_y() + 2
                    pdf.set_fill_color(16, 185, 129) if running else pdf.set_fill_color(239, 68, 68)
                    pdf.ellipse(dot_x, dot_y, 3.5, 3.5, style='F')
                    pdf.cell(12, 7, "", border='LRB', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                pdf.ln(3)

            diag_start_y = pdf.get_y()
            draw_diag_block("Boiler 01 (Indirect)", stages_b01, b1_active, pdf.l_margin, left_w)
            draw_diag_block("Boiler 02 (Direct)",   stages_b02, b2_active, pdf.l_margin, left_w)
            diag_end_y = pdf.get_y()

            # -- Right: Energy Consumption Analysis --
            pdf.set_xy(right_x, section_y)
            pdf.set_font('helvetica', 'B', 10)
            pdf.cell(right_w, 7, "Energy Consumption Analysis", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

            energy_items = [
                ("BOILER 1 (PANEL 1 - INDIRECT)", b1_energy, "#10b981"),
                ("BOILER 2 (PANEL 2 - DIRECT)",   b2_energy, "#3b82f6"),
            ]
            bar_max = max(b1_energy, b2_energy, 1)
            for elabel, eval_, ecolor in energy_items:
                pdf.set_xy(right_x, pdf.get_y())
                pdf.set_font('helvetica', '', 6.5)
                pdf.set_text_color(100, 116, 139)
                pdf.cell(right_w, 5, elabel)
                pdf.ln(5)
                pdf.set_xy(right_x, pdf.get_y())
                pdf.set_font('helvetica', 'B', 13)
                r2, g2, b2_ = int(ecolor[1:3],16), int(ecolor[3:5],16), int(ecolor[5:7],16)
                pdf.set_text_color(r2, g2, b2_)
                pdf.cell(right_w, 8, f"{fv(eval_)} kWh")
                pdf.ln(8)
                # Progress bar background
                pdf.set_xy(right_x, pdf.get_y())
                bar_total_w = right_w - 4
                pdf.set_fill_color(226, 232, 240)
                pdf.rect(right_x, pdf.get_y(), bar_total_w, 4, style='F')
                # Progress bar fill
                bar_fill_w = (eval_ / bar_max) * bar_total_w
                pdf.set_fill_color(r2, g2, b2_)
                pdf.rect(right_x, pdf.get_y(), bar_fill_w, 4, style='F')
                pdf.ln(9)
            pdf.set_text_color(0)

            # Move cursor past the taller of the two columns
            pdf.set_xy(pdf.l_margin, max(diag_end_y, pdf.get_y()) + 4)

            # ── CHARTS ───────────────────────────────────────────────────────
            pdf.set_font('helvetica', 'B', 11)
            pdf.cell(0, 7, "Detailed Sub-Boiler Runtimes (hr)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(1)
            rt_chart = generate_boiler_runtime_chart(boiler_data)
            if rt_chart:
                temp_files.append(rt_chart)
                pdf.image(rt_chart, x=10, w=190)
            else:
                pdf.set_font('helvetica', 'I', 9)
                pdf.cell(0, 7, "No runtime data available.", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(4)

            pdf.set_font('helvetica', 'B', 11)
            pdf.cell(0, 7, "Consumption Correlation  (Gas vs Steam)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(1)
            cons_chart = generate_boiler_consumption_chart(boiler_data)
            if cons_chart:
                temp_files.append(cons_chart)
                pdf.image(cons_chart, x=10, w=190)
            else:
                pdf.set_font('helvetica', 'I', 9)
                pdf.cell(0, 7, "No consumption data available.", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        except Exception as e:
            import traceback
            print(f"PDF Boiler Error: {e}\n{traceback.format_exc()}")
            pdf.cell(0, 10, f"Boiler data error: {e}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # --- PAGE 9: CCTV ---
        pdf.add_page()
        pdf.set_link(lnk_cctv, page=pdf.page_no())
        
        pdf.set_font('helvetica', 'B', 16)
        pdf.cell(0, 10, "7. CCTV Monitoring Status", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        
        pdf.set_font('helvetica', '', 11)
        pdf.multi_cell(0, 8, 
            "This section details the online/offline status of the facility surveillance network. "
            "Offline durations and counts are calculated based on the latest automated resource logs."
        )
        pdf.ln(5)

        try:
            cctv_df = get_cctv_raw_data()
            if not cctv_df.empty:
                # 1. Summary Statistics
                total_cams = len(cctv_df)
                offline_cams = len(cctv_df[cctv_df['Current Status'].str.lower() != 'online'])
                offline_pct = (offline_cams / total_cams * 100) if total_cams > 0 else 0.0

                pdf.set_font('helvetica', 'B', 12)
                pdf.cell(0, 10, f"System Overview: {total_cams} Total Cameras | {offline_cams} Offline | Offline Rate: {offline_pct:.1f}%",
                         new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                pdf.ln(2)

                # 2. Render the Detailed Log Table
                render_cctv_table(pdf, cctv_df)
            else:
                pdf.cell(0, 10, "CCTV log file not found or data is empty.", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        except Exception as e:
            print(f"PDF CCTV Error: {e}")
            pdf.cell(0, 10, "Error generating CCTV report section.", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # --- PAGE 10: AIR COMPRESSOR ---
        pdf.add_page()
        pdf.set_link(lnk_ac, page=pdf.page_no())
        pdf.set_font('helvetica', 'B', 16)
        pdf.cell(0, 10, "8. Air Compressor",
                new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        pdf.set_font('helvetica', '', 11)
        pdf.multi_cell(
            0, 8,
            "This section provides an operational overview of the compressed air system, "
            "including energy consumption, airflow performance, and air quality (dewpoint). "
            "Data shown reflects the most recent available measurements."
        )
        pdf.ln(3)

        data = load_aircompressor_data()

        if not data:
            pdf.set_font('helvetica', 'I', 11)
            pdf.cell(0, 10, "Air Compressor data unavailable for reporting.")
        else:
            kpi = calculate_aircompressor_kpis(data)

            # --- KPI TABLE ---
            pdf.set_font('helvetica', 'B', 11)
            pdf.cell(60, 10, "Metric", 1)
            pdf.cell(60, 10, "Latest Value", 1,
                    new_x=XPos.LMARGIN, new_y=YPos.NEXT)

            pdf.set_font('helvetica', '', 11)
            pdf.cell(60, 10, "Air Flow", 1)
            pdf.cell(60, 10, f"{kpi['flow']:.2f} m³", 1,
                    new_x=XPos.LMARGIN, new_y=YPos.NEXT)

            pdf.cell(60, 10, "Energy Consumption", 1)
            pdf.cell(60, 10, f"{kpi['energy']:.2f} kWh", 1,
                    new_x=XPos.LMARGIN, new_y=YPos.NEXT)

            pdf.cell(60, 10, "Dewpoint", 1)
            pdf.cell(60, 10, f"{kpi['dewpoint']:.1f} °C", 1,
                    new_x=XPos.LMARGIN, new_y=YPos.NEXT)

            pdf.cell(60, 10, "Specific Power", 1)
            pdf.cell(60, 10, f"{kpi['efficiency']:.3f} kWh/m³", 1,
                    new_x=XPos.LMARGIN, new_y=YPos.NEXT)

            pdf.ln(5)

            # --- CHARTS ---
            charts = generate_aircompressor_charts(data)

            pdf.set_font('helvetica', 'B', 12)
            pdf.cell(0, 10, "Air Compressor Performance Trends",
                    new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(1)

            eff_path = charts.get("efficiency")
            dew_path = charts.get("dewpoint")
            if eff_path:
                temp_files.append(eff_path)
                pdf.set_font('helvetica', 'B', 10)
                pdf.cell(0, 7, "Specific Power & Flow Efficiency Trend", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                pdf.image(eff_path, x=10, w=190)
                pdf.ln(5)
            else:
                pdf.set_font('helvetica', 'I', 9)
                pdf.cell(0, 7, "Efficiency trend chart unavailable.", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

            if dew_path:
                temp_files.append(dew_path)
                pdf.set_font('helvetica', 'B', 10)
                pdf.cell(0, 7, "Dewpoint Trend (Air Quality)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                pdf.image(dew_path, x=10, w=190)
            else:
                pdf.set_font('helvetica', 'I', 9)
                pdf.cell(0, 7, "Dewpoint trend chart unavailable.", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # --- KITCHEN EQUIPMENT PAGE ---
        pdf.add_page()
        pdf.set_link(lnk_kitchen, page=pdf.page_no())
        pdf.set_font('helvetica', 'B', 16)
        pdf.cell(0, 10, "9. Kitchen Equipment", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font('helvetica', '', 9)
        pdf.set_text_color(100, 116, 139)
        pdf.cell(0, 5, f"Report generated: {datetime.now().strftime('%d %b %Y  %H:%M')}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(0)
        pdf.ln(3)
        pdf.set_font('helvetica', '', 11)
        pdf.multi_cell(0, 8, "Status overview of all kitchen equipment units. Data is simulated from live equipment sensors.")
        pdf.ln(3)

        try:
            kit_info = [
                ("Hobart Sanitizer",  api_hobart,      lambda d: (f"{d['summary']['cycles_today']} cycles today", f"Wash Temp: {d['readings'][-1]['wash_temp']:.1f} °C" if d.get('readings') else "--")),
                ("Steambox",          api_steambox,     lambda d: (f"{d['summary']['units_today']} units today",   f"Chamber: {d['readings'][-1]['avg_chamber_temp']:.1f} °C" if d.get('readings') else "--")),
                ("X-Ray Inspection",  api_xray,         lambda d: (f"{d['summary']['reject_rate_pct']:.2f}% reject rate", f"Inspected: {d['summary']['inspected_today']:,}")),
                ("Checkweigher",      api_checkweigher, lambda d: (f"{d['summary']['pass_rate_pct']:.1f}% pass rate",     f"Total: {d['summary']['total_today']:,} units")),
            ]

            kit_table_rows = []
            for name, fn, metrics_fn in kit_info:
                try:
                    with app.test_request_context():
                        resp = fn()
                        data = resp.get_json()
                    metric1, metric2 = metrics_fn(data)
                    status = "ONLINE"
                except Exception:
                    metric1, metric2, status = "--", "--", "OFFLINE"
                kit_table_rows.append([name, status, metric1, metric2])

            online_count = sum(1 for r in kit_table_rows if r[1] == "ONLINE")

            pdf.set_font('helvetica', 'B', 12)
            pdf.cell(0, 8, f"9.1  Equipment Status Summary  ({online_count}/4 Online)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(1)

            # Header
            pdf.set_font('helvetica', 'B', 10)
            pdf.set_fill_color(30, 41, 59)
            pdf.set_text_color(255)
            for header, w in [("Equipment", 50), ("Status", 25), ("Key Metric", 55), ("Detail", 55)]:
                pdf.cell(w, 11, f" {header}", 1, fill=True)
            pdf.ln()
            pdf.set_text_color(0)

            for row in kit_table_rows:
                name, status, metric1, metric2 = row
                pdf.set_font('helvetica', '', 10)
                pdf.cell(50, 11, f" {name}", 1)
                if status == "ONLINE":
                    pdf.set_fill_color(240, 253, 244); pdf.set_text_color(22, 101, 52)
                else:
                    pdf.set_fill_color(254, 226, 226); pdf.set_text_color(220, 38, 38)
                pdf.cell(25, 11, status, 1, fill=True, align='C')
                pdf.set_text_color(0)
                pdf.cell(55, 11, f" {metric1}", 1)
                pdf.cell(55, 11, f" {metric2}", 1, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

            pdf.ln(6)

            # 9.2 Per-equipment details (each gets its own page below)
            chart_generators = {
                "Hobart Sanitizer":  generate_hobart_charts,
                "Steambox":          generate_steambox_charts,
                "X-Ray Inspection":  generate_xray_charts,
                "Checkweigher":      generate_checkweigher_charts,
            }
            chart_labels = {
                "Hobart Sanitizer":  [("temp", "Wash & Rinse Temperature Trend"), ("cycles", "Hourly Cycle Count")],
                "Steambox":          [("temp", "Chamber Temperature Profile"), ("pressure", "Steam Pressure Trend"), ("throughput", "Hourly Throughput")],
                "X-Ray Inspection":  [("throughput", "Hourly Throughput & Rejects"), ("reject_rate", "Reject Rate Trend")],
                "Checkweigher":      [("distribution", "Weight Distribution"), ("pass_rate", "Pass Rate Trend")],
            }

            for name, fn, _ in kit_info:
                pdf.add_page()
                pdf.set_font('helvetica', 'B', 13)
                pdf.cell(0, 9, f"9.2  {name}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                pdf.ln(1)
                try:
                    with app.test_request_context():
                        data = fn().get_json()

                    # ── Summary table (all equipment) ──────────────────────────
                    pdf.set_font('helvetica', 'B', 11)
                    pdf.cell(0, 8, "Performance Summary", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                    pdf.ln(1)
                    summary = data.get("summary", {})
                    detail_rows = [[k.replace("_", " ").title(), str(v)] for k, v in summary.items()]
                    render_simple_table(pdf, ["Metric", "Value"], detail_rows, [100, 85])
                    pdf.ln(5)

                    # ── HOBART specific sections ───────────────────────────────
                    if name == "Hobart Sanitizer":
                        readings = data.get("readings", [])
                        diag     = data.get("diagnostics", {})

                        # Latest readings table
                        if readings:
                            latest = readings[-1]
                            pdf.set_font('helvetica', 'B', 11)
                            pdf.cell(0, 8, "Latest Readings", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                            pdf.ln(1)
                            render_simple_table(
                                pdf,
                                ["Parameter", "Value", "Target", "Status"],
                                [
                                    ["Wash Temperature",  f"{latest.get('wash_temp', '--'):.1f} °C",   ">= 60 °C",      "OK" if latest.get('wash_temp', 0) >= 60 else "LOW"],
                                    ["Rinse Temperature", f"{latest.get('rinse_temp', '--'):.1f} °C",  ">= 82 °C",      "OK" if latest.get('rinse_temp', 0) >= 82 else "LOW"],
                                    ["Sanitizer Conc.",  f"{int(latest.get('sanitizer_ppm', 0))} ppm", "200-400 ppm",   "OK" if 200 <= latest.get('sanitizer_ppm', 0) <= 400 else "CHECK"],
                                ],
                                [60, 45, 45, 35]
                            )
                            pdf.ln(5)

                        # Unit diagnostics table
                        if diag:
                            pdf.set_font('helvetica', 'B', 11)
                            pdf.cell(0, 8, "Unit Diagnostics", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                            pdf.ln(1)
                            unit_rows = []
                            comp_labels = {"wash_arm": "Wash Arm", "rinse_pump": "Rinse Pump", "dose_pump": "Dose Pump", "door_seal": "Door Seal"}
                            for uid, udata in diag.items():
                                for comp_key, comp_label in comp_labels.items():
                                    ok = udata.get(comp_key, False)
                                    unit_rows.append([uid.upper(), comp_label, "ACTIVE" if ok else "FAULT", "OK" if ok else "ACTION REQUIRED"])
                            render_simple_table(pdf, ["Unit", "Component", "State", "Status"], unit_rows, [30, 55, 40, 60])
                            pdf.ln(5)

                    # ── STEAMBOX specific sections ──────────────────────────────
                    elif name == "Steambox":
                        readings = data.get("readings", [])
                        diag     = data.get("diagnostics", {})

                        # Latest readings table
                        if readings:
                            latest = readings[-1]
                            pdf.set_font('helvetica', 'B', 11)
                            pdf.cell(0, 8, "Latest Readings", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                            pdf.ln(1)
                            render_simple_table(
                                pdf,
                                ["Parameter", "Value", "Target", "Status"],
                                [
                                    ["Avg Chamber Temp",  f"{latest.get('avg_chamber_temp', '--'):.1f} °C", ">= 95 °C",     "OK" if latest.get('avg_chamber_temp', 0) >= 95 else "LOW"],
                                    ["SB-01 Chamber Temp",f"{latest.get('sb01_temp', '--'):.1f} °C",        ">= 95 °C",     "OK" if latest.get('sb01_temp', 0) >= 95 else "LOW"],
                                    ["SB-02 Chamber Temp",f"{latest.get('sb02_temp', '--'):.1f} °C",        ">= 95 °C",     "OK" if latest.get('sb02_temp', 0) >= 95 else "LOW"],
                                    ["SB-03 Chamber Temp",f"{latest.get('sb03_temp', '--'):.1f} °C",        ">= 95 °C",     "OK" if latest.get('sb03_temp', 0) >= 95 else "LOW"],
                                    ["Steam Pressure",    f"{latest.get('pressure_bar', '--'):.2f} bar",    "2.0-3.5 bar",  "OK" if 2.0 <= latest.get('pressure_bar', 0) <= 3.5 else "CHECK"],
                                ],
                                [60, 45, 45, 35]
                            )
                            pdf.ln(5)

                        # Unit diagnostics table
                        if diag:
                            pdf.set_font('helvetica', 'B', 11)
                            pdf.cell(0, 8, "Unit Diagnostics", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                            pdf.ln(1)
                            unit_rows = []
                            comp_labels = {"heating_element": "Heating Element", "steam_generator": "Steam Generator", "pressure_valve": "Pressure Valve", "door_seal": "Door Seal"}
                            for uid, udata in diag.items():
                                for comp_key, comp_label in comp_labels.items():
                                    ok = udata.get(comp_key, False)
                                    unit_rows.append([uid.upper(), comp_label, "ACTIVE" if ok else "FAULT", "OK" if ok else "ACTION REQUIRED"])
                            render_simple_table(pdf, ["Unit", "Component", "State", "Status"], unit_rows, [30, 55, 40, 60])
                            pdf.ln(5)

                    # ── X-RAY specific sections ────────────────────────────────
                    if name == "X-Ray Inspection":
                        # Machine details
                        machine = data.get("machine", {})
                        diag    = data.get("diagnostics", {})
                        tube_h  = machine.get("tube_hours", 0)
                        tube_mx = machine.get("tube_max_hours", 10000)
                        tube_pct = round(tube_h / tube_mx * 100, 1) if tube_mx else 0

                        pdf.set_font('helvetica', 'B', 11)
                        pdf.cell(0, 8, "Machine Health", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                        pdf.ln(1)
                        render_simple_table(
                            pdf,
                            ["Parameter", "Value", "Status"],
                            [
                                ["Detection Sensitivity", f"{machine.get('sensitivity_mm', '--')} mm",  "OK"],
                                ["X-Ray Tube Hours",      f"{tube_h:,} / {tube_mx:,} hrs ({tube_pct}%)",
                                 "WARNING" if tube_pct > 80 else "OK"],
                                ["Days Since Calibration", str(machine.get("days_since_calibration", "--")) + " days",
                                 "WARNING" if machine.get("days_since_calibration", 0) > 14 else "OK"],
                                ["X-Ray Tube",            "ACTIVE" if diag.get("xray_tube") else "FAULT",
                                 "OK" if diag.get("xray_tube") else "FAULT"],
                                ["Conveyor Belt",         "ACTIVE" if diag.get("conveyor_belt") else "FAULT",
                                 "OK" if diag.get("conveyor_belt") else "FAULT"],
                                ["Detection Algorithm",   "ACTIVE" if diag.get("detection_algo") else "DEGRADED",
                                 "OK" if diag.get("detection_algo") else "WARNING"],
                                ["Reject Mechanism",      "ACTIVE" if diag.get("reject_mech") else "FAULT",
                                 "OK" if diag.get("reject_mech") else "FAULT"],
                                ["Shielding",             "INTACT" if diag.get("shielding_ok") else "CHECK",
                                 "OK" if diag.get("shielding_ok") else "WARNING"],
                            ],
                            [80, 75, 30]
                        )
                        pdf.ln(5)

                        # Reject log table
                        reject_log = data.get("reject_log", [])
                        if reject_log:
                            pdf.set_font('helvetica', 'B', 11)
                            pdf.cell(0, 8, f"Recent Reject Events  ({len(reject_log)} shown)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                            pdf.ln(1)
                            render_simple_table(
                                pdf,
                                ["Time", "Product", "Detection Type"],
                                [[r.get("time","--"), r.get("product","--"), r.get("detection_type","--")] for r in reject_log],
                                [40, 80, 65]
                            )
                            pdf.ln(5)

                    # ── CHECKWEIGHER specific sections ─────────────────────────
                    elif name == "Checkweigher":
                        spec = data.get("spec", {})

                        # Specification table
                        pdf.set_font('helvetica', 'B', 11)
                        pdf.cell(0, 8, "Weight Specification", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                        pdf.ln(1)
                        render_simple_table(
                            pdf,
                            ["Parameter", "Value"],
                            [
                                ["Target Weight",     f"{spec.get('target_g', '--')} g"],
                                ["Tolerance (±)",     f"{spec.get('tolerance_g', '--')} g"],
                                ["Lower Limit (LSL)", f"{spec.get('lower_g', '--')} g"],
                                ["Upper Limit (USL)", f"{spec.get('upper_g', '--')} g"],
                            ],
                            [100, 85]
                        )
                        pdf.ln(5)

                        # Machine diagnostics
                        diag = data.get("diagnostics", {})
                        pdf.set_font('helvetica', 'B', 11)
                        pdf.cell(0, 8, "Machine Status", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                        pdf.ln(1)
                        unit_rows = []
                        for uid, udata in diag.items():
                            cal = udata.get("last_cal_days", 0)
                            unit_rows.append([
                                uid.upper(),
                                udata.get("status", "--").upper(),
                                f"{udata.get('speed_mpm', '--')} m/min",
                                f"{udata.get('items_checked', '--'):,}",
                                f"{cal} days {'!' if cal > 10 else ''}",
                            ])
                        render_simple_table(
                            pdf,
                            ["Unit", "Status", "Conv. Speed", "Items Checked", "Last Calibration"],
                            unit_rows,
                            [22, 25, 32, 35, 35]
                        )
                        pdf.ln(5)

                        # Recent weight log
                        recent_log = data.get("recent_log", [])[:15]
                        if recent_log:
                            target_g = spec.get("target_g", 250)
                            lower_g  = spec.get("lower_g",  245)
                            upper_g  = spec.get("upper_g",  255)
                            pdf.set_font('helvetica', 'B', 11)
                            pdf.cell(0, 8, "Recent Weight Log  (last 15 items)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                            pdf.ln(1)

                            # Header
                            pdf.set_font('helvetica', 'B', 8)
                            pdf.set_fill_color(30, 41, 59); pdf.set_text_color(255)
                            for hdr, cw in [("Time",35),("Product",70),("Weight (g)",35),("Variance",35),("Result",20)]:
                                pdf.cell(cw, 9, f" {hdr}", border=1, fill=True)
                            pdf.ln(); pdf.set_text_color(0)

                            for i, r in enumerate(recent_log):
                                wt  = r.get("weight_g", target_g)
                                var = wt - target_g
                                result = "UNDER" if wt < lower_g else "OVER" if wt > upper_g else "PASS"
                                pdf.set_font('helvetica', '', 8)
                                fill = i % 2 == 0
                                pdf.set_fill_color(248,250,252) if fill else pdf.set_fill_color(255,255,255)
                                pdf.cell(35, 8, f" {r.get('time','--')}",     border=1, fill=fill)
                                pdf.cell(70, 8, f" {r.get('product','--')}",  border=1, fill=fill)
                                pdf.cell(35, 8, f" {wt:.1f} g",               border=1, fill=fill)
                                pdf.cell(35, 8, f" {var:+.1f} g",             border=1, fill=fill)
                                # Result cell — colour coded
                                if result == "PASS":
                                    pdf.set_fill_color(220,252,231); pdf.set_text_color(22,101,52)
                                elif result == "UNDER":
                                    pdf.set_fill_color(254,226,226); pdf.set_text_color(220,38,38)
                                else:
                                    pdf.set_fill_color(254,243,199); pdf.set_text_color(161,98,7)
                                pdf.cell(20, 8, f" {result}", border=1, fill=True)
                                pdf.set_text_color(0)
                                pdf.ln()
                            pdf.ln(4)

                    # ── Charts (all equipment) ─────────────────────────────────
                    charts = chart_generators[name](data)
                    for key, label in chart_labels.get(name, []):
                        chart_path = charts.get(key)
                        if chart_path:
                            temp_files.append(chart_path)
                            pdf.set_font('helvetica', 'B', 10)
                            pdf.cell(0, 7, label, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                            pdf.image(chart_path, x=10, w=190)
                            pdf.ln(3)
                except Exception as ex:
                    pdf.set_font('helvetica', 'I', 9)
                    pdf.cell(0, 7, f"Data unavailable: {ex}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        except Exception as e:
            import traceback
            print(f"PDF Kitchen Error: {e}\n{traceback.format_exc()}")
            pdf.cell(0, 10, f"Kitchen Equipment data error: {e}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # --- DOWNTIME & RELIABILITY PAGE ---
        pdf.add_page()
        pdf.set_link(lnk_downtime, page=pdf.page_no())
        pdf.set_font('helvetica', 'B', 16)
        pdf.cell(0, 10, "10. Downtime & Reliability", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font('helvetica', '', 9)
        pdf.set_text_color(100, 116, 139)
        pdf.cell(0, 5, f"Report generated: {datetime.now().strftime('%d %b %Y  %H:%M')}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(0)
        pdf.ln(3)
        pdf.set_font('helvetica', '', 11)
        pdf.multi_cell(0, 8, "Equipment failure tracking and reliability metrics for today's operational shift. "
                             "Downtime events, recovery times, MTBF, and overall uptime are summarised below.")
        pdf.ln(4)

        try:
            dt_data = generate_downtime_data()
            downtime_payload = load_downtime_overview_payload("ytd")
            downtime_summary = downtime_payload.get("summary", {})
            downtime_meta = downtime_payload.get("meta", {})

            # KPI summary row
            total_down   = sum(d["total_down"] for d in dt_data)
            total_events = sum(d["events"] for d in dt_data)
            worst        = max(dt_data, key=lambda d: d["total_down"])
            all_uptime   = [(24*60 * len(dt_data) - total_down) / (24*60 * len(dt_data)) * 100]
            mtbf_vals    = [d["mtbf"] for d in dt_data if d["events"] > 0]
            avg_mtbf     = sum(mtbf_vals) / len(mtbf_vals) if mtbf_vals else 24*60

            def fmt_dur(mins):
                h = int(mins // 60); m = int(mins % 60)
                return f"{h}h {m}m" if h > 0 else f"{m} min"

            pdf.set_font('helvetica', 'B', 12)
            pdf.cell(0, 8, "10.1  Summary KPIs", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(1)
            render_simple_table(
                pdf,
                ["Metric", "Value"],
                [
                    ["Total Downtime Year-To-Date", format_pdf_downtime_hours(downtime_summary.get("total_hours"))],
                    ["Downtime This Month", format_pdf_downtime_hours(downtime_summary.get("this_month_hours"))],
                    ["Downtime Events Year-To-Date", str(downtime_summary.get("event_count", 0))],
                    ["Highest Impact System", downtime_summary.get("highest_system") or "No downtime recorded"],
                    ["Total Downtime Today",     fmt_dur(total_down)],
                    ["Total Downtime Events",    str(total_events)],
                    ["Overall Uptime",           f"{all_uptime[0]:.1f}%"],
                    ["Avg MTBF (across systems)",fmt_dur(avg_mtbf)],
                    ["Worst Performing System",  f"{worst['name']} ({fmt_dur(worst['total_down'])})"],
                ],
                [100, 90]
            )
            pdf.ln(6)

            # Equipment Downtime Log table
            pdf.set_font('helvetica', 'B', 12)
            pdf.cell(0, 8, "10.2  Equipment Downtime Log", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(1)

            headers = ["Equipment", "Events", "Total Down", "Avg Duration", "Avg Recovery", "Uptime %", "Status"]
            col_w   = [48, 18, 28, 28, 28, 22, 18]

            pdf.set_font('helvetica', 'B', 8)
            pdf.set_fill_color(30, 41, 59)
            pdf.set_text_color(255)
            for h, w in zip(headers, col_w):
                pdf.cell(w, 10, f" {h}", border=1, fill=True)
            pdf.ln()
            pdf.set_text_color(0)

            for i, d in enumerate(dt_data):
                pdf.set_font('helvetica', '', 8)
                fill = i % 2 == 0
                pdf.set_fill_color(248, 250, 252) if fill else pdf.set_fill_color(255, 255, 255)
                row = [
                    d["name"],
                    str(d["events"]),
                    fmt_dur(d["total_down"]),
                    fmt_dur(d["avg_dur"]),
                    fmt_dur(d["avg_rec"]),
                    f"{d['uptime_pct']:.1f}%",
                    d["status"],
                ]
                for j, (val, w) in enumerate(zip(row, col_w)):
                    if j == 6:  # Status cell — colour coded
                        if d["status"] == "CRITICAL":
                            pdf.set_fill_color(254, 226, 226); pdf.set_text_color(220, 38, 38)
                        elif d["status"] == "WARNING":
                            pdf.set_fill_color(254, 243, 199); pdf.set_text_color(161, 98, 7)
                        else:
                            pdf.set_fill_color(220, 252, 231); pdf.set_text_color(22, 101, 52)
                        pdf.cell(w, 9, f" {val}", border=1, fill=True)
                        pdf.set_text_color(0)
                        pdf.set_fill_color(248, 250, 252) if fill else pdf.set_fill_color(255, 255, 255)
                    else:
                        pdf.cell(w, 9, f" {val}", border=1, fill=fill)
                pdf.ln()

            pdf.ln(6)

            # Reliability chart
            pdf.set_font('helvetica', 'B', 12)
            pdf.cell(0, 8, "10.3  System Reliability Scores", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(1)
            rel_chart = generate_downtime_reliability_chart(dt_data)
            if rel_chart:
                temp_files.append(rel_chart)
                pdf.image(rel_chart, x=10, w=190)

        except Exception as e:
            import traceback
            print(f"PDF Downtime Error: {e}\n{traceback.format_exc()}")
            pdf.cell(0, 10, f"Downtime data error: {e}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # --- FINAL EXPORT (ONLY ONCE) ---
        pdf_raw = pdf.output() 
        pdf_bytes = pdf_raw.encode('latin-1') if isinstance(pdf_raw, str) else pdf_raw

        for f in temp_files:
            if os.path.exists(f):
                os.remove(f)

        _PDF_REPORT_CACHE["signature"] = report_signature
        _PDF_REPORT_CACHE["generated_at"] = datetime.now()
        _PDF_REPORT_CACHE["bytes"] = pdf_bytes

        return make_pdf_report_response(pdf_bytes, "MISS")

    except Exception as e:
        print(f"EXPORT FAILED: {str(e)}")
        return jsonify({"error": str(e)}), 500

 
# =====================================================
# SERVER START
# =====================================================

if __name__ == "__main__":
    print("\nServer running at http://127.0.0.1:5001")
    print(f"Data directory: {DATA_DIR}\n")
    debug_enabled = os.environ.get("FLASK_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}
    app.run(debug=debug_enabled, port=5001)
