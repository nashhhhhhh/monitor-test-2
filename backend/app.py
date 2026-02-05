from flask import Flask, jsonify, send_from_directory
import sqlite3
import csv
import os
import io
import pandas as pd

# =====================================================
# PATH CONFIGURATION
# =====================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "frontend"))
DATA_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "data"))

app = Flask(
    __name__,
    static_folder=FRONTEND_DIR,
    static_url_path=""
)

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

            for row in reader:
                # Clean keys (strip whitespace)
                clean_row = {k.strip(): v for k, v in row.items() if k}

                ts_val = None
                real_val = None

                # Find the Timestamp and Value columns dynamically
                for k, v in clean_row.items():
                    kl = k.lower()
                    if "timestamp" in kl:
                        ts_val = v
                    if "value" in kl:
                        real_val = v

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

    return data


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
        return jsonify([dict(r) for r in rows])
    except:
        return jsonify([])


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


# =========================
# WWTP API ROUTES
# =========================

@app.route("/api/wwtp/summary")
def wwtp_dashboard_data():
    """Consolidated endpoint for the WWTP Dashboard"""
    return jsonify({
        "effluent_flow": read_csv("EffluentPump_Total.csv", "m3"),
        "raw_pump_flow": read_csv("_RawWaterWastePump-01_Total.csv", "m3"),
        "raw_temp": read_csv("_RawWasteWater_Temp.csv", "temp"),
        "control_energy": read_csv("_PM-WWTP-CONTROL-PANEL_Energy.csv", "kwh"),
        "plant_energy": read_csv("PMG-WWTP_Energy.csv", "kwh"),
        "solid_waste": read_csv("WG-WWTP.csv", "m3")
    })

# Individual endpoints for specific chart updates
@app.route("/api/wwtp/effluent_pump")
def effluent_pump():
    return jsonify(read_csv("EffluentPump_Total.csv", "value"))

@app.route("/api/wwtp/raw_pump")
def raw_pump():
    return jsonify(read_csv("_RawWaterWastePump-01_Total.csv", "value"))

@app.route("/api/wwtp/raw_temp")
def raw_temp():
    return jsonify(read_csv("_RawWasteWater_Temp.csv", "value"))

@app.route("/api/wwtp/control_energy")
def control_energy():
    return jsonify(read_csv("_PM-WWTP-CONTROL-PANEL_Energy.csv", "value"))

@app.route("/api/wwtp/pmg_energy")
def pmg_energy():
    return jsonify(read_csv("PMG-WWTP_Energy.csv", "value"))

@app.route("/api/wwtp/wg")
def wg():
    return jsonify(read_csv("WG-WWTP.csv", "value"))


# =====================================================
# SPIRAL BLAST FREEZER API
# =====================================================

@app.route("/api/spiral_blast_freezer")
def spiral_blast_freezer():
    
    # --- 1. COMPRESSOR PERFORMANCE ---
    comp01_data = {
        "full_data": read_csv("sbf_comp1.csv"),
        "metrics": {
            "runtime": read_csv("sbf_comp1.csv", "RUNTIME"),
            "freq": read_csv("sbf_comp1.csv", "FRQ"),
            "current": read_csv("sbf_comp1.csv", "CURRENT")
        }
    }
    comp02_data = {
        "full_data": read_csv("sbf_comp2.csv"),
        "metrics": {
            "runtime": read_csv("sbf_comp2.csv", "RUNTIME"),
            "freq": read_csv("sbf_comp2.csv", "FRQ"),
            "current": read_csv("sbf_comp2.csv", "CURRENT")
        }
    }

    # --- 2. SPIRAL FREEZER UNITS (01, 02, 03) ---
    spiral01 = {
        "full_data": read_csv("sbf_spiral1.csv"),
        "metrics": {
            "temp": read_csv("sbf_spiral1.csv", "TEF01"),
            "runtime": read_csv("sbf_spiral1.csv", "Runtime")
        }
    }
    spiral02 = {
        "full_data": read_csv("sbf_spiral2.csv"),
        "metrics": {
            "temp": read_csv("sbf_spiral2.csv", "TEF01"),
            "runtime": read_csv("sbf_spiral2.csv", "Runtime")
        }
    }
    spiral03 = {
        "full_data": read_csv("sbf_spiral3.csv"),
        "metrics": {
            "temp": read_csv("sbf_spiral3.csv", "TEF01"),
            "runtime": read_csv("sbf_spiral3.csv", "Runtime")
        }
    }

    # --- 3. REFRIGERATION SYSTEM STATUS ---
    refrig_system = {
        "full_data": read_csv("sbf_refrig.csv"),
        "metrics": {
            "receiver_01": read_csv("sbf_refrig.csv", "NO.1"),
            "receiver_02": read_csv("sbf_refrig.csv", "NO.2"),
            "receiver_03": read_csv("sbf_refrig.csv", "NO.3")
        }
    }

    # --- 4. MULTI-LAYER FREEZERS (MLF) ENERGY ---
    mlf_energy = {
        "mlf01": {
            "full_data": read_csv("sbf_mlf1.csv"),
            "kwh": read_csv("sbf_mlf1.csv", "kWh.")
        },
        "mlf02": {
            "full_data": read_csv("sbf_mlf2.csv"),
            "kwh": read_csv("sbf_mlf2.csv", "kWh.")
        }
    }

    # --- 5. CONVEYOR & PRODUCTION ---
    conveyor_lines = {
        "line_1": {
            "full_data": read_csv("sbf_convey1.csv"),
            "capacity": read_csv("sbf_convey1.csv", "Capacity (Pcs/Min)")
        },
        "line_2": {
            "full_data": read_csv("sbf_convey2.csv"),
            "capacity": read_csv("sbf_convey2.csv", "Capacity (Pcs/Min)")
        },
        "line_3": {
            "full_data": read_csv("sbf_convey3.csv"),
            "capacity": read_csv("sbf_convey3.csv", "Capacity (Pcs/Min)")
        }
    }

    # --- 6. UTILITY / MDB POWER TOTALS ---
    mdb_power = {
        "panel_01": {
            "full_data": read_csv("sbf_mdb1.csv"),
            "kwh": read_csv("sbf_mdb1.csv", "kWh.")
        },
        "panel_02": {
            "full_data": read_csv("sbf_mdb2.csv"),
            "kwh": read_csv("sbf_mdb2.csv", "kWh.")
        },
        "monthly_summary": {
            "full_data": read_csv("sbf_power_monthly.csv"),
            "kwh": read_csv("sbf_power_monthly.csv", "kWh")
        }
    }

    return jsonify({
        "compressors": {
            "c01": comp01_data,
            "c02": comp02_data
        },
        "spiral_freezers": {
            "s01": spiral01,
            "s02": spiral02,
            "s03": spiral03
        },
        "refrigeration": refrig_system,
        "energy_consumption": {
            "mlf": mlf_energy,
            "mdb": mdb_power
        },
        "production_output": conveyor_lines
    })


# =====================================================
# SERVER START
# =====================================================

if __name__ == "__main__":
    print("\n🚀 Server running at http://127.0.0.1:5000")
    print(f"📂 Data directory: {DATA_DIR}\n")
    app.run(debug=True, port=5000)
