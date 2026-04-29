from __future__ import annotations

import math
import os
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import pandas as pd

from downtime_management import load_grouped_machine_mapping
from maintenance_service import MONTH_LABELS, build_equipment_dataset, clean_text


DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
D365_SPARE_PARTS_PATH = Path(
    os.environ.get(
        "SPARE_PARTS_D365_PATH",
        str(DEFAULT_DATA_DIR / "DynamicsExport_complete_final.xlsx"),
    )
)
GEN_PO_SPARE_PARTS_PATH = Path(
    os.environ.get(
        "SPARE_PARTS_GEN_PO_PATH",
        str(DEFAULT_DATA_DIR / "Gen_PO_translated_fully_clean.xlsx"),
    )
)

PART_INCLUDE_KEYWORDS = (
    "part",
    "spare",
    "valve",
    "gauge",
    "sensor",
    "switch",
    "motor",
    "pump",
    "compressor",
    "fan",
    "belt",
    "bearing",
    "seal",
    "lamp",
    "cable",
    "fitting",
    "connector",
    "refrigerant",
    "oil",
    "filter",
    "thermostat",
    "transmitter",
    "dryer",
    "axial",
    "pressure",
    "copper",
)
PART_EXCLUDE_KEYWORDS = (
    "labour",
    "labor",
    "service charge",
    "rag",
    "sign",
    "sticker",
    "cleaning",
    "civil",
    "cevil",
    "job",
)
_SPARE_PARTS_CACHE: dict[tuple, dict] = {}


def _file_signature(path: Path | None):
    if not path:
        return None
    try:
        stat = path.stat()
    except OSError:
        return None
    return (str(path), stat.st_mtime_ns, stat.st_size)


def _normalize_key(value: str | None) -> str:
    return "".join(ch for ch in str(value or "").lower() if ch.isalnum())


def _normalize_phrase(value: str | None) -> str:
    cleaned = clean_text(value) or ""
    cleaned = cleaned.lower()
    cleaned = re.sub(r"[^a-z0-9\s/-]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _clean_numeric(value):
    numeric = pd.to_numeric(value, errors="coerce")
    if pd.isna(numeric):
        return None
    number = float(numeric)
    if math.isclose(number, round(number)):
        return int(round(number))
    return round(number, 3)


def _parse_date(value):
    parsed = pd.to_datetime(value, errors="coerce", dayfirst=False)
    if pd.isna(parsed):
        return None
    return parsed.to_pydatetime()


def _normalize_part_name(value: str | None) -> str:
    phrase = _normalize_phrase(value)
    if not phrase:
        return ""
    phrase = re.sub(r"\b(model|size|color|grade|installed|use|for|the|and)\b", " ", phrase)
    phrase = re.sub(r"\s+", " ", phrase).strip()
    return phrase


def _row_has_any_content(row, columns) -> bool:
    return any(clean_text(row.get(column)) for column in columns)


def _has_pd_machine_reference(value: str | None) -> bool:
    return bool(_normalize_phrase(value))


def _is_relevant_inventory_row(row) -> bool:
    item_group = _normalize_phrase(row.get("Item Group"))
    if item_group != "spare":
        return False
    quantity = _clean_numeric(row.get("Available physical"))
    return quantity is not None and quantity > 0


def _is_relevant_external_row(row) -> bool:
    text = " ".join(
        filter(
            None,
            [
                _normalize_phrase(row.get("Type of cost")),
                _normalize_phrase(row.get("Group of cost")),
                _normalize_phrase(row.get("PD Machine")),
                _normalize_phrase(row.get("Description")),
                _normalize_phrase(row.get("Note")),
            ],
        )
    )
    if not text:
        return False
    if any(keyword in text for keyword in PART_EXCLUDE_KEYWORDS):
        return False
    if any(keyword in text for keyword in PART_INCLUDE_KEYWORDS):
        return True
    return "machine" in text or "cooling" in text or "electrical" in text or "mechanical" in text


def _build_equipment_candidates(data_dir: str):
    equipment_dataset = build_equipment_dataset()
    mapping = load_grouped_machine_mapping(data_dir)

    candidates = {}
    for asset in equipment_dataset.get("assets", []):
        asset_code = clean_text(asset.get("asset_code"))
        asset_name = clean_text(asset.get("asset_name"))
        machine_group = clean_text(asset.get("subcategory") or asset.get("category") or asset_name)
        if not asset_name:
            continue
        key = asset_code or asset_name
        candidates[key] = {
            "asset_id": asset_code,
            "equipment_name": asset_name,
            "machine_group": machine_group or asset_name,
            "location": clean_text(asset.get("location_display")) or machine_group or "Unknown",
            "criticality": clean_text(asset.get("criticality")) or "Standard",
            "aliases": {
                _normalize_phrase(asset_name),
                _normalize_phrase(machine_group),
                _normalize_key(asset_name),
                _normalize_key(machine_group),
            },
        }

    for group in mapping.get("groups", []):
        group_name = clean_text(group.get("machine_group"))
        if not group_name:
            continue
        asset_ids = group.get("asset_ids") or []
        primary_asset = asset_ids[0] if asset_ids else None
        key = primary_asset or group_name
        existing = candidates.get(key, {})
        aliases = set(existing.get("aliases", set()))
        aliases.update({
            _normalize_phrase(group_name),
            _normalize_key(group_name),
        })
        candidates[key] = {
            "asset_id": existing.get("asset_id") or primary_asset,
            "equipment_name": existing.get("equipment_name") or group_name,
            "machine_group": existing.get("machine_group") or group_name,
            "location": existing.get("location") or clean_text(group.get("location")) or "Unknown",
            "criticality": clean_text(group.get("criticality")) or existing.get("criticality") or "Standard",
            "aliases": aliases,
        }

    candidate_rows = []
    for candidate in candidates.values():
        aliases = sorted({alias for alias in candidate["aliases"] if alias}, key=len, reverse=True)
        if not aliases:
            continue
        candidate_rows.append({**candidate, "aliases": aliases})
    candidate_rows.sort(key=lambda item: max(len(alias) for alias in item["aliases"]), reverse=True)
    return candidate_rows


def _link_equipment(record, candidates):
    text_fields = [
        clean_text(record.get("asset_id")),
        clean_text(record.get("equipment_name")),
        clean_text(record.get("item_description")),
        clean_text(record.get("raw_description")),
        clean_text(record.get("machine_hint")),
        clean_text(record.get("remarks")),
    ]
    joined_text = " ".join(filter(None, text_fields))
    phrase = _normalize_phrase(joined_text)
    compact = _normalize_key(joined_text)

    for candidate in candidates:
        asset_id = clean_text(candidate.get("asset_id"))
        if asset_id and asset_id.lower() in joined_text.lower():
                return {
                    "linked_equipment_name": candidate["equipment_name"],
                    "linked_asset_id": asset_id,
                    "linked_machine_group": candidate["machine_group"],
                    "linked_criticality": candidate.get("criticality") or "Standard",
                    "link_confidence": "Exact Asset ID",
                    "unlinked_flag": False,
                }

    for candidate in candidates:
        for alias in candidate["aliases"]:
            if len(alias) < 5:
                continue
            if (" " in alias and alias in phrase) or (" " not in alias and alias in compact):
                confidence = "Exact Name" if alias == _normalize_phrase(candidate["equipment_name"]) else "Machine Group Match"
                return {
                    "linked_equipment_name": candidate["equipment_name"],
                    "linked_asset_id": candidate.get("asset_id"),
                    "linked_machine_group": candidate["machine_group"],
                    "linked_criticality": candidate.get("criticality") or "Standard",
                    "link_confidence": confidence,
                    "unlinked_flag": False,
                }

    return {
        "linked_equipment_name": None,
        "linked_asset_id": None,
        "linked_machine_group": None,
        "linked_criticality": None,
        "link_confidence": "Unlinked / Review Needed",
        "unlinked_flag": True,
    }


def _classify_record(record) -> str | None:
    if record.get("source_type") == "Inventory":
        return "Planned"

    if _has_pd_machine_reference(record.get("machine_hint")):
        return "Urgent"
    return None


def _build_trend(records):
    dated = [row for row in records if row.get("date")]
    if not dated:
        return {"labels": [], "planned_counts": [], "urgent_counts": []}

    buckets = defaultdict(lambda: {"Planned": 0, "Urgent": 0})
    for row in dated:
        dt = _parse_date(row.get("date"))
        if not dt:
            continue
        if row.get("urgency_type") not in {"Planned", "Urgent"}:
            continue
        key = f"{dt.year}-{dt.month:02d}"
        buckets[key][row.get("urgency_type") or "Planned"] += 1

    ordered = sorted(buckets)
    return {
        "labels": [
            f"{MONTH_LABELS[int(key.split('-')[1]) - 1]} {key.split('-')[0]}"
            for key in ordered
        ],
        "planned_counts": [buckets[key]["Planned"] for key in ordered],
        "urgent_counts": [buckets[key]["Urgent"] for key in ordered],
    }


def _build_filter_options(records):
    urgency_types = [value for value in ("Planned", "Urgent") if any(row.get("urgency_type") == value for row in records)]
    return {
        "source_types": sorted({row["source_type"] for row in records}),
        "urgency_types": urgency_types,
        "equipment_names": sorted({row["linked_equipment_name"] for row in records if row.get("linked_equipment_name")}),
        "asset_ids": sorted({row["linked_asset_id"] for row in records if row.get("linked_asset_id")}),
        "vendors": sorted({row["supplier_vendor"] for row in records if row.get("supplier_vendor")}),
        "link_states": [
            {"value": "all", "label": "All"},
            {"value": "linked", "label": "Linked"},
            {"value": "unlinked", "label": "Unlinked"},
        ],
    }


def build_spare_parts_payload():
    cache_signature = (_file_signature(D365_SPARE_PARTS_PATH), _file_signature(GEN_PO_SPARE_PARTS_PATH))
    cached = _SPARE_PARTS_CACHE.get(cache_signature)
    if cached:
        return cached

    records = []
    source_errors = []
    inventory_part_count = 0
    external_part_count = 0
    external_purchase_value_total = 0.0
    data_dir = str(Path(__file__).resolve().parent.parent / "data")
    equipment_candidates = _build_equipment_candidates(data_dir)

    if D365_SPARE_PARTS_PATH.exists():
        try:
            frame = pd.read_excel(D365_SPARE_PARTS_PATH)
            for _, row in frame.iterrows():
                if not _is_relevant_inventory_row(row):
                    continue
                inventory_part_count += 1
                item_description = clean_text(row.get("Product name")) or clean_text(row.get("Search name"))
                record = {
                    "source_type": "Inventory",
                    "item_description": item_description,
                    "normalized_part_name": _normalize_part_name(item_description or row.get("Search name")),
                    "quantity": _clean_numeric(row.get("Available physical")),
                    "unit": clean_text(row.get("Unit of measure")) or clean_text(row.get("Inventory unit")),
                    "date": None,
                    "work_order_id": None,
                    "request_id": None,
                    "po_id": None,
                    "equipment_name": None,
                    "asset_id": clean_text(row.get("Product identification")) if re.search(r"[A-Z]{2,}[A-Z0-9]*-\d+", str(row.get("Product identification") or "")) else None,
                    "equipment_group": None,
                    "supplier_vendor": clean_text(row.get("Vendor Name")),
                    "cost_value": None,
                    "raw_source_reference": clean_text(row.get("Item number")),
                    "raw_description": clean_text(row.get("Search name")) or item_description,
                    "machine_hint": None,
                    "remarks": clean_text(row.get("Item Group")),
                }
                record.update(_link_equipment(record, equipment_candidates))
                record["urgency_type"] = _classify_record(record)
                records.append(record)
        except Exception as exc:
            source_errors.append(f"D365 inventory: {exc}")
    else:
        source_errors.append(f"Missing source file: {D365_SPARE_PARTS_PATH}")

    if GEN_PO_SPARE_PARTS_PATH.exists():
        try:
            frame = pd.read_excel(GEN_PO_SPARE_PARTS_PATH)
            for _, row in frame.iterrows():
                if _row_has_any_content(
                    row,
                    ["Description", "PO No.", "PR No.", "CPP No.", "Vendor name", "PD Machine", "Group of cost", "Type of cost"],
                ):
                    external_part_count += 1
                if not _is_relevant_external_row(row):
                    continue
                description = clean_text(row.get("Description"))
                machine_hint = clean_text(row.get("PD Machine"))
                note = clean_text(row.get("Note"))
                group_cost = clean_text(row.get("Group of cost"))
                date_value = (
                    _parse_date(row.get("Date Gen PO"))
                    or _parse_date(row.get("DMY Create(EN) CPP"))
                    or _parse_date(row.get("DMY Create PR"))
                )
                record = {
                    "source_type": "External Purchase",
                    "item_description": description,
                    "normalized_part_name": _normalize_part_name(description),
                    "quantity": _clean_numeric(row.get("Qty'")),
                    "unit": clean_text(row.get("Unit")),
                    "date": date_value.isoformat() if date_value else None,
                    "work_order_id": clean_text(row.get("PR No.")),
                    "request_id": clean_text(row.get("CPP No.")),
                    "po_id": clean_text(row.get("PO No.")),
                    "equipment_name": machine_hint,
                    "asset_id": clean_text(row.get("PD Machine")) if re.search(r"[A-Z]{2,}[A-Z0-9]*-\d+", str(row.get("PD Machine") or "")) else None,
                    "equipment_group": group_cost,
                    "supplier_vendor": clean_text(row.get("Vendor name")),
                    "cost_value": _clean_numeric(row.get("Total price")),
                    "raw_source_reference": clean_text(row.get("PO No.")) or clean_text(row.get("PR No.")),
                    "raw_description": description,
                    "machine_hint": machine_hint,
                    "remarks": note,
                }
                external_purchase_value_total += float(record.get("cost_value") or 0)
                record.update(_link_equipment(record, equipment_candidates))
                record["urgency_type"] = _classify_record(record)
                if record["urgency_type"] != "Urgent":
                    continue
                records.append(record)
        except Exception as exc:
            source_errors.append(f"Gen PO: {exc}")
    else:
        source_errors.append(f"Missing source file: {GEN_PO_SPARE_PARTS_PATH}")

    equipment_usage = defaultdict(lambda: {"record_count": 0, "urgent_count": 0, "planned_count": 0, "inventory_count": 0, "external_count": 0, "part_names": Counter(), "last_date": None})
    unlinked_rows = []
    for row in records:
        if row.get("unlinked_flag"):
            unlinked_rows.append(
                {
                    "raw_description": row.get("raw_description") or row.get("item_description") or "-",
                    "source_type": row.get("source_type"),
                    "possible_equipment_match": row.get("machine_hint") or "-",
                    "link_confidence": row.get("link_confidence"),
                }
            )
            continue
        equipment_name = row.get("linked_equipment_name") or "Unknown"
        usage = equipment_usage[equipment_name]
        usage["record_count"] += 1
        usage["urgent_count"] += 1 if row.get("urgency_type") == "Urgent" else 0
        usage["planned_count"] += 1 if row.get("urgency_type") == "Planned" else 0
        usage["inventory_count"] += 1 if row.get("source_type") == "Inventory" else 0
        usage["external_count"] += 1 if row.get("source_type") == "External Purchase" else 0
        if row.get("normalized_part_name"):
            usage["part_names"][row["normalized_part_name"]] += 1
        if row.get("date") and (usage["last_date"] is None or row["date"] > usage["last_date"]):
            usage["last_date"] = row["date"]

    equipment_rows = []
    for equipment_name, usage in equipment_usage.items():
        top_parts = [name for name, _ in usage["part_names"].most_common(3)]
        equipment_rows.append(
            {
                "equipment_name": equipment_name,
                "linked_asset_id": next((row.get("linked_asset_id") for row in records if row.get("linked_equipment_name") == equipment_name and row.get("linked_asset_id")), None),
                "machine_group": next((row.get("linked_machine_group") for row in records if row.get("linked_equipment_name") == equipment_name and row.get("linked_machine_group")), None),
                "record_count": usage["record_count"],
                "urgent_count": usage["urgent_count"],
                "planned_count": usage["planned_count"],
                "inventory_count": usage["inventory_count"],
                "external_count": usage["external_count"],
                "part_names": top_parts,
                "last_date": usage["last_date"],
            }
        )
    equipment_rows.sort(key=lambda row: (-row["urgent_count"], -row["record_count"], row["equipment_name"]))

    planned_count = sum(1 for row in records if row.get("urgency_type") == "Planned")
    urgent_count = sum(1 for row in records if row.get("urgency_type") == "Urgent")
    inventory_count = inventory_part_count
    external_count = external_part_count
    linked_equipment_count = len({row.get("linked_equipment_name") for row in records if row.get("linked_equipment_name")})
    total_external_purchase_value = round(external_purchase_value_total, 2)
    top_equipment = equipment_rows[0]["equipment_name"] if equipment_rows else None

    external_part_counter = Counter(row.get("normalized_part_name") or row.get("item_description") for row in records if row.get("source_type") == "External Purchase")
    urgent_part_counter = Counter(row.get("normalized_part_name") or row.get("item_description") for row in records if row.get("urgency_type") == "Urgent")
    trend = _build_trend(records)

    classified_total = planned_count + urgent_count
    payload = {
        "meta": {
            "last_synced": max(
                [timestamp for timestamp in [
                    datetime.fromtimestamp(D365_SPARE_PARTS_PATH.stat().st_mtime).isoformat() if D365_SPARE_PARTS_PATH.exists() else None,
                    datetime.fromtimestamp(GEN_PO_SPARE_PARTS_PATH.stat().st_mtime).isoformat() if GEN_PO_SPARE_PARTS_PATH.exists() else None,
                ] if timestamp],
                default=None,
            ),
            "source_paths": [str(D365_SPARE_PARTS_PATH), str(GEN_PO_SPARE_PARTS_PATH)],
            "errors": source_errors,
        },
        "summary": {
            "total_records": len(records),
            "planned_count": planned_count,
            "urgent_count": urgent_count,
            "inventory_count": inventory_count,
            "external_count": external_count,
            "linked_equipment_count": linked_equipment_count,
            "unlinked_count": len(unlinked_rows),
            "top_equipment_name": top_equipment,
            "top_equipment_usage_count": equipment_rows[0]["record_count"] if equipment_rows else 0,
            "total_external_purchase_value": total_external_purchase_value,
        },
        "planned_vs_urgent": {
            "planned_count": planned_count,
            "urgent_count": urgent_count,
            "planned_pct": round((planned_count / classified_total) * 100, 1) if classified_total else 0,
            "urgent_pct": round((urgent_count / classified_total) * 100, 1) if classified_total else 0,
            "trend": trend,
        },
        "source_split": {
            "inventory": {
                "count": inventory_count,
                "part_count": inventory_count,
                "quantity": inventory_count,
                "value": None,
            },
            "external_purchase": {
                "count": external_count,
                "part_count": external_count,
                "quantity": external_count,
                "value": total_external_purchase_value,
            },
        },
        "equipment_rows": equipment_rows,
        "top_external_parts": [
            {"part_name": name, "count": count}
            for name, count in external_part_counter.most_common(10)
            if name
        ],
        "top_urgent_parts": [
            {"part_name": name, "count": count}
            for name, count in urgent_part_counter.most_common(10)
            if name
        ],
        "records": sorted(records, key=lambda row: (row.get("urgency_type") != "Urgent", -(int(bool(row.get("date")))), row.get("date") or "", row.get("item_description") or ""), reverse=False),
        "unlinked_rows": unlinked_rows[:100],
        "filter_options": _build_filter_options(records),
        "matching_rules": {
            "urgency": "Adjust _classify_record() and _has_pd_machine_reference() in backend/spare_parts_service.py",
            "part_filter": "Adjust _is_relevant_inventory_row() and _is_relevant_external_row() in backend/spare_parts_service.py",
            "equipment_linking": "Adjust _build_equipment_candidates() and _link_equipment() in backend/spare_parts_service.py",
        },
    }
    _SPARE_PARTS_CACHE.clear()
    _SPARE_PARTS_CACHE[cache_signature] = payload
    return payload
