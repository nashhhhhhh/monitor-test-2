import os
import re
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd


GROUPED_MACHINE_MAPPING_FILE = "AssetList.xlsx"
GROUPED_MACHINE_MAPPING_CANDIDATES = [
    Path.home() / "Downloads" / GROUPED_MACHINE_MAPPING_FILE,
]
CRITICALITY_ORDER = [
    "Critical",
    "Semi-Critical",
    "Support Systems",
    "Facility / Non-Critical",
    "Unmapped",
]
CRITICALITY_RANK = {label: index for index, label in enumerate(CRITICALITY_ORDER, start=1)}
ASSET_ID_PATTERN = re.compile(r"([A-Z]{2,}[A-Z0-9]*-\d+)")

HIGH_MTTR_THRESHOLD_HOURS = 48.0
HIGH_DOWNTIME_THRESHOLD_HOURS = 72.0
CRITICAL_HIGH_DOWNTIME_THRESHOLD_HOURS = 120.0
REPEATED_WORK_ORDER_THRESHOLD = 3
LOW_MTBF_THRESHOLD_HOURS = 168.0
HIGH_MTBF_THRESHOLD_HOURS = 720.0

_GROUPED_MAPPING_CACHE = {"signature": None, "payload": None}
PRODUCTION_AREA_GROUPS = {
    "Producton High Risk",
    "Producton Low Risk",
    "Producton Medium Risk",
    "Production High Risk",
    "Production Low Risk",
    "Production Medium Risk",
}
GROUP_NAME_ALIASES = {
    "Bratt pan": ["bratt pan", "brattpan", "battpan", "bran pan", "round batt pan", "round bratts", "bratts pan"],
    "Check weight": ["check weight", "checkweight"],
    "X-Ray": ["x-ray", "xray"],
    "Swing Vacuum": ["swing vacuum", "swing vaccuum", "vaccuum"],
    "Combi oven": ["combi oven", "combi"],
    "Steambox": ["steam box", "steambox"],
    "Blast chiller": ["blast chill", "blast chiller"],
    "Air blast freezer": ["air blast", "blast freezer"],
    "Holding chiller": ["holding chill", "holding chill room"],
    "Conveyor": ["conveyor", "สายพาน"],
}
DESCRIPTION_MACHINE_HINTS = [
    (r"\bholding\s*chill\b", "Holding chill"),
    (r"\bassembly\b", "Assembly"),
    (r"\bcheck\s*weight\b", "Check weight"),
    (r"\bx[\s-]*ray\b", "X-Ray"),
    (r"\bsteam\s*box\b", "Steambox"),
    (r"\bbratt\.?\s*pan\s*\d*\b", "Bratt pan"),
    (r"\bround\s*bratt", "Round bratt pan"),
    (r"\bswing\s*vac", "Swing Vacuum"),
    (r"\bair\s*blast\s*\d*\b", "Air blast"),
    (r"\bblast\s*chill\s*\d*\b", "Blast chill"),
    (r"\bblast\s*freezer\s*\d*\b", "Blast freezer"),
    (r"\bcold\s*\d+\b", "Cold room"),
    (r"\bpackaging\s*store\b", "Packaging store"),
    (r"\bice\s*maker\b", "Ice maker"),
    (r"\brobot\s*coupe\b", "Robot Coupe"),
    (r"\bdice\b", "Dice machine"),
    (r"\bhood\b", "Hood"),
    (r"\bcombi\b", "Combi oven"),
    (r"\bsealer?\b", "Sealer"),
]
YEAR_START_MONTH = 1
YEAR_START_DAY = 1


def _file_signature(path):
    try:
        stat = os.stat(path)
    except OSError:
        return None
    return (stat.st_mtime_ns, stat.st_size)


def _resolve_mapping_path(data_dir):
    candidates = [Path(path) for path in GROUPED_MACHINE_MAPPING_CANDIDATES]
    candidates.append(Path(data_dir) / GROUPED_MACHINE_MAPPING_FILE)

    ordered = []
    for candidate in candidates:
        signature = _file_signature(candidate)
        if not signature:
            continue
        ordered.append((candidate, signature))
    ordered.sort(key=lambda item: item[1][0], reverse=True)
    return ordered


def _clean_text(value, fallback=""):
    text = str(value or "").replace("\ufeff", " ").strip()
    text = re.sub(r"\s+", " ", text)
    return text or fallback


def _normalize_key(value):
    return "".join(ch for ch in str(value or "").strip().lower() if ch.isalnum())


def _normalized_text(value):
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _normalize_asset_id(value):
    return _clean_text(value).upper()


def _normalize_criticality(value):
    cleaned = _clean_text(value, "Unmapped")
    normalized = _normalize_key(cleaned)
    if normalized == "critical":
        return "Critical"
    if normalized in {"semicritical", "semicriticalsystem"}:
        return "Semi-Critical"
    if normalized in {"supportsystems", "supportsystem"}:
        return "Support Systems"
    if normalized in {"facilitynoncritical", "facilitynoncriticalsystem", "noncritical", "facility"}:
        return "Facility / Non-Critical"
    return cleaned


def _is_production_area_group(value):
    return _normalize_key(value) in {
        "productonhighrisk",
        "productonlowrisk",
        "productonmediumrisk",
        "productionhighrisk",
        "productionlowrisk",
        "productionmediumrisk",
    }


def _extract_asset_ids(value):
    matches = []
    for match in ASSET_ID_PATTERN.findall(str(value or "").upper()):
        if match not in matches:
            matches.append(match)
    return matches


def _extract_asset_entries(value, machine_group):
    entries = []
    seen = set()
    for raw_line in str(value or "").splitlines():
        line = _clean_text(raw_line)
        if not line:
            continue
        asset_ids = _extract_asset_ids(line)
        if not asset_ids:
            continue
        label_part = line.split(":", 1)[0].strip() if ":" in line else ""
        for asset_id in asset_ids:
            if asset_id in seen:
                continue
            seen.add(asset_id)
            display_name = f"{machine_group} {label_part}".strip() if label_part else machine_group
            entries.append({
                "asset_id": asset_id,
                "asset_label": label_part or asset_id,
                "asset_display_name": display_name,
            })
    return entries


def _build_group_aliases(machine_group):
    aliases = {
        _normalized_text(machine_group),
        _normalize_key(machine_group),
    }
    for alias in GROUP_NAME_ALIASES.get(machine_group, []):
        aliases.add(_normalized_text(alias))
        aliases.add(_normalize_key(alias))
    return sorted({alias for alias in aliases if alias}, key=len, reverse=True)


def _parse_timestamp(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.to_pydatetime()


def _normalize_status(value):
    return _clean_text(value).lower()


def _is_unresolved_status(value):
    normalized = _normalize_status(value)
    if not normalized:
        return False
    resolved_states = {
        "finished",
        "closed",
        "completed",
        "complete",
        "resolved",
        "done",
        "cancelled",
        "canceled",
        "rejected",
    }
    return normalized not in resolved_states


def _is_mtbf_eligible_status(value):
    normalized = _normalize_status(value)
    if not normalized:
        return True
    invalid_states = {
        "open",
        "pending",
        "cancelled",
        "canceled",
        "rejected",
        "reject",
        "draft",
    }
    return normalized not in invalid_states


def _infer_criticality(asset_id, machine_name, location, job_trade, description):
    haystack = " ".join([asset_id, machine_name, location, job_trade, description]).lower()
    critical_keywords = [
        "production", "fryer", "oven", "bratt", "bowl cutter", "chopper", "conveyor",
        "steambox", "x-ray", "check weight", "vacuum", "meatball", "strap", "sealer", "sbf",
    ]
    semi_keywords = [
        "water", "cool", "refriger", "evap", "condenc", "condens", "hvac", "boiler", "compressor",
        "pump", "tank", "filter",
    ]
    support_keywords = [
        "lighting", "cctv", "alarm", "distribution board", "transformer", "monitor", "electrical",
        "hood", "lpg", "vaporizer", "uv machine",
    ]
    if any(keyword in haystack for keyword in critical_keywords):
        return "Critical"
    if any(keyword in haystack for keyword in semi_keywords):
        return "Semi-Critical"
    if any(keyword in haystack for keyword in support_keywords):
        return "Support Systems"
    return "Facility / Non-Critical"


def _infer_group_from_description(description, mapping):
    description_text = _normalized_text(description)
    description_key = _normalize_key(description)
    if not description_text and not description_key:
        return None

    for matcher in mapping.get("group_matchers", []):
        for alias in matcher.get("aliases", []):
            if not alias:
                continue
            if (" " in alias and alias in description_text) or (" " not in alias and alias in description_key):
                return matcher
    return None


def _extract_machine_hint_from_description(description):
    description_text = _normalized_text(description)
    if not description_text:
        return ""
    for pattern, label in DESCRIPTION_MACHINE_HINTS:
        if re.search(pattern, description_text, flags=re.IGNORECASE):
            return label
    return ""


def _build_fallback_mapping(asset_id, machine_name, location, job_trade, description):
    display_name = _clean_text(machine_name) or _clean_text(asset_id) or "Unmapped Asset"
    normalized_location = _clean_text(location, "Unassigned")
    criticality = _infer_criticality(asset_id, machine_name, location, job_trade, description)
    return {
        "asset_id": _normalize_asset_id(asset_id) or _clean_text(asset_id),
        "machine_group": display_name,
        "machine_name_display": display_name,
        "asset_label": _clean_text(asset_id),
        "asset_display_name": display_name,
        "location": normalized_location,
        "building": normalized_location,
        "criticality": criticality,
        "criticality_rank": CRITICALITY_RANK.get(criticality, CRITICALITY_RANK["Unmapped"]),
        "mapping_source": "fallback",
        "group_asset_ids": [_normalize_asset_id(asset_id)] if _normalize_asset_id(asset_id) else [],
    }


def load_grouped_machine_mapping(data_dir):
    resolved_candidates = _resolve_mapping_path(data_dir)
    top_path, top_signature = resolved_candidates[0] if resolved_candidates else (None, None)
    if top_signature and _GROUPED_MAPPING_CACHE["signature"] == top_signature and _GROUPED_MAPPING_CACHE["payload"] is not None:
        return _GROUPED_MAPPING_CACHE["payload"]

    payload = {
        "available": False,
        "path": str(top_path) if top_path else str(Path(data_dir) / GROUPED_MACHINE_MAPPING_FILE),
        "last_synced": None,
        "asset_map": {},
        "groups": [],
        "message": "Grouped machine criticality mapping not found.",
    }
    if not resolved_candidates:
        _GROUPED_MAPPING_CACHE["signature"] = None
        _GROUPED_MAPPING_CACHE["payload"] = payload
        return payload

    df = None
    resolved_path = None
    signature = None
    read_errors = []
    for candidate_path, candidate_signature in resolved_candidates:
        try:
            df = pd.read_excel(candidate_path)
            resolved_path = candidate_path
            signature = candidate_signature
            break
        except Exception as exc:
            read_errors.append(f"{candidate_path}: {exc}")

    if df is None or resolved_path is None or signature is None:
        payload["message"] = "Grouped machine criticality mapping could not be read."
        if read_errors:
            payload["read_errors"] = read_errors
        _GROUPED_MAPPING_CACHE["signature"] = None
        _GROUPED_MAPPING_CACHE["payload"] = payload
        return payload

    df.columns = [_clean_text(column) for column in df.columns]

    asset_map = {}
    groups = []
    group_matchers = []
    for _, row in df.iterrows():
        machine_group = _clean_text(row.get("Machine name"))
        asset_entries = _extract_asset_entries(row.get("AssetID"), machine_group)
        if len(asset_entries) == 1:
            asset_entries[0]["asset_display_name"] = machine_group
        asset_ids = [entry["asset_id"] for entry in asset_entries]
        if not machine_group or not asset_entries:
            continue

        location = _clean_text(row.get("Location"), "Unassigned")
        criticality = _normalize_criticality(row.get("Criticality"))
        if _is_production_area_group(machine_group):
            criticality = "Critical"
        group_row = {
            "machine_group": machine_group,
            "machine_name_display": machine_group,
            "location": location,
            "building": location,
            "criticality": criticality,
            "criticality_rank": CRITICALITY_RANK.get(criticality, CRITICALITY_RANK["Unmapped"]),
            "asset_ids": asset_ids,
            "asset_entries": asset_entries,
        }
        groups.append(group_row)
        group_matchers.append(
            {
                "machine_group": machine_group,
                "machine_name_display": machine_group,
                "location": location,
                "building": location,
                "criticality": criticality,
                "criticality_rank": group_row["criticality_rank"],
                "aliases": _build_group_aliases(machine_group),
            }
        )
        for entry in asset_entries:
            asset_id = entry["asset_id"]
            asset_map[asset_id] = {
                "asset_id": asset_id,
                "machine_group": machine_group,
                "machine_name_display": machine_group,
                "asset_label": entry["asset_label"],
                "asset_display_name": entry["asset_display_name"],
                "location": location,
                "building": location,
                "criticality": criticality,
                "criticality_rank": group_row["criticality_rank"],
                "mapping_source": "AssetList.xlsx",
                "group_asset_ids": asset_ids,
            }

    payload = {
        "available": True,
        "path": str(resolved_path),
        "last_synced": datetime.fromtimestamp(os.path.getmtime(resolved_path)).isoformat(),
        "asset_map": asset_map,
        "groups": groups,
        "group_matchers": sorted(group_matchers, key=lambda item: max((len(alias) for alias in item["aliases"]), default=0), reverse=True),
        "message": "Grouped machine criticality mapping loaded.",
    }
    _GROUPED_MAPPING_CACHE["signature"] = signature
    _GROUPED_MAPPING_CACHE["payload"] = payload
    return payload


def enrich_work_order_records(records, data_dir):
    mapping = load_grouped_machine_mapping(data_dir)
    asset_map = mapping.get("asset_map", {})
    enriched = []
    for row in records or []:
        asset_id = _normalize_asset_id(row.get("asset_id") or row.get("machine_code"))
        machine_name = _clean_text(row.get("raw_machine_name") or row.get("machine_name"))
        location = _clean_text(row.get("raw_location") or row.get("area"), "Unassigned")
        job_trade = _clean_text(row.get("job_trade") or row.get("system"))
        description = _clean_text(row.get("remarks") or row.get("description"))
        mapped = asset_map.get(asset_id) if asset_id else None
        if not mapped:
            mapped = _build_fallback_mapping(asset_id, machine_name, location, job_trade, description)

        if _is_production_area_group(mapped.get("machine_group")):
            mapped = {
                **mapped,
                "criticality": "Critical",
                "criticality_rank": CRITICALITY_RANK["Critical"],
            }
            description_hint = _extract_machine_hint_from_description(description)
            if description_hint:
                mapped = {
                    **mapped,
                    "asset_display_name": description_hint,
                    "mapping_source": "description_hint",
                }

        merged = {
            **row,
            "asset_id": asset_id or _clean_text(row.get("asset_id") or row.get("machine_code")),
            "machine_group": mapped["machine_group"],
            "machine_name_display": mapped["machine_name_display"],
            "asset_label": mapped.get("asset_label") or asset_id or _clean_text(row.get("asset_id") or row.get("machine_code")),
            "asset_display_name": mapped.get("asset_display_name") or machine_name or mapped["machine_name_display"],
            "location": mapped["location"],
            "building": mapped["building"],
            "criticality": mapped["criticality"],
            "criticality_rank": mapped["criticality_rank"],
            "mapping_source": mapped["mapping_source"],
            "group_asset_ids": mapped["group_asset_ids"],
            "ttr_hours": round(float(row.get("duration_hours") or 0), 3) if row.get("duration_hours") is not None else None,
            "request_state": _clean_text(row.get("status")),
            "description": description,
            "job_trade": job_trade,
            "is_open": _is_unresolved_status(row.get("status")),
            "latest_event_time": row.get("end_time") or row.get("start_time"),
            "actual_start_time": row.get("maintenance_start_time") or row.get("start_time"),
            "actual_end_time": row.get("maintenance_end_time") or row.get("end_time"),
        }
        merged["machine_name"] = merged["machine_name_display"]
        merged["area"] = merged["location"]
        enriched.append(merged)
    return enriched


def _build_alert_flags(total_hours, mttr_hours, work_order_count, criticality, open_count):
    flags = []
    if total_hours >= HIGH_DOWNTIME_THRESHOLD_HOURS:
        flags.append("High downtime")
    if mttr_hours is not None and mttr_hours >= HIGH_MTTR_THRESHOLD_HOURS:
        flags.append("High MTTR")
    if work_order_count >= REPEATED_WORK_ORDER_THRESHOLD:
        flags.append("Repeated work orders")
    if criticality == "Critical" and open_count > 0:
        flags.append("Open critical issue")
    return flags


def _build_status_flag(total_hours, mttr_hours, work_order_count, criticality, open_count):
    if criticality == "Critical" and open_count > 0:
        return "critical"
    if total_hours >= CRITICAL_HIGH_DOWNTIME_THRESHOLD_HOURS:
        return "critical"
    if mttr_hours is not None and mttr_hours >= HIGH_MTTR_THRESHOLD_HOURS:
        return "warning"
    if work_order_count >= REPEATED_WORK_ORDER_THRESHOLD or total_hours >= HIGH_DOWNTIME_THRESHOLD_HOURS:
        return "warning"
    return "ok"


def _format_hours(hours):
    if hours is None:
        return None
    if hours <= 0:
        return "0 min"
    if hours < 1:
        return f"{round(hours * 60)} min"
    whole = int(hours)
    minutes = round((hours - whole) * 60)
    if minutes == 60:
        return f"{whole + 1} hr"
    if minutes > 0:
        return f"{whole} hr {minutes} min"
    return f"{whole} hr"


def _resolve_year_floor(period_start, period_end):
    reference = period_start or period_end or datetime.now()
    return reference.replace(month=YEAR_START_MONTH, day=YEAR_START_DAY, hour=0, minute=0, second=0, microsecond=0)


def _calculate_bounded_hours(row, floor_start, period_end=None):
    original_hours = float(row.get("ttr_hours") or row.get("duration_hours") or 0)
    if original_hours <= 0:
        return 0.0

    actual_start = _parse_timestamp(row.get("actual_start_time") or row.get("start_time"))
    actual_end = _parse_timestamp(row.get("actual_end_time") or row.get("end_time"))
    if actual_end is None:
        return round(original_hours, 3)
    if actual_start is None:
        actual_start = actual_end - timedelta(hours=original_hours)

    bounded_start = max(actual_start, floor_start) if floor_start else actual_start
    bounded_end = min(actual_end, period_end) if period_end else actual_end
    bounded_duration = (bounded_end - bounded_start).total_seconds() / 3600
    if bounded_duration <= 0:
        return 0.0
    return round(min(original_hours, bounded_duration), 3)


def _build_trend(rows, period_start, period_end):
    valid_rows = []
    for row in rows:
        timestamp = _parse_timestamp(row.get("end_time") or row.get("start_time"))
        if timestamp is None:
            continue
        valid_rows.append((timestamp, row))

    if not valid_rows:
        return {"labels": [], "downtime_hours": [], "work_order_counts": [], "bucket_mode": "day"}

    day_span = max((period_end - period_start).days, 0)
    if day_span >= 120:
        bucket_mode = "month"
        bucket_format = "%b %Y"
        bucket_key = lambda dt: datetime(dt.year, dt.month, 1)
    elif day_span >= 45:
        bucket_mode = "week"
        bucket_format = "%d %b"
        bucket_key = lambda dt: dt - pd.to_timedelta(dt.weekday(), unit="D")
    else:
        bucket_mode = "day"
        bucket_format = "%d %b"
        bucket_key = lambda dt: datetime(dt.year, dt.month, dt.day)

    buckets = defaultdict(lambda: {"hours": 0.0, "count": 0})
    for timestamp, row in valid_rows:
        key = bucket_key(timestamp)
        buckets[key]["hours"] += float(row.get("effective_ttr_hours") or row.get("ttr_hours") or row.get("duration_hours") or 0)
        buckets[key]["count"] += 1

    ordered_keys = sorted(buckets)
    return {
        "labels": [key.strftime(bucket_format) for key in ordered_keys],
        "downtime_hours": [round(buckets[key]["hours"], 3) for key in ordered_keys],
        "work_order_counts": [buckets[key]["count"] for key in ordered_keys],
        "bucket_mode": bucket_mode,
    }


def get_grouped_machine_mapping_meta(data_dir):
    mapping = load_grouped_machine_mapping(data_dir)
    return {
        "available": mapping.get("available", False),
        "path": mapping.get("path"),
        "last_synced": mapping.get("last_synced"),
        "group_count": len(mapping.get("groups", [])),
        "asset_count": len(mapping.get("asset_map", {})),
        "message": mapping.get("message"),
    }


def _compute_mtbf_payload(rows):
    eligible_rows = []
    for row in rows:
        actual_start = _parse_timestamp(row.get("actual_start_time"))
        actual_end = _parse_timestamp(row.get("actual_end_time"))
        if not row.get("asset_id"):
            continue
        if actual_start is None or actual_end is None:
            continue
        if actual_end <= actual_start:
            continue
        if not _is_mtbf_eligible_status(row.get("request_state")):
            continue
        eligible_rows.append(
            {
                **row,
                "_actual_start": actual_start,
                "_actual_end": actual_end,
            }
        )

    asset_rows = []
    group_rows_map = {}
    criticality_rows_map = {}
    mtbf_points = []

    rows_by_asset = defaultdict(list)
    for row in eligible_rows:
        rows_by_asset[row["asset_id"]].append(row)

    for asset_id, asset_items in rows_by_asset.items():
        asset_items.sort(key=lambda item: item["_actual_start"])
        mtbf_gaps = []
        invalid_gap_count = 0
        for prev_item, next_item in zip(asset_items, asset_items[1:]):
            gap_hours = (next_item["_actual_start"] - prev_item["_actual_end"]).total_seconds() / 3600
            if gap_hours <= 0:
                invalid_gap_count += 1
                continue
            mtbf_gaps.append(
                {
                    "gap_hours": round(gap_hours, 3),
                    "previous_work_order_id": prev_item.get("work_order_id"),
                    "next_work_order_id": next_item.get("work_order_id"),
                    "previous_end_time": prev_item.get("actual_end_time"),
                    "next_start_time": next_item.get("actual_start_time"),
                }
            )
            mtbf_points.append(
                {
                    "timestamp": next_item["_actual_start"],
                    "gap_hours": round(gap_hours, 3),
                }
            )

        total_ttr_hours = round(sum(float(item.get("effective_ttr_hours") or item.get("ttr_hours") or 0) for item in asset_items), 3)
        work_order_count = len(asset_items)
        average_mttr = round(total_ttr_hours / work_order_count, 3) if work_order_count else None
        average_mtbf = round(sum(item["gap_hours"] for item in mtbf_gaps) / len(mtbf_gaps), 3) if mtbf_gaps else None
        latest_item = max(asset_items, key=lambda item: item["_actual_end"])
        latest_gap = mtbf_gaps[-1]["gap_hours"] if mtbf_gaps else None
        repeated_failures = len(mtbf_gaps)

        if average_mtbf is None:
            reliability_status = "insufficient"
        elif average_mtbf < LOW_MTBF_THRESHOLD_HOURS or repeated_failures >= REPEATED_WORK_ORDER_THRESHOLD:
            reliability_status = "poor"
        elif average_mtbf >= HIGH_MTBF_THRESHOLD_HOURS and work_order_count <= 3:
            reliability_status = "good"
        else:
            reliability_status = "moderate"

        asset_row = {
            "asset_id": asset_id,
            "asset_name": latest_item.get("asset_display_name") or latest_item.get("machine_name") or asset_id,
            "machine_group": latest_item.get("machine_group") or latest_item.get("machine_name_display") or asset_id,
            "criticality": latest_item.get("criticality") or "Unmapped",
            "criticality_rank": latest_item.get("criticality_rank") or CRITICALITY_RANK["Unmapped"],
            "location": latest_item.get("location") or latest_item.get("building") or "Unassigned",
            "work_order_count": work_order_count,
            "average_mttr_hours": average_mttr,
            "average_mtbf_hours": average_mtbf,
            "last_failure_date": latest_item.get("actual_end_time"),
            "next_failure_gap_hours": latest_gap,
            "valid_mtbf_gap_count": len(mtbf_gaps),
            "invalid_mtbf_gap_count": invalid_gap_count,
            "reliability_status": reliability_status,
            "status_badge": {
                "poor": "critical",
                "moderate": "warning",
                "good": "ok",
                "insufficient": "offline",
            }.get(reliability_status, "offline"),
            "insight": (
                "Insufficient repeat work order data"
                if average_mtbf is None
                else (
                    "Lower reliability with repeated failures"
                    if reliability_status == "poor"
                    else ("Stable operating interval" if reliability_status == "good" else "Monitor repeat repair pattern")
                )
            ),
        }
        asset_rows.append(asset_row)

        group_key = f"{asset_row['machine_group']}__{asset_row['location']}"
        group_row = group_rows_map.setdefault(
            group_key,
            {
                "machine_group": asset_row["machine_group"],
                "location": asset_row["location"],
                "criticality": asset_row["criticality"],
                "criticality_rank": asset_row["criticality_rank"],
                "asset_count": 0,
                "work_order_count": 0,
                "total_mttr_hours": 0.0,
                "total_mtbf_hours": 0.0,
                "valid_mtbf_asset_count": 0,
            },
        )
        group_row["asset_count"] += 1
        group_row["work_order_count"] += asset_row["work_order_count"]
        group_row["total_mttr_hours"] += float(asset_row["average_mttr_hours"] or 0)
        if asset_row["average_mtbf_hours"] is not None:
            group_row["total_mtbf_hours"] += float(asset_row["average_mtbf_hours"])
            group_row["valid_mtbf_asset_count"] += 1

        crit_row = criticality_rows_map.setdefault(
            asset_row["criticality"],
            {
                "criticality": asset_row["criticality"],
                "criticality_rank": asset_row["criticality_rank"],
                "asset_count": 0,
                "work_order_count": 0,
                "total_mttr_hours": 0.0,
                "total_mtbf_hours": 0.0,
                "valid_mtbf_asset_count": 0,
            },
        )
        crit_row["asset_count"] += 1
        crit_row["work_order_count"] += asset_row["work_order_count"]
        crit_row["total_mttr_hours"] += float(asset_row["average_mttr_hours"] or 0)
        if asset_row["average_mtbf_hours"] is not None:
            crit_row["total_mtbf_hours"] += float(asset_row["average_mtbf_hours"])
            crit_row["valid_mtbf_asset_count"] += 1

    asset_rows.sort(
        key=lambda item: (
            item["criticality_rank"],
            float(item["average_mtbf_hours"]) if item["average_mtbf_hours"] is not None else float("inf"),
            -float(item["work_order_count"] or 0),
            item["asset_id"],
        )
    )

    group_rows = []
    for row in group_rows_map.values():
        row["average_mttr_hours"] = round(row["total_mttr_hours"] / row["asset_count"], 3) if row["asset_count"] else None
        row["average_mtbf_hours"] = round(row["total_mtbf_hours"] / row["valid_mtbf_asset_count"], 3) if row["valid_mtbf_asset_count"] else None
        group_rows.append(row)
    group_rows.sort(key=lambda item: (item["criticality_rank"], float(item["average_mtbf_hours"]) if item["average_mtbf_hours"] is not None else float("inf"), item["machine_group"]))

    criticality_rows = []
    for row in criticality_rows_map.values():
        row["average_mttr_hours"] = round(row["total_mttr_hours"] / row["asset_count"], 3) if row["asset_count"] else None
        row["average_mtbf_hours"] = round(row["total_mtbf_hours"] / row["valid_mtbf_asset_count"], 3) if row["valid_mtbf_asset_count"] else None
        criticality_rows.append(row)
    criticality_rows.sort(key=lambda item: item["criticality_rank"])

    mtbf_values = [row["average_mtbf_hours"] for row in asset_rows if row["average_mtbf_hours"] is not None]
    overall_average_mtbf = round(sum(mtbf_values) / len(mtbf_values), 3) if mtbf_values else None
    lowest_mtbf_asset = min((row for row in asset_rows if row["average_mtbf_hours"] is not None), key=lambda item: item["average_mtbf_hours"], default=None)
    highest_mtbf_asset = max((row for row in asset_rows if row["average_mtbf_hours"] is not None), key=lambda item: item["average_mtbf_hours"], default=None)
    repeated_failure_assets = [row for row in asset_rows if row["valid_mtbf_gap_count"] >= 1 and row["work_order_count"] >= REPEATED_WORK_ORDER_THRESHOLD]

    mtbf_points.sort(key=lambda item: item["timestamp"])
    trend = {"labels": [], "mtbf_hours": [], "pair_counts": [], "bucket_mode": "day"}
    if mtbf_points:
        overall_start = mtbf_points[0]["timestamp"]
        overall_end = mtbf_points[-1]["timestamp"]
        day_span = max((overall_end - overall_start).days, 0)
        if day_span >= 120:
            bucket_mode = "month"
            bucket_format = "%b %Y"
            bucket_key = lambda dt: datetime(dt.year, dt.month, 1)
        elif day_span >= 45:
            bucket_mode = "week"
            bucket_format = "%d %b"
            bucket_key = lambda dt: dt - pd.to_timedelta(dt.weekday(), unit="D")
        else:
            bucket_mode = "day"
            bucket_format = "%d %b"
            bucket_key = lambda dt: datetime(dt.year, dt.month, dt.day)

        buckets = defaultdict(lambda: {"hours": 0.0, "count": 0})
        for point in mtbf_points:
            key = bucket_key(point["timestamp"])
            buckets[key]["hours"] += float(point["gap_hours"])
            buckets[key]["count"] += 1
        ordered_keys = sorted(buckets)
        trend = {
            "labels": [key.strftime(bucket_format) for key in ordered_keys],
            "mtbf_hours": [round(buckets[key]["hours"] / buckets[key]["count"], 3) if buckets[key]["count"] else 0 for key in ordered_keys],
            "pair_counts": [buckets[key]["count"] for key in ordered_keys],
            "bucket_mode": bucket_mode,
        }

    return {
        "summary": {
            "overall_average_mtbf_hours": overall_average_mtbf,
            "lowest_mtbf_asset_id": lowest_mtbf_asset["asset_id"] if lowest_mtbf_asset else None,
            "lowest_mtbf_asset_name": lowest_mtbf_asset["asset_name"] if lowest_mtbf_asset else None,
            "lowest_mtbf_hours": lowest_mtbf_asset["average_mtbf_hours"] if lowest_mtbf_asset else None,
            "highest_mtbf_asset_id": highest_mtbf_asset["asset_id"] if highest_mtbf_asset else None,
            "highest_mtbf_asset_name": highest_mtbf_asset["asset_name"] if highest_mtbf_asset else None,
            "highest_mtbf_hours": highest_mtbf_asset["average_mtbf_hours"] if highest_mtbf_asset else None,
            "repeated_failure_assets": len(repeated_failure_assets),
            "assets_with_valid_mtbf": len(mtbf_values),
        },
        "criticality_rows": criticality_rows,
        "machine_group_rows": group_rows,
        "asset_rows": asset_rows,
        "trend": trend,
    }


def _build_utilities_group_row(status_events):
    if not status_events:
        return None

    asset_rows_map = {}
    total_hours = 0.0
    latest_event_time = None
    locations = set()

    for event in status_events:
        duration_hours = float(event.get("duration_hours") or 0)
        if duration_hours <= 0:
            continue
        total_hours += duration_hours
        machine_code = _clean_text(event.get("machine_code"), "UTILITY")
        machine_name = _clean_text(event.get("machine_name"), machine_code)
        location = _clean_text(event.get("area"), "Utilities")
        locations.add(location)
        event_end = _parse_timestamp(event.get("end_time") or event.get("start_time"))
        if event_end and (latest_event_time is None or event_end > latest_event_time):
            latest_event_time = event_end

        asset_row = asset_rows_map.setdefault(
            machine_code,
            {
                "asset_id": machine_code,
                "asset_label": machine_code,
                "asset_display_name": machine_name,
                "work_order_count": 0,
                "total_ttr_hours": 0.0,
                "latest_work_order_time": None,
            },
        )
        asset_row["work_order_count"] += 1
        asset_row["total_ttr_hours"] += duration_hours
        latest_asset_time = _parse_timestamp(asset_row.get("latest_work_order_time"))
        if event_end and (latest_asset_time is None or event_end > latest_asset_time):
            asset_row["latest_work_order_time"] = event_end.isoformat()

    if total_hours <= 0:
        return None

    asset_ttr_rows = []
    for asset_row in asset_rows_map.values():
        asset_row["total_ttr_hours"] = round(asset_row["total_ttr_hours"], 3)
        asset_row["mttr_hours"] = round((asset_row["total_ttr_hours"] / asset_row["work_order_count"]), 3) if asset_row["work_order_count"] else None
        asset_ttr_rows.append(asset_row)
    asset_ttr_rows.sort(key=lambda item: (-float(item["total_ttr_hours"] or 0), -float(item["mttr_hours"] or 0), item["asset_id"]))

    location_label = "Utilities"
    if len(locations) == 1:
        location_label = next(iter(locations))

    row = {
        "criticality": "Support Systems",
        "criticality_rank": CRITICALITY_RANK.get("Support Systems", CRITICALITY_RANK["Unmapped"]),
        "machine_group": "Utilities",
        "machine_name_display": "Utilities",
        "location": location_label,
        "building": location_label,
        "asset_ids": sorted(asset_rows_map),
        "asset_id_count": len(asset_rows_map),
        "work_order_count": sum(int(asset_row["work_order_count"]) for asset_row in asset_ttr_rows),
        "total_downtime_hours": round(total_hours, 3),
        "mttr_hours": round(total_hours / sum(int(asset_row["work_order_count"]) for asset_row in asset_ttr_rows), 3),
        "latest_work_order_time": latest_event_time.isoformat() if latest_event_time else None,
        "open_work_orders": 0,
        "mapping_source": "status_derived_downtime",
        "asset_ttr_rows": asset_ttr_rows,
    }
    row["alert_flags"] = _build_alert_flags(
        row["total_downtime_hours"],
        row["mttr_hours"],
        row["work_order_count"],
        row["criticality"],
        row["open_work_orders"],
    )
    row["status_flag"] = _build_status_flag(
        row["total_downtime_hours"],
        row["mttr_hours"],
        row["work_order_count"],
        row["criticality"],
        row["open_work_orders"],
    )
    return row


def build_management_downtime_payload(records, status_events, period_start, period_end, data_dir, mtbf_records=None):
    year_floor = _resolve_year_floor(period_start, period_end)
    rows = []
    for row in records or []:
        ttr_hours = pd.to_numeric(row.get("ttr_hours") or row.get("duration_hours"), errors="coerce")
        if pd.isna(ttr_hours) or float(ttr_hours) <= 0:
            continue
        prepared = {**row, "ttr_hours": round(float(ttr_hours), 3)}
        prepared["effective_ttr_hours"] = _calculate_bounded_hours(prepared, year_floor, period_end)
        rows.append(prepared)

    total_hours = round(sum(float(row["effective_ttr_hours"]) for row in rows), 3) if rows else 0.0
    work_order_count = len(rows)
    overall_mttr = round(total_hours / work_order_count, 3) if work_order_count else None

    criticality_totals = {
        label: {"criticality": label, "criticality_rank": CRITICALITY_RANK[label], "total_downtime_hours": 0.0, "work_order_count": 0, "open_work_orders": 0}
        for label in CRITICALITY_ORDER[:-1]
    }
    machine_group_map = {}
    location_map = {}

    for row in rows:
        criticality = row.get("criticality") or "Unmapped"
        criticality_row = criticality_totals.setdefault(
            criticality,
            {"criticality": criticality, "criticality_rank": CRITICALITY_RANK.get(criticality, CRITICALITY_RANK["Unmapped"]), "total_downtime_hours": 0.0, "work_order_count": 0, "open_work_orders": 0},
        )
        effective_hours = float(row.get("effective_ttr_hours") or 0)
        criticality_row["total_downtime_hours"] += effective_hours
        criticality_row["work_order_count"] += 1
        criticality_row["open_work_orders"] += 1 if row.get("is_open") else 0

        location = row.get("location") or row.get("building") or "Unassigned"
        location_key = _clean_text(location, "Unassigned")
        location_row = location_map.setdefault(
            location_key,
            {"location": location_key, "building": location_key, "total_downtime_hours": 0.0, "work_order_count": 0, "mttr_hours": None},
        )
        location_row["total_downtime_hours"] += effective_hours
        location_row["work_order_count"] += 1

        group_name = row.get("machine_group") or row.get("machine_name_display") or row.get("asset_id") or "Unmapped Asset"
        group_key = f"{group_name}__{location_key}"
        group_row = machine_group_map.setdefault(
            group_key,
            {
                "criticality": criticality,
                "criticality_rank": CRITICALITY_RANK.get(criticality, CRITICALITY_RANK["Unmapped"]),
                "machine_group": group_name,
                "machine_name_display": row.get("machine_name_display") or group_name,
                "location": location_key,
                "building": location_key,
                "asset_ids": set(),
                "work_order_count": 0,
                "total_downtime_hours": 0.0,
                "mttr_hours": None,
                "latest_work_order_time": None,
                "open_work_orders": 0,
                "mapping_source": row.get("mapping_source"),
                "asset_ttr_map": {},
            },
        )
        if row.get("asset_id"):
            group_row["asset_ids"].add(row["asset_id"])
            asset_row = group_row["asset_ttr_map"].setdefault(
                row["asset_id"],
                {
                    "asset_id": row["asset_id"],
                    "asset_label": row.get("asset_label") or row["asset_id"],
                    "asset_display_name": row.get("asset_display_name") or row.get("raw_machine_name") or row.get("machine_name_display") or row["asset_id"],
                    "work_order_count": 0,
                    "total_ttr_hours": 0.0,
                    "latest_work_order_time": None,
                },
            )
            asset_row["work_order_count"] += 1
            asset_row["total_ttr_hours"] += float(row["ttr_hours"])
            asset_event_time = _parse_timestamp(row.get("latest_event_time"))
            latest_asset_time = _parse_timestamp(asset_row.get("latest_work_order_time"))
            if asset_event_time and (latest_asset_time is None or asset_event_time > latest_asset_time):
                asset_row["latest_work_order_time"] = asset_event_time.isoformat()
        group_row["work_order_count"] += 1
        group_row["total_downtime_hours"] += effective_hours
        group_row["open_work_orders"] += 1 if row.get("is_open") else 0
        event_time = _parse_timestamp(row.get("latest_event_time"))
        latest_existing = _parse_timestamp(group_row.get("latest_work_order_time"))
        if event_time and (latest_existing is None or event_time > latest_existing):
            group_row["latest_work_order_time"] = event_time.isoformat()

    criticality_rows = []
    for row in criticality_totals.values():
        row["total_downtime_hours"] = round(row["total_downtime_hours"], 3)
        row["share_of_total_pct"] = round((row["total_downtime_hours"] / total_hours) * 100, 1) if total_hours else 0.0
        row["average_mttr_hours"] = round((row["total_downtime_hours"] / row["work_order_count"]), 3) if row["work_order_count"] else None
        criticality_rows.append(row)
    criticality_rows.sort(key=lambda item: (item["criticality_rank"], -item["total_downtime_hours"], -item["work_order_count"]))

    machine_group_rows = []
    for row in machine_group_map.values():
        row["asset_ids"] = sorted(row["asset_ids"])
        row["asset_id_count"] = len(row["asset_ids"])
        row["total_downtime_hours"] = round(row["total_downtime_hours"], 3)
        row["mttr_hours"] = round((row["total_downtime_hours"] / row["work_order_count"]), 3) if row["work_order_count"] else None
        asset_ttr_rows = []
        for asset_row in row["asset_ttr_map"].values():
            asset_row["total_ttr_hours"] = round(asset_row["total_ttr_hours"], 3)
            asset_row["mttr_hours"] = round((asset_row["total_ttr_hours"] / asset_row["work_order_count"]), 3) if asset_row["work_order_count"] else None
            asset_ttr_rows.append(asset_row)
        asset_ttr_rows.sort(key=lambda item: (-float(item["total_ttr_hours"] or 0), -float(item["mttr_hours"] or 0), item["asset_id"]))
        row["asset_ttr_rows"] = asset_ttr_rows
        del row["asset_ttr_map"]
        row["alert_flags"] = _build_alert_flags(
            row["total_downtime_hours"],
            row["mttr_hours"],
            row["work_order_count"],
            row["criticality"],
            row["open_work_orders"],
        )
        row["status_flag"] = _build_status_flag(
            row["total_downtime_hours"],
            row["mttr_hours"],
            row["work_order_count"],
            row["criticality"],
            row["open_work_orders"],
        )
        machine_group_rows.append(row)
    machine_group_rows.sort(
        key=lambda item: (
            item["criticality_rank"],
            -float(item["total_downtime_hours"] or 0),
            -float(item["mttr_hours"] or 0),
            item["machine_group"],
        )
    )

    utilities_row = _build_utilities_group_row(status_events)
    if utilities_row:
        machine_group_rows.append(utilities_row)
        machine_group_rows.sort(
            key=lambda item: (
                item["criticality_rank"],
                -float(item["total_downtime_hours"] or 0),
                -float(item["mttr_hours"] or 0),
                item["machine_group"],
            )
        )

    location_rows = []
    for row in location_map.values():
        row["total_downtime_hours"] = round(row["total_downtime_hours"], 3)
        row["mttr_hours"] = round((row["total_downtime_hours"] / row["work_order_count"]), 3) if row["work_order_count"] else None
        location_rows.append(row)
    location_rows.sort(key=lambda item: (-float(item["total_downtime_hours"] or 0), -float(item["mttr_hours"] or 0), item["location"]))

    highest_mttr_group = max(machine_group_rows, key=lambda item: float(item["mttr_hours"] or 0), default=None)
    highest_downtime_group = max(machine_group_rows, key=lambda item: float(item["total_downtime_hours"] or 0), default=None)
    most_affected_location = max(location_rows, key=lambda item: float(item["total_downtime_hours"] or 0), default=None)

    detailed_rows = []
    for row in sorted(rows, key=lambda item: (_parse_timestamp(item.get("latest_event_time")) or datetime.min), reverse=True):
        asset_id = row.get("asset_id") or ""
        detail = {
            "work_order_id": row.get("work_order_id") or "--",
            "request_id": row.get("maintenance_order_id") or "--",
            "asset_id": asset_id,
            "machine_group": row.get("machine_group") or row.get("machine_name_display") or "--",
            "machine_name": row.get("machine_name_display") or row.get("machine_group") or "--",
            "asset_display_name": row.get("asset_display_name") or row.get("raw_machine_name") or row.get("machine_name_display") or "--",
            "criticality": row.get("criticality") or "Unmapped",
            "criticality_rank": row.get("criticality_rank") or CRITICALITY_RANK["Unmapped"],
            "location": row.get("location") or row.get("building") or "Unassigned",
            "building": row.get("building") or row.get("location") or "Unassigned",
            "ttr_hours": row.get("effective_ttr_hours"),
            "original_ttr_hours": row.get("ttr_hours"),
            "request_state": row.get("request_state") or "--",
            "status_flag": "critical" if row.get("criticality") == "Critical" and row.get("is_open") else ("warning" if row.get("is_open") else "ok"),
            "is_open": bool(row.get("is_open")),
            "start_time": row.get("start_time"),
            "end_time": row.get("end_time"),
            "latest_event_time": row.get("latest_event_time"),
            "description": row.get("description") or "",
            "job_trade": row.get("job_trade") or "",
            "mapping_source": row.get("mapping_source"),
        }
        detailed_rows.append(detail)

    alerts = []
    if highest_mttr_group and float(highest_mttr_group.get("mttr_hours") or 0) >= HIGH_MTTR_THRESHOLD_HOURS:
        alerts.append(
            {
                "level": "critical",
                "message": f"{highest_mttr_group['machine_group']} has the highest MTTR at {_format_hours(highest_mttr_group['mttr_hours'])}.",
            }
        )
    if most_affected_location and float(most_affected_location.get("total_downtime_hours") or 0) >= HIGH_DOWNTIME_THRESHOLD_HOURS:
        alerts.append(
            {
                "level": "warning",
                "message": f"{most_affected_location['location']} has the highest downtime at {_format_hours(most_affected_location['total_downtime_hours'])}.",
            }
        )
    open_critical_count = sum(1 for row in detailed_rows if row["criticality"] == "Critical" and row["is_open"])
    if open_critical_count:
        alerts.append(
            {
                "level": "critical",
                "message": f"{open_critical_count} critical work order(s) are still unresolved in the selected period.",
            }
        )

    filters = {
        "criticalities": [row["criticality"] for row in criticality_rows if row["work_order_count"] > 0],
        "machine_groups": sorted({row["machine_group"] for row in machine_group_rows}),
        "locations": sorted({row["location"] for row in machine_group_rows}),
        "asset_ids": sorted({row["asset_id"] for row in detailed_rows if row["asset_id"]}),
        "statuses": sorted({row["request_state"] for row in detailed_rows if row["request_state"]}),
    }

    mtbf_payload = _compute_mtbf_payload(mtbf_records if mtbf_records is not None else rows)

    summary = {
        "total_downtime_hours": total_hours,
        "total_work_orders": work_order_count,
        "overall_mttr_hours": overall_mttr,
        "critical_downtime_hours": round(sum(row["total_downtime_hours"] for row in criticality_rows if row["criticality"] == "Critical"), 3),
        "semi_critical_downtime_hours": round(sum(row["total_downtime_hours"] for row in criticality_rows if row["criticality"] == "Semi-Critical"), 3),
        "open_work_orders": sum(1 for row in detailed_rows if row["is_open"]),
        "highest_mttr_machine_group": highest_mttr_group["machine_group"] if highest_mttr_group else None,
        "highest_mttr_hours": highest_mttr_group["mttr_hours"] if highest_mttr_group else None,
        "highest_mttr_location": highest_mttr_group["location"] if highest_mttr_group else None,
        "highest_downtime_machine_group": highest_downtime_group["machine_group"] if highest_downtime_group else None,
        "highest_downtime_hours": highest_downtime_group["total_downtime_hours"] if highest_downtime_group else None,
        "highest_downtime_location": highest_downtime_group["location"] if highest_downtime_group else None,
        "most_affected_location": most_affected_location["location"] if most_affected_location else None,
        "most_affected_location_hours": most_affected_location["total_downtime_hours"] if most_affected_location else None,
        "critical_machine_groups_with_repeats": sum(
            1 for row in machine_group_rows if row["criticality"] == "Critical" and row["work_order_count"] >= REPEATED_WORK_ORDER_THRESHOLD
        ),
    }

    return {
        "summary": summary,
        "mtbf": mtbf_payload,
        "criticality_rows": criticality_rows,
        "machine_group_rows": machine_group_rows,
        "location_rows": location_rows,
        "trend": _build_trend(detailed_rows, period_start, period_end),
        "work_orders": detailed_rows,
        "filters": filters,
        "alerts": alerts,
        "mapping_meta": get_grouped_machine_mapping_meta(data_dir),
    }
