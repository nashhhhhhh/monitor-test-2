from flask import Flask, jsonify, send_from_directory, Blueprint
import sqlite3
import csv
import os
import io
import pandas as pd

# --- PATH CONFIGURATION ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "frontend"))
DATA_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "data"))

app = Flask(
    __name__,
    static_folder=FRONTEND_DIR,
    static_url_path=""
)

# =====================================================
# BRUTE-FORCE CSV READER
# =====================================================

def read_csv(file_name, value_key):
    path = os.path.join(DATA_DIR, file_name)
    data = []
    
    if not os.path.exists(path):
        print(f"❌ FILE MISSING: {path}")
        return data

    try:
        # Using utf-8-sig to handle Excel's Byte Order Mark (BOM)
        with open(path, mode="r", encoding="utf-8-sig", errors="ignore") as f:
            lines = f.readlines()
            
            # 1. FIND THE DATA START
            # We look for the line containing 'Timestamp'
            header_idx = -1
            for i, line in enumerate(lines):
                if "Timestamp" in line or "timestamp" in line:
                    header_idx = i
                    break
            
            if header_idx == -1:
                print(f"⚠️ HEADER NOT FOUND in {file_name}. Printing first line for debug: {lines[0] if lines else 'EMPTY'}")
                return data

            # 2. PARSE THE DATA
            # We take the lines from the header onwards
            content = "".join(lines[header_idx:])
            # Use io.StringIO to treat the string like a file for DictReader
            reader = csv.DictReader(io.StringIO(content))
            
            for row in reader:
                # Force clean the keys (strip invisible spaces/characters)
                clean_row = {k.strip() if k else "": v for k, v in row.items()}
                
                # Try to find the timestamp and value columns regardless of case
                ts_val = None
                real_val = None
                
                for k, v in clean_row.items():
                    k_lower = k.lower()
                    if "timestamp" in k_lower: ts_val = v
                    if "value" in k_lower: real_val = v

                if ts_val and real_val:
                    try:
                        # Extract Time (HH:MM:SS)
                        time_part = ts_val.strip().split(" ")[1] if " " in ts_val.strip() else ts_val.strip()
                        
                        data.append({
                            "time": time_part,
                            value_key: float(real_val.strip())
                        })
                    except (ValueError, IndexError):
                        continue
            
            print(f"✅ LOADED: {file_name} ({len(data)} rows)")
            
    except Exception as e:
        print(f"🔥 ERROR reading {file_name}: {str(e)}")
        
    return data

# =====================================================
# FRONTEND ROUTING
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
        return jsonify([dict(r) for r in rows])
    except Exception as e:
        return jsonify([])

# =====================================================
# AIR COMPRESSOR API
# =====================================================

@app.route("/api/aircompressor")
def aircompressor():
    energy = read_csv("aircompressor_energy.csv", "energy")
    flow = read_csv("airmeter_flow.csv", "flow")
    dew = read_csv("air_dewpoint.csv", "dewpoint")

    return jsonify({
        "energy": energy,
        "flow": flow,
        "dewpoint": dew
    })

# =====================================================
# BOILER API
# =====================================================

@app.route("/api/boiler")
def boiler():
    # Boiler 1 Runtimes
    b01_1 = read_csv("boiler01_1_RT.csv", "runtime")
    b01_2 = read_csv("boiler01_2_RT.csv", "runtime")
    b01_3 = read_csv("boiler01_3_RT.csv", "runtime")
    
    # Boiler 2 Runtimes
    b02_1 = read_csv("boiler02_1_RT.csv", "runtime")
    b02_2 = read_csv("boiler02_2_RT.csv", "runtime")
    
    # Flow and Gas Totals
    gas_total = read_csv("boiler_gas_total.csv", "gas")
    direct_steam = read_csv("boiler_directsteam_meterflow_total.csv", "steam")
    indirect_steam = read_csv("boiler_indirectsteam_meterflow.csv", "steam")

    return jsonify({
        "boiler_01": {
            "stage_1_runtime": b01_1,
            "stage_2_runtime": b01_2,
            "stage_3_runtime": b01_3
        },
        "boiler_02": {
            "stage_1_runtime": b02_1,
            "stage_2_runtime": b02_2
        },
        "consumption": {
            "gas_total_kg": gas_total,
            "direct_steam_kg": direct_steam,
            "indirect_steam_kg": indirect_steam
        }
    })


# =====================================================
# CCTV / RESOURCE STATUS API
# =====================================================

@app.route("/api/cctv/log")
def cctv_log():
    file_name = "../data/Resource Online Status Log_2026_02_05_10_21_49.xlsx"
    path = os.path.join(DATA_DIR, file_name)
    data = []
    
    if not os.path.exists(path):
        print(f"❌ File not found: {path}")
        return jsonify([])

    try:
        # Use utf-8-sig to handle the invisible Excel BOM characters
        with open(path, mode="r", encoding="utf-8-sig", errors="ignore") as f:
            lines = f.readlines()
            
            # THE CRITICAL STEP:
            # Your file has 9 lines of metadata. The headers are on Line 10 (index 9).
            # We skip exactly 9 lines to find the columns: Timestamp, Resource Name, Resource Status.
            if len(lines) < 10:
                return jsonify([])

            data_start = lines[9:] # Slicing starting from the header row
            reader = csv.DictReader(io.StringIO("".join(data_start)))
            
            for row in reader:
                name = row.get("Resource Name", "").strip()
                status = row.get("Resource Status", "").strip()
                ts = row.get("Timestamp", "").strip()

                if name and status:
                    data.append({
                        "name": name,
                        "status": status,
                        # Split "2026-02-05 10:21:49" to get "10:21:49"
                        "time": ts.split(" ")[1] if " " in ts else ts
                    })

        # Deduplicate: Get only the LATEST status for each device
        latest_status = {}
        for entry in data:
            latest_status[entry["name"]] = entry

        final_list = list(latest_status.values())
        print(f"✅ Successfully loaded {len(final_list)} unique CCTV resources.")
        return jsonify(final_list)
            
    except Exception as e:
        print(f"🔥 Error: {e}")
        return jsonify([])


# =====================================================

if __name__ == "__main__":
    print(f"\n🚀 Server starting at http://127.0.0.1:5000")
    print(f"📂 Data folder: {DATA_DIR}\n")
    app.run(debug=True, port=5000)