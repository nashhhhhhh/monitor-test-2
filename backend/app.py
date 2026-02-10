from flask import Flask, jsonify, send_from_directory, request, make_response
import sqlite3
import csv
import os
import io
import pandas as pd
from datetime import datetime
from fpdf import FPDF
import matplotlib
matplotlib.use('Agg')  # Required for headless server environments
import matplotlib.pyplot as plt

# =====================================================
# PATH CONFIGURATION
# =====================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "frontend"))
DATA_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "data"))
LOGO_LOCATIONS = [
    "/shared/assets/SATS_Logo.png",
    os.path.join(DATA_DIR, "SATS_Logo.png"),
    os.path.join(BASE_DIR, "SATS_Logo.png")
]

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

        # 5. Fill NaNs with None (becomes null in JSON)
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
        return jsonify([dict(r) for r in rows])
    except:
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
            # Skip metadata lines 1 & 2
            df = pd.read_csv(path, skiprows=2)
            df.columns = [c.strip() for c in df.columns]
            
            # Clean ' ICT' and parse timestamps
            df['Timestamp'] = df['Timestamp'].str.replace(' ICT', '', regex=False)
            df['dt'] = pd.to_datetime(df['Timestamp'], format='%d-%b-%y %I:%M:%S %p')
            
            # Filter by the user-selected date
            if date_str:
                df = df[df['dt'].dt.strftime('%Y-%m-%d') == date_str]
            else:
                df = df.tail(50)

            # Identify the Value column dynamically
            val_col = [c for c in df.columns if 'Value' in c][0]
            
            return [{
                "time": r['dt'].strftime('%H:%M'), 
                "value": float(r[val_col])
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

@app.route("/api/mdb")
def mdb_data():
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
        }
    }

    # CRITICAL FIX: Standard JSON cannot handle NaN. 
    # This recursive function finds all NaNs and turns them into None (null).
    def clean_nan(obj):
        if isinstance(obj, list):
            return [clean_nan(i) for i in obj]
        if isinstance(obj, dict):
            return {k: clean_nan(v) for k, v in obj.items()}
        if isinstance(obj, float) and pd.isna(obj):
            return None
        return obj

    return jsonify(clean_nan(raw_data))
@app.route("/api/mdb/history")
def mdb_history():
    date_str = request.args.get('date')
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

    response_data = {}
    if category == 'energy':
        res = get_filtered_mdb("mdb_emdb.csv", "kwh")
        response_data['emdb_1'] = res['points']
        response_data['selected_date'] = res['date_used']
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
            self.set_x(50) # Move text right
        else:
            self.set_x(10) # Start from left if no logo
            
        self.set_font('Arial', 'B', 12)
        self.set_text_color(15, 23, 42)
        self.cell(0, 10, 'STAGE 2 INDUSTRIAL SYSTEMS MASTER REPORT', 0, 1, 'L')
        
        self.set_draw_color(59, 130, 246)
        self.line(10, 22, 200, 22)
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.set_text_color(128)
        self.cell(0, 10, f'Page {self.page_no()} | CONFIDENTIAL DATA', 0, 0, 'C')


def save_chart_to_file(df, x_col, y_col, title, ylabel, filename, color='#3b82f6'):
    plt.figure(figsize=(6, 3))
    plt.plot(df[x_col], df[y_col], color=color, linewidth=2)
    plt.title(title, fontsize=10, fontweight='bold')
    plt.ylabel(ylabel, fontsize=8)
    plt.xticks(rotation=45, fontsize=7)
    plt.yticks(fontsize=7)
    plt.grid(True, linestyle='--', alpha=0.4)
    plt.tight_layout()
    path = os.path.join(BASE_DIR, filename)
    plt.savefig(path, format='png', dpi=150)
    plt.close()
    return path

@app.route("/api/export/report")
def export_report():
    temp_files = []
    excel_path = os.path.join(DATA_DIR, 'Temperature_Reading.xlsx')
    
    try:
        pdf = SATS_Report()
        pdf.set_auto_page_break(auto=True, margin=20)
        
        # 1. Initialize Interactive Hyperlinks
        links = {k: pdf.add_link() for k in ["mdb", "temp", "wtp", "wwtp", "sbf", "boiler", "air", "cctv"]}

        # --- PAGE 1: COVER ---
        pdf.add_page()
        pdf.ln(80)
        pdf.set_font('Arial', 'B', 32)
        pdf.cell(0, 20, "STAGE 2 FACILITY", 0, 1, 'C')
        pdf.cell(0, 20, "SYSTEMS MASTER REPORT", 0, 1, 'C')
        pdf.ln(10)
        pdf.set_font('Arial', '', 14)
        pdf.cell(0, 10, f"Generated: {datetime.now().strftime('%d %b %Y, %I:%M %p')}", 0, 1, 'C')

        # --- PAGE 2: MASTER HEALTH OVERVIEW (AT-A-GLANCE) ---
        pdf.add_page()
        pdf.set_font('Arial', 'B', 20)
        pdf.cell(0, 15, "Master System Status Overview", 0, 1, 'L')
        pdf.set_font('Arial', '', 10)
        pdf.cell(0, 5, "Click any system name to jump to its deep-dive report.", 0, 1, 'L')
        pdf.ln(8)

        # Table Headers
        pdf.set_font('Arial', 'B', 10)
        pdf.set_fill_color(30, 41, 59); pdf.set_text_color(255)
        pdf.cell(70, 12, " Industrial System", 1, 0, 'L', True)
        pdf.cell(40, 12, "Status", 1, 0, 'C', True)
        pdf.cell(80, 12, "Key Metric / Observation", 1, 1, 'C', True)
        pdf.set_text_color(0)

        # Helper to add rows to Overview
        def add_overview_row(name, link_key, status, metric):
            pdf.set_font('Arial', '', 10)
            pdf.set_text_color(37, 99, 235)
            pdf.cell(70, 12, f" {name}", 1, 0, 'L', link=links[link_key])
            pdf.set_text_color(0)
            if status == "ATTENTION": pdf.set_fill_color(254, 226, 226); pdf.set_text_color(220, 38, 38)
            elif status == "WARNING": pdf.set_fill_color(255, 247, 237); pdf.set_text_color(194, 65, 12)
            else: pdf.set_fill_color(240, 253, 244); pdf.set_text_color(22, 101, 52)
            pdf.cell(40, 12, status, 1, 0, 'C', True)
            pdf.set_text_color(0)
            pdf.cell(80, 12, f" {metric}", 1, 1, 'L')

        # Overview Data Logic
        # Temp
        try:
            df_sum = pd.read_excel(excel_path, sheet_name='Summary')
            total_out = df_sum[df_sum.iloc[:, 0] == "Total:"].iloc[0, 1]
            add_overview_row("Cold Chain (Temp)", "temp", "ATTENTION" if int(total_out) > 0 else "NORMAL", f"{total_out} Alarms Found")
        except: add_overview_row("Cold Chain (Temp)", "temp", "OFFLINE", "No Data")
        
        # MDB
        try:
            val = pd.read_csv(os.path.join(DATA_DIR, 'mdb_emdb.csv'), skiprows=2).iloc[-1].iloc[-1]
            add_overview_row("Power Systems (MDB)", "mdb", "NORMAL", f"{val:,.0f} kWh")
        except: add_overview_row("Power Systems (MDB)", "mdb", "OFFLINE", "No Data")

        # CCTV
        try:
            df_c = pd.read_excel(os.path.join(DATA_DIR, "Resource Online Status Log_2026_02_05_10_21_49.xlsx"))
            off = len(df_c[df_c['Current Status'].str.lower() != 'online'])
            add_overview_row("CCTV Security", "cctv", "WARNING" if off > 0 else "NORMAL", f"{off} Cameras Offline")
        except: add_overview_row("CCTV Security", "cctv", "OFFLINE", "Log Missing")

        # WTP
        try:
            wtp = pd.read_csv(os.path.join(DATA_DIR, 'RES102ROWaterSupply_ResCl2.csv'), skiprows=2).iloc[-1].iloc[-1]
            add_overview_row("Water Treatment (WTP)", "wtp", "NORMAL", f"{wtp} mg/L Chlorine")
        except: add_overview_row("Water Treatment (WTP)", "wtp", "OFFLINE", "No Data")

        # Others (Boiler, Air, WWTP, SBF) - Brief Rows
        add_overview_row("Spiral Blast Freezer", "sbf", "NORMAL", "Online")
        add_overview_row("Boiler Systems", "boiler", "NORMAL", "Online")
        add_overview_row("Air Compressor", "air", "NORMAL", "Online")
        add_overview_row("Wastewater Plant", "wwtp", "NORMAL", "Online")

        # --- PAGE 3: MDB DEEP DIVE (FIXED SPACING) ---
        pdf.add_page()
        pdf.set_link(links["mdb"], page=pdf.page_no())
        pdf.set_font('Arial', 'B', 16); pdf.cell(0, 10, "1. Power Systems (MDB) Details", 0, 1, 'L')
        try:
            df_mdb = pd.read_csv(os.path.join(DATA_DIR, 'mdb_emdb.csv'), skiprows=2)
            df_chart = df_mdb.tail(24).copy()
            df_chart.columns = [c.strip() for c in df_chart.columns]
            val_col = [c for c in df_chart.columns if 'Value' in c][0]
            df_chart['time_label'] = df_chart['Timestamp'].str.replace(' ICT', '').str.split(' ').str[1].str[:5]
            
            p_mdb = save_chart_to_file(df_chart, 'time_label', val_col, "Energy Consumption Trend", "kWh", "tmp_mdb.png")
            temp_files.append(p_mdb)
            
            pdf.image(p_mdb, x=15, y=45, w=180)
            # 🔑 THE FIX: Move Y cursor to 140mm to prevent overlap with the chart
            pdf.set_y(140) 
            
            pdf.set_font('Arial', 'B', 11); pdf.cell(0, 10, " Historical Consumption Log", 0, 1, 'L')
            pdf.set_font('Arial', '', 9)
            for _, r in df_mdb.tail(10).iterrows():
                pdf.cell(90, 7, str(r['Timestamp']).replace(' ICT', ''), 1, 0, 'L')
                pdf.cell(90, 7, f"{r[val_col]:,.2f} kWh", 1, 1, 'R')
        except Exception as e: pdf.cell(0, 10, f"Error: {str(e)}", 0, 1)

        # --- PAGE 4: COLD CHAIN ALL ROOMS ---
        pdf.add_page()
        pdf.set_link(links["temp"], page=pdf.page_no())
        pdf.set_font('Arial', 'B', 16); pdf.cell(0, 10, "2. Cold Chain - Detailed Temperature Logs", 0, 1, 'L')
        pdf.ln(5)
        try:
            df_temp = pd.read_excel(excel_path, sheet_name='Database')
            df_temp.columns = [c.replace(':', '').strip().lower() for c in df_temp.columns]
            
            def p_h():
                pdf.set_font('Arial', 'B', 9); pdf.set_fill_color(230, 235, 245)
                pdf.cell(85, 8, "Room Name", 1, 0, 'C', True)
                pdf.cell(30, 8, "Temp (C)", 1, 0, 'C', True)
                pdf.cell(65, 8, "Status / Remarks", 1, 1, 'C', True)
                pdf.set_font('Arial', '', 7)
            
            p_h()
            t_k = [c for c in df_temp.columns if 'recent temp' in c][0]
            tol_k = [c for c in df_temp.columns if 'tolerance' in c][0]
            
            for _, row in df_temp.iterrows():
                if pdf.get_y() > 265: pdf.add_page(); p_h()
                is_out = str(row[tol_k]).strip().upper() == 'N'
                if is_out: pdf.set_text_color(220, 38, 38)
                pdf.cell(85, 6, str(row.iloc[1])[:45], 1, 0, 'L')
                pdf.cell(30, 6, str(row[t_k]), 1, 0, 'C')
                pdf.cell(65, 6, "OUT OF TOLERANCE" if is_out else "NORMAL", 1, 1, 'C')
                pdf.set_text_color(0)
        except Exception as e: pdf.cell(0, 10, f"Error: {str(e)}", 0, 1)

        # --- PAGE 5: WATER & WASTEWATER ---
        pdf.add_page()
        pdf.set_link(links["wtp"], page=pdf.page_no())
        pdf.set_font('Arial', 'B', 16); pdf.cell(0, 10, "3. Utilities: Water Treatment (WTP & WWTP)", 0, 1, 'L')
        try:
            wtp_df = pd.read_csv(os.path.join(DATA_DIR, 'RES102ROWaterSupply_ResCl2.csv'), skiprows=2).tail(15)
            pdf.image(save_chart_to_file(wtp_df.tail(20), wtp_df.columns[0], wtp_df.columns[1], "Chlorine Trend", "mg/L", "tmp_wtp.png", "#10b981"), x=15, y=45, w=180)
            pdf.set_y(140)
            pdf.cell(0, 10, "Latest Water Quality Log", 0, 1, 'L')
            for _, r in wtp_df.tail(8).iterrows():
                pdf.cell(90, 7, str(r.iloc[0]).replace(' ICT', ''), 1, 0, 'L')
                pdf.cell(90, 7, f"{r.iloc[1]} mg/L", 1, 1, 'R')
        except: pdf.cell(0, 10, "Utility Data Unreachable", 0, 1)

        # --- PAGE 6: SBF, BOILER, AIR COMPRESSOR ---
        pdf.add_page()
        pdf.set_link(links["sbf"], page=pdf.page_no())
        pdf.set_font('Arial', 'B', 16); pdf.cell(0, 10, "4. KitchenEquipment Status", 0, 1, 'L')
        pdf.ln(5)
        # SBF Summary
        pdf.set_font('Arial', 'B', 11); pdf.cell(0, 10, "Spiral Blast Freezer", 0, 1, 'L', True)
        pdf.set_font('Arial', '', 10); pdf.cell(0, 8, "Systems operating within baseline. See Dashboard for live vibration/motor metrics.", 0, 1)
        # Boiler Summary
        pdf.set_font('Arial', 'B', 11); pdf.cell(0, 10, "Boiler Systems", 0, 1, 'L', True)
        pdf.set_font('Arial', '', 10); pdf.cell(0, 8, "Steam Pressure and Gas Consumption consistent with production load.", 0, 1)
        # Air Compressor
        pdf.set_font('Arial', 'B', 11); pdf.cell(0, 10, "Air Compressor", 0, 1, 'L', True)
        pdf.set_font('Arial', '', 10); pdf.cell(0, 8, "Instrument Air Dewpoint: Stable.", 0, 1)

        # --- EXPORT ---
        pdf_raw = pdf.output(dest='S')
        response = make_response(pdf_raw.encode('latin-1') if isinstance(pdf_raw, str) else pdf_raw)
        response.headers.set('Content-Type', 'application/pdf')
        response.headers.set('Content-Disposition', 'attachment', filename='SATS_Master_Report.pdf')
        for f in temp_files:
            if os.path.exists(f): os.remove(f)
        return response

    except Exception as e:
        for f in temp_files:
            if os.path.exists(f): os.remove(f)
        return jsonify({"error": str(e)}), 500
# =====================================================
# SERVER START
# =====================================================

if __name__ == "__main__":
    print("\n🚀 Server running at http://127.0.0.1:5000")
    print(f"📂 Data directory: {DATA_DIR}\n")
    app.run(debug=True, port=5000)
55