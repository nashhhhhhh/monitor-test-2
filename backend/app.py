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

    # Energy Metrics (Added per request)
    direct_energy = read_csv("boiler_direct_energy.csv", "energy")
    indirect_energy = read_csv("boiler_indirect_energy.csv", "energy")

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
            "indirect_steam_kg": indirect_steam,
            "direct_energy_kwh": direct_energy,
            "indirect_energy_kwh": indirect_energy
        }
    })


# =====================================================
# CCTV / RESOURCE STATUS API
# =====================================================

@app.route("/api/cctv/log")
def cctv_log():
    file_name = "Resource Online Status Log_2026_02_05_10_21_49.xlsx"
    path = os.path.join(DATA_DIR, file_name)

    if not os.path.exists(path):
        print(f"❌ File not found: {path}")
        return jsonify([])

    try:
        import pandas as pd

        df = pd.read_excel(path)
        df.columns = df.columns.str.strip()

        devices = []

        for _, row in df.iterrows():
            devices.append({
                "name": str(row["Name"]).strip(),
                "status": str(row["Current Status"]).strip(),
                "area": str(row["Area"]).strip(),
                "address": str(row["Address"]).strip(),
                "lastOffline": str(row["Latest Offline Time"]),
                "offlineCount": str(row["Total Offline Times"]),
                "offlineDuration": str(row["Total Offline Duration"])
            })

        print(f"✅ Loaded {len(devices)} CCTV devices")
        return jsonify(devices)

    except Exception as e:
        print("🔥 CCTV API Error:", e)
        return jsonify([]) 
    
# =====================================================
# SPIRAL BLAST FREEZER API
# =====================================================

@app.route("/api/spiral_blast_freezer")
def spiral_blast_freezer():
    # --- 1. COMPRESSOR PERFORMANCE ---
    # Metrics: Runtime, Frequency (Hz), and Current (Amp)
    comp01_data = {
        "runtime": read_csv("COMP01 2025-11-28 (60 Min).xlsx - Data.csv", "RUNTIME"),
        "freq": read_csv("COMP01 2025-11-28 (60 Min).xlsx - Data.csv", "FRQ"),
        "current": read_csv("COMP01 2025-11-28 (60 Min).xlsx - Data.csv", "CURRENT")
    }
    comp02_data = {
        "runtime": read_csv("COMP02 2025-11-27 (60 Min).xlsx - Data.csv", "RUNTIME"),
        "freq": read_csv("COMP02 2025-11-27 (60 Min).xlsx - Data.csv", "FRQ"),
        "current": read_csv("COMP02 2025-11-27 (60 Min).xlsx - Data.csv", "CURRENT")
    }

    # --- 2. SPIRAL FREEZER UNITS (01, 02, 03) ---
    # Metrics: Internal Temps (TEF01) and Unit Runtimes
    spiral01 = {
        "temp": read_csv("SPIRAL01 2025-11-28 (1 Min).xlsx - Data.csv", "TEF01"),
        "runtime": read_csv("SPIRAL01 2025-11-28 (1 Min).xlsx - Data.csv", "Runtime")
    }
    spiral02 = {
        "temp": read_csv("SPIRAL02 2025-11-28 (1 Min).xlsx - Data.csv", "TEF01"),
        "runtime": read_csv("SPIRAL02 2025-11-28 (1 Min).xlsx - Data.csv", "Runtime")
    }
    spiral03 = {
        "temp": read_csv("SPIRAL03 2025-11-28 (60 Min).xlsx - Data.csv", "TEF01"),
        "runtime": read_csv("SPIRAL03 2025-11-28 (60 Min).xlsx - Data.csv", "Runtime")
    }

    # --- 3. REFRIGERATION SYSTEM STATUS ---
    # Metrics: Low Receiver Temperatures
    refrig_system = {
        "receiver_01": read_csv("REFRIG 2025-11-28 (60 Min).xlsx - Data.csv", "NO.1"),
        "receiver_02": read_csv("REFRIG 2025-11-28 (60 Min).xlsx - Data.csv", "NO.2"),
        "receiver_03": read_csv("REFRIG 2025-11-28 (60 Min).xlsx - Data.csv", "NO.3")
    }

    # --- 4. MULTI-LAYER FREEZERS (MLF) ENERGY ---
    # Metrics: Total Energy Consumption (kWh)
    mlf_energy = {
        "mlf01_kwh": read_csv("MLF01 2025-11-28 (60 Min).xlsx - Data.csv", "kWh."),
        "mlf02_kwh": read_csv("MLF02 2025-11-20 (60 Min).xlsx - Data.csv", "kWh.")
    }

    # --- 5. CONVEYOR & PRODUCTION ---
    # Metrics: Line capacity (Pieces/Minute)
    conveyor_lines = {
        "line_1": read_csv("CONVE01 2025-11-28 (60 Min).xlsx - Data.csv", "Capacity (Pcs/Min)"),
        "line_2": read_csv("CONVE02 2025-12-23 (1 Min).xlsx - Data.csv", "Capacity (Pcs/Min)"),
        "line_3": read_csv("CONVE03 2025-11-28 (60 Min).xlsx - Data.csv", "Capacity (Pcs/Min)")
    }

    # --- 6. UTILITY / MDB POWER TOTALS ---
    mdb_power = {
        "panel_01": read_csv("MDB01 2025-11-25 (60 Min).xlsx - Data.csv", "kWh."),
        "panel_02": read_csv("MDB02 2025-11-26 (60 Min).xlsx - Data.csv", "kWh."),
        "monthly_summary": read_csv("Power_Meter_Monthly & Utility Monthly (November-2025).xlsx - ENERGY.csv", "kWh")
    }

    return jsonify({
        "compressors": {"c01": comp01_data, "c02": comp02_data},
        "spiral_freezers": {"s01": spiral01, "s02": spiral02, "s03": spiral03},
        "refrigeration": refrig_system,
        "energy_consumption": {"mlf": mlf_energy, "mdb": mdb_power},
        "production_output": conveyor_lines
    })

# =====================================================

if __name__ == "__main__":
    print(f"\n🚀 Server starting at http://127.0.0.1:5000")
    print(f"📂 Data folder: {DATA_DIR}\n")
    app.run(debug=True, port=5000)