from flask import Flask, jsonify, send_from_directory, request
import sqlite3
import csv
import os
import io
import pandas as pd
from datetime import datetime

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

def read_sbf_csv(file_name):
    """
    SAFE reader for Spiral Blast Freezer CSVs
    - Removes NaN values
    - Drops Excel 'Unnamed' columns
    - Guarantees JSON-safe output
    """
    path = os.path.join(DATA_DIR, file_name)
    data = []

    if not os.path.exists(path):
        print(f"❌ FILE MISSING: {path}")
        return data

    try:
        df = pd.read_csv(path)
        df.columns = [c.strip() for c in df.columns]

        # Drop Excel junk columns
        df = df.loc[:, ~df.columns.str.contains("^Unnamed", case=False)]

        # Drop completely empty rows
        df = df.dropna(how="all")

        # Detect time column
        time_col = None
        for c in df.columns:
            cl = c.lower()
            if "time" in cl or "date" in cl or "timestamp" in cl:
                time_col = c
                break

        # Fallback: first column
        if not time_col:
            time_col = df.columns[0]

        for _, r in df.iterrows():
            row = {}

            # Time (always string)
            row["time"] = str(r[time_col])

            for c in df.columns:
                if c == time_col:
                    continue

                val = r[c]

                # 🔒 HARD FILTER: no NaN allowed
                if pd.isna(val):
                    continue

                # Convert safely
                try:
                    row[c.lower()] = float(val)
                except:
                    row[c.lower()] = str(val)

            # Only append rows that have actual data
            if len(row) > 1:
                data.append(row)

    except Exception as e:
        print(f"🔥 SBF CSV ERROR ({file_name}): {e}")

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
    return jsonify({
        "system": "spiral_blast_freezer",
        "status_data": {
            "spiral_01": { "data": read_sbf_csv("sbf_spiral1_Data.csv") },
            "spiral_02": { "data": read_sbf_csv("sbf_spiral2_Data.csv") },
            "spiral_03": { "data": read_sbf_csv("sbf_spiral3_Data.csv") }
        },
        "energy": {
            "monthly_energy": read_sbf_csv("sbf_power_monthly_ENERGY.csv")
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

@app.route("/api/mdb")
def mdb_data():
    return jsonify({
        "energy": {
            # Use the daily aggregator for the trend chart
            "emdb_1_daily": read_mdb_daily_consumption("mdb_emdb.csv"),
            
            # Keep raw readings for the distribution (pie/bar) charts
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
        }
    })

# =====================================================
# WATER TREATMENT PLANT (WTP) API
# =====================================================

def get_flow_rate(file_name):
    """Calculates flow rate (m3/hr) from 15-minute totalizer logs."""
    path = os.path.join(DATA_DIR, file_name)
    if not os.path.exists(path): return 0
    try:
        df = pd.read_csv(path, skiprows=2)
        df.columns = [c.strip() for c in df.columns]
        val_col = [c for c in df.columns if 'Value' in c][0]
        last_two = df.tail(2)
        if len(last_two) == 2:
            # (Latest Total - Previous Total) / 0.25 hours = m3/hr
            diff = float(last_two.iloc[1][val_col]) - float(last_two.iloc[0][val_col])
            return round(diff * 4, 2)
    except: pass
    return 0

@app.route("/api/wtp/chlorine")
def wtp_chlorine():
    date_str = request.args.get('date') # Expected format: YYYY-MM-DD
    file_name = "RES102ROWaterSupply_ResCl2.csv"
    path = os.path.join(DATA_DIR, file_name)
    data = []
    
    if not os.path.exists(path): return jsonify([])

    try:
        df = pd.read_csv(path, skiprows=2)
        df.columns = [c.strip() for c in df.columns]
        df['Timestamp'] = df['Timestamp'].str.replace(' ICT', '', regex=False)
        df['dt'] = pd.to_datetime(df['Timestamp'], format='%d-%b-%y %I:%M:%S %p')
        
        # Filter by date if provided, otherwise show latest 50 points
        if date_str:
            df = df[df['dt'].dt.strftime('%Y-%m-%d') == date_str]
        else:
            df = df.tail(50)

        for _, row in df.iterrows():
            data.append({
                "time": row['dt'].strftime('%H:%M'),
                "mg": float(row.get('Value (mg)', row.get('Value', 0)))
            })
    except Exception as e:
        print(f"Chlorine Filter Error: {e}")
    return jsonify(data)

@app.route("/api/wtp/pressure")
def wtp_pressure():
    date_str = request.args.get('date') # Format: YYYY-MM-DD
    # We have two files for pressure
    file_ro = "PT102ROWaterSupply_Pres.csv"
    file_soft = "PT101SoftWaterSupplyNo1_Pres.csv"
    
    def get_filtered_data(file_name, value_key):
        path = os.path.join(DATA_DIR, file_name)
        if not os.path.exists(path): return []
        try:
            df = pd.read_csv(path, skiprows=2)
            df.columns = [c.strip() for c in df.columns]
            df['Timestamp'] = df['Timestamp'].str.replace(' ICT', '', regex=False)
            df['dt'] = pd.to_datetime(df['Timestamp'], format='%d-%b-%y %I:%M:%S %p')
            
            if date_str:
                df = df[df['dt'].dt.strftime('%Y-%m-%d') == date_str]
            else:
                df = df.tail(50)

            val_col = [c for c in df.columns if 'Value' in c][0]
            return [{"time": r['dt'].strftime('%H:%M'), value_key: float(r[val_col])} for _, r in df.iterrows()]
        except: return []

    return jsonify({
        "ro_supply": get_filtered_data(file_ro, "bar"),
        "soft_water": get_filtered_data(file_soft, "bar")
    })

@app.route("/api/wtp")
def wtp_data():
    return jsonify({
        "flow_totals": {
            "deep_well":     read_csv("FIT-101-DeepWellWater_Total.csv", "m3"),
            "soft_water_1":  read_csv("FIT-102-SoftWaterSupply-01_Total.csv", "m3"),
            "soft_water_2":  read_csv("_FIT-104-SoftWaterSupply-02_Total.csv", "m3"),
            "ro_water":      read_csv("FIT-103-ROWaterSupply_Total.csv", "m3"),
            "fire_water":    read_csv("FIT-105-FireWaterTank_Total.csv", "m3")
        },
        "flow_rates": {
            "deep_well":    get_flow_rate("FIT-101-DeepWellWater_Total.csv"),
            "soft_water_1": get_flow_rate("FIT-102-SoftWaterSupply-01_Total.csv"),
            "soft_water_2": get_flow_rate("_FIT-104-SoftWaterSupply-02_Total.csv"),
            "ro_water":     get_flow_rate("FIT-103-ROWaterSupply_Total.csv"),
            "fire_water":   get_flow_rate("FIT-105-FireWaterTank_Total.csv") # Added this
        },
        "pressure": {
            "soft_water":    read_csv("PT101SoftWaterSupplyNo1_Pres.csv", "bar"),
            "ro_supply":     read_csv("PT102ROWaterSupply_Pres.csv", "bar")
        },
        "quality": {
            "ro_chlorine":   read_csv("RES102ROWaterSupply_ResCl2.csv", "mg")
        }
    })

# =====================================================
# SERVER START
# =====================================================

if __name__ == "__main__":
    print("\n🚀 Server running at http://127.0.0.1:5000")
    print(f"📂 Data directory: {DATA_DIR}\n")
    app.run(debug=True, port=5000)
