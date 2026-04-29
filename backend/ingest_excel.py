import re
import sqlite3
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR.parent / "data"
DB_FILE = BASE_DIR / "temps.db"
SOURCE_FILES = [
    DATA_DIR / "20251124_20260327_HR-ZONE.csv",
    DATA_DIR / "20251124_20260327_IW-ZONE.csv",
    DATA_DIR / "20251124_20260327_LR-ZONE.csv",
]
SOURCE_ENCODINGS = ["utf-8-sig", "utf-16", "latin-1", "cp1252"]
SUPPLEMENTAL_ROOMS = {
    "IW18": {"base_room": "L:02", "room_name": "BATTERY CHARGING (IW18)"},
    "IW-CLOAK": {"base_room": "L:19", "room_name": "CLOAK ROOM (IW-CLOAK)"},
    "LR-STAFF-ACCESS": {"base_room": "L:32", "room_name": "STAFF ACCESS LR AREA (LR-STAFF-ACCESS)"},
    "LR-WAR-RM": {"base_room": "L:49", "room_name": "LR WAR RM (LR-WAR-RM)"},
    "OW5/1-2": {"base_room": "M:02", "room_name": "OUTGOING WAREHOUSE (OW5/1-2)"},
    "OW7": {"base_room": "M:04", "room_name": "CLOAK ROOM (OW7)"},
}

ROOM_CODE_RE = re.compile(r"\(([^)]+)\)")
HEADER_RE = re.compile(r"^(?P<label>.+?) \((?P<code>[^)]+)\)(?: (?P<suffix>.*))?$")


def normalize_room_code(value):
    if value is None:
        return None
    text = str(value).strip().upper()
    return re.sub(r"[^A-Z0-9/:-]", "", text)


def extract_room_code(value):
    if value is None:
        return None
    match = ROOM_CODE_RE.search(str(value))
    return normalize_room_code(match.group(1)) if match else None


def load_existing_room_map():
    if not DB_FILE.exists():
        return {}

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT base_room, room_name FROM room_temperature").fetchall()
    finally:
        conn.close()

    room_map = {}
    for row in rows:
        room_name = row["room_name"]
        room_code = extract_room_code(room_name)
        if not room_code:
            continue
        room_map[room_code] = {
            "base_room": row["base_room"],
            "room_name": room_name,
        }
    for room_code, mapping in SUPPLEMENTAL_ROOMS.items():
        room_map.setdefault(room_code, dict(mapping))
    return room_map


def get_latest_numeric_value(series):
    numeric = pd.to_numeric(series, errors="coerce")
    valid = numeric.dropna()
    if valid.empty:
        return None
    return float(valid.iloc[-1])


def read_source_csv(path):
    last_error = None
    for encoding in SOURCE_ENCODINGS:
        try:
            return pd.read_csv(path, encoding=encoding, low_memory=False)
        except UnicodeDecodeError as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    return pd.read_csv(path, low_memory=False)


def classify_status(actual_temp, requirement):
    if actual_temp is None or requirement is None:
        return "NO_DATA"

    diff = actual_temp - requirement
    return "CRITICAL" if diff >= 2 else "OK"


def ingest():
    room_map = load_existing_room_map()
    parsed_rooms = {}

    for source_file in SOURCE_FILES:
        if not source_file.exists():
            continue

        df = read_source_csv(source_file)
        for column in df.columns:
            if str(column).strip().lower() == "time":
                continue

            match = HEADER_RE.match(str(column).strip())
            if not match:
                continue

            room_code = normalize_room_code(match.group("code"))
            if not room_code:
                continue

            suffix = (match.group("suffix") or "").strip().lower().rstrip(".")
            if "coil temp" in suffix:
                continue

            room_entry = parsed_rooms.setdefault(room_code, {})
            value = get_latest_numeric_value(df[column])

            if suffix.startswith("sp"):
                room_entry["Requirement"] = value
            elif suffix == "":
                room_entry["Actual Temp"] = value
                room_entry["source_label"] = match.group("label").strip()

    records = []
    for room_code, mapping in room_map.items():
        source_values = parsed_rooms.get(room_code, {})
        actual_temp = source_values.get("Actual Temp")
        requirement = source_values.get("Requirement")
        temp_diff = None if actual_temp is None or requirement is None else actual_temp - requirement

        records.append(
            {
                "base_room": mapping["base_room"],
                "room_name": mapping["room_name"],
                "Actual Temp": actual_temp,
                "Requirement": requirement,
                "temp_diff": temp_diff,
                "status": classify_status(actual_temp, requirement),
            }
        )

    room_df = pd.DataFrame(records, columns=["base_room", "room_name", "Actual Temp", "Requirement", "temp_diff", "status"])

    conn = sqlite3.connect(DB_FILE)
    try:
        room_df.to_sql("room_temperature", conn, if_exists="replace", index=False)
    finally:
        conn.close()

    print(f"Loaded {len(room_df)} room rows from CSV temperature sources.")


if __name__ == "__main__":
    ingest()
