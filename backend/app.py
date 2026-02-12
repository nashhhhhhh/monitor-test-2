from flask import Flask, jsonify, send_from_directory, request, make_response, Blueprint, send_file
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
from fpdf import FPDF
from fpdf.enums import XPos, YPos
from io import BytesIO
import tempfile


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

    return jsonify(collect_mdb_data())
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

def get_wtp_raw_data():
    return {
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
            "fire_water":   get_flow_rate("FIT-105-FireWaterTank_Total.csv")
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
    
    # Convert list of dicts to DataFrame for easy plotting
    df = pd.DataFrame(data_list)
    # Extract just the last 24 points for clarity
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

def render_temperature_table(pdf, df):
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

    # ---------- INITIAL HEADER ----------
    draw_header()

    pdf.set_font('helvetica', '', 9)
    pdf.set_text_color(0)

    fill = False  # for alternating row colour

    for _, r in df.iterrows():
        # ---------- PAGE BREAK ----------
        if pdf.get_y() > 265:
            pdf.add_page()
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

def render_mdb_energy_table(pdf, energy_data):
    pdf.set_font('helvetica', 'B', 12)
    pdf.cell(0, 8, "MDB Energy Distribution (Latest Reading)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)

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

def get_wwtp_report_data(): # Ensure this matches what you call in the route
    files = {
        "effluent": "EffluentPump_Total.csv",
        "raw_pump": "_RawWaterWastePump-01_Total.csv",
        "raw_temp": "_RawWasteWater_Temp.csv", # 🔑 This must match l_temp's key
        "pmg_energy": "PMG-WWTP_Energy.csv",
        "ctrl_energy": "_PM-WWTP-CONTROL-PANEL_Energy.csv"
    }
    
    data_output = {}
    for key, file_name in files.items():
        path = os.path.join(DATA_DIR, file_name)
        if os.path.exists(path):
            try:
                # Read CSV skipping metadata
                df = pd.read_csv(path, skiprows=2)
                df.columns = [c.strip() for c in df.columns]
                val_col = [c for c in df.columns if 'Value' in c][0]
                
                # 🔑 THE FIX: Force numeric conversion
                # errors='coerce' turns "{ }" into NaN
                # .fillna(0.0) turns NaN into 0.0
                df[val_col] = pd.to_numeric(df[val_col], errors='coerce').fillna(0.0)
                
                df['Timestamp'] = df['Timestamp'].astype(str).str.replace(' ICT', '', regex=False)
                df['dt'] = pd.to_datetime(df['Timestamp'], format='%d-%b-%y %I:%M:%S %p', errors='coerce')
                
                data_output[key] = df.dropna(subset=['dt'])
            except Exception as e:
                data_output[key] = pd.DataFrame()
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

    # --- Efficiency Chart ---
    fig, ax1 = plt.subplots(figsize=(7, 3.5))
    ax2 = ax1.twinx()

    ax1.plot(labels, flow_vals, label="Flow (m³)", linewidth=2)
    ax2.plot(labels, energy_vals, label="Energy (kWh)", linewidth=2)

    ax1.set_ylabel("Flow (m³)")
    ax2.set_ylabel("Energy (kWh)")
    ax1.set_title("Air Compressor Efficiency")

    fig.tight_layout()
    eff_path = os.path.join(tmp_dir, "air_efficiency.png")
    plt.savefig(eff_path, dpi=150)
    plt.close()

    img_paths["efficiency"] = eff_path

    # --- Dewpoint Chart ---
    plt.figure(figsize=(7, 3.5))
    plt.plot(labels, dew_vals, linewidth=2)
    plt.title("Compressed Air Dewpoint")
    plt.ylabel("Dewpoint (°C)")
    plt.tight_layout()

    dew_path = os.path.join(tmp_dir, "air_dewpoint.png")
    plt.savefig(dew_path, dpi=150)
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
# MASTER EXPORT ROUTE
# =====================================================
@app.route("/api/export/report")
def export_report():
    temp_files = []
    excel_path = os.path.join(DATA_DIR, 'Temperature_Reading.xlsx')

    try:
        pdf = SATS_Report()
        pdf.set_auto_page_break(auto=True, margin=20)

        # 1. Initialize Links
        lnk_mdb = pdf.add_link()
        lnk_tmp = pdf.add_link()
        lnk_util = pdf.add_link()
        lnk_cctv = pdf.add_link()
        lnk_wwtp = pdf.add_link()
        lnk_ac= pdf.add_link()

        pdf.set_link(lnk_mdb, page=1)
        pdf.set_link(lnk_tmp, page=1)
        pdf.set_link(lnk_util, page=1)
        pdf.set_link(lnk_cctv, page=1)
        pdf.set_link(lnk_wwtp, page=1)
        pdf.set_link(lnk_ac, page=1)

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
            f"Generated: {datetime.now().strftime('%d %b %Y, %I:%M %p')}",
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

        try:
            df_sum = pd.read_excel(excel_path, sheet_name='Summary')
            total_out = df_sum[df_sum.iloc[:, 0] == "Total:"].iloc[0, 1]
            add_row("Cold Chain (Temp)", lnk_tmp,
                    "ATTENTION" if int(total_out) > 0 else "NORMAL",
                    f"{total_out} Alarms Found")
        except:
            add_row("Cold Chain (Temp)", lnk_tmp, "OFFLINE", "Data Error")

        add_row("Power Systems (MDB)", lnk_mdb, "NORMAL", "Active Stream")
        add_row("Water Treatment (WTP)", lnk_util, "NORMAL", "Online")
        add_row("Wastewater (WWTP)", lnk_wwtp, "NORMAL", "Online")
        add_row("Spiral Blast Freezer", lnk_util, "NORMAL", "Online")
        add_row("Boiler Systems", lnk_util, "NORMAL", "Online")
        add_row("CCTV Monitoring", lnk_cctv, "NORMAL", "Online")
        add_row("Air Compressor", lnk_ac, "NORMAL", "Online")

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
            render_temperature_table(pdf, df_temp)
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

            for key in mdb_panels:
                readings = mdb_data["energy"].get(key, [])
                mdb_energy[key.upper().replace("_", "-")] = readings[-1]["kwh"] if readings else 0

            render_mdb_energy_table(pdf, mdb_energy)

            # --- EMDB Summary ---
            emdb_list = mdb_data["energy"].get("emdb_1", [])
            emdb_latest = emdb_list[-1]["kwh"] if emdb_list else 0
            render_emdb_summary(pdf, emdb_latest)

            # --- Generator Status ---
            render_generator_status_table(pdf, mdb_data["generators"])

        except Exception as e:
            pdf.set_font('helvetica', '', 11)
            pdf.cell(
                0, 10,
                "Power system data unavailable for reporting",
                new_x=XPos.LMARGIN,
                new_y=YPos.NEXT
            )


        # --- PAGE 5: WTP ---
        pdf.add_page()
        pdf.set_link(lnk_util, page=pdf.page_no())
        pdf.set_font('helvetica', 'B', 16)
        pdf.cell(0, 10, "3. Water Treatment Plant (WTP)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        try:
            # CALL THE RAW FUNCTION, NOT THE ROUTE
            wtp = get_wtp_raw_data()

            # -------------------------------
            # 1. EXECUTIVE KPI SUMMARY
            # -------------------------------
            pdf.set_font('helvetica', 'B', 13)
            pdf.cell(0, 8, "3.1 Executive Summary", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(2)

            # --- Data Extraction ---
            ft = wtp["flow_totals"]
            
            # Fetch last readings for all 5 sources
            last_well = ft.get("deep_well", [])[-1]["m3"] if ft.get("deep_well") else 0
            last_soft1 = ft.get("soft_water_1", [])[-1]["m3"] if ft.get("soft_water_1") else 0
            last_soft2 = ft.get("soft_water_2", [])[-1]["m3"] if ft.get("soft_water_2") else 0
            last_ro = ft.get("ro_water", [])[-1]["m3"] if ft.get("ro_water") else 0
            last_fire = ft.get("fire_water", [])[-1]["m3"] if ft.get("fire_water") else 0

            # Fetch Pressure and Quality
            ro_pres_list = wtp["pressure"].get("ro_supply", [])
            soft_pres_list = wtp["pressure"].get("soft_water", [])
            last_ro_pres = ro_pres_list[-1]["bar"] if ro_pres_list else 0
            last_soft_pres = soft_pres_list[-1]["bar"] if soft_pres_list else 0

            cl_list = wtp["quality"].get("ro_chlorine", [])
            last_cl = cl_list[-1]["mg"] if cl_list else 0

            # Combined Status Logic
            status = "ATTENTION" if (last_cl < 0.1 or last_ro_pres > 7.5 or last_soft_pres > 7.5) else "NORMAL"

            # Render Table 1: Compliance & Pressure
            render_simple_table(
                pdf,
                ["Compliance Metric", "Current Reading"],
                [
                    ["Chlorine (mg/L)", f"{last_cl:.2f}"],
                    ["RO Supply Pressure (bar)", f"{last_ro_pres:.1f}"],
                    ["Soft Water Pressure (bar)", f"{last_soft_pres:.1f}"],
                    ["Overall System Status", status],
                ],
                [90, 60]
            )
            pdf.ln(5)

            # Render Table 2: Full Water Source Inventory (5 Sources)
            pdf.set_font('helvetica', 'B', 12)
            pdf.cell(0, 10, "3.2 Accumulated Water Source Volumes", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            render_simple_table(
                pdf,
                ["Water Source", "Total Accumulation (m3)"],
                [
                    ["Deep Well", f"{last_well:,.0f}"],
                    ["Soft Water 1", f"{last_soft1:,.0f}"],
                    ["Soft Water 2", f"{last_soft2:,.0f}"],
                    ["RO Water", f"{last_ro:,.0f}"],
                    ["Fire Water Tank", f"{last_fire:,.0f}"],
                ],
                [90, 60]
            )
            
            # -------------------------------
            # 4. VISUAL TREND ANALYSIS
            # -------------------------------
            pdf.set_font('helvetica', 'B', 14)
            pdf.cell(0, 10, "3.3 Visual Trend Analysis", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(5)

            # --- Chart 1: Residual Chlorine Trend ---
            cl_chart_path = save_wtp_chart(
                wtp["quality"].get("ro_chlorine", []), 'mg', 
                "Chlorine Trend", "mg/L", "tmp_cl_trend.png", color='#f59e0b'
            )
            if cl_chart_path:
                temp_files.append(cl_chart_path)
                pdf.image(cl_chart_path, x=15, w=180)
                pdf.ln(2)

            # --- Chart 2: RO Supply Pressure Trend ---
            ro_chart_path = save_wtp_chart(
                wtp["pressure"].get("ro_supply", []), 'bar', 
                "RO Supply Pressure Trend", "Bar", "tmp_ro_pres.png", color='#3b82f6'
            )
            if ro_chart_path:
                temp_files.append(ro_chart_path)
                pdf.image(ro_chart_path, x=15, w=180)
                pdf.ln(2)

            # --- Chart 3: Soft Water Pressure Trend (NEW) ---
            soft_chart_path = save_wtp_chart(
                wtp["pressure"].get("soft_water", []), 'bar', 
                "Soft Water Supply Pressure Trend", "Bar", "tmp_soft_pres.png", color='#64748b'
            )
            if soft_chart_path:
                temp_files.append(soft_chart_path)
                pdf.image(soft_chart_path, x=15, w=180)

        except Exception as e:
            print(f"PDF WTP Error: {e}")
            pdf.cell(0, 10, "Water Treatment Plant data error: " + str(e), new_x=XPos.LMARGIN, new_y=YPos.NEXT)


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
            
            df_temp = wwtp_data.get('raw_temp')

            # 🔑 THE FIX: Use 'is not None' and '.empty'
            if df_temp is not None and not df_temp.empty:
                chart_df = df_temp.tail(24).copy()
                chart_df['time'] = chart_df['dt'].dt.strftime('%H:%M')
                
                # Dynamically get the Value column name
                val_col = [c for c in chart_df.columns if 'Value' in c][0]
                
                # Convert DataFrame to a list of dicts for your save_wtp_chart helper
                data_list = chart_df.to_dict('records')
                
                temp_path = save_wtp_chart(
                    data_list, val_col, "Inflow Temp (Last 24 Readings)", 
                    "deg C", "tmp_wwtp_temp.png", color='#f59e0b'
                )
                
                if temp_path:
                    temp_files.append(temp_path)
                    pdf.image(temp_path, x=15, w=150)
                    pdf.ln(5)

            # -------------------------------
            # 4.3 Effluent Flow & Energy
            # -------------------------------
            pdf.set_font('helvetica', 'B', 12)
            pdf.cell(0, 10, "4.3 Effluent Flow & Energy Consumption", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

            df_energy = wwtp_data.get('pmg_energy')
            
            # 🔑 THE FIX: Again, use .empty check
            if df_energy is not None and not df_energy.empty:
                chart_df = df_energy.tail(24).copy()
                chart_df['time'] = chart_df['dt'].dt.strftime('%H:%M')
                val_col = [c for c in chart_df.columns if 'Value' in c][0]
                
                data_list = chart_df.to_dict('records')
                
                energy_path = save_wtp_chart(
                    data_list, val_col, "Main WWTP Energy (kWh)", 
                    "kWh", "tmp_wwtp_energy.png", color='#3b82f6'
                )
                
                if energy_path:
                    temp_files.append(energy_path)
                    pdf.image(energy_path, x=15, w=150)

        except Exception as e:
            print(f"🔥 PDF WWTP Error: {e}")
            pdf.set_text_color(220, 38, 38)
            pdf.cell(0, 10, f"WWTP Data Error: {str(e)}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_text_color(0)

        # --- PAGE 7: SBF ---
        pdf.add_page()
        pdf.set_font('helvetica', 'B', 16)
        pdf.cell(0, 10, "5. Spiral Blast Freezer",
                new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # --- PAGE 8: BOILER ---
        pdf.add_page()
        pdf.set_font('helvetica', 'B', 16)
        pdf.cell(0, 10, "6. Boiler System",
                new_x=XPos.LMARGIN, new_y=YPos.NEXT)

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
                
                pdf.set_font('helvetica', 'B', 12)
                pdf.cell(0, 10, f"System Overview: {total_cams} Total Cameras | {offline_cams} Offline", 
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

            pdf.image(charts["efficiency"], w=180)
            pdf.ln(5)
            pdf.image(charts["dewpoint"], w=180)

        # --- FINAL EXPORT (ONLY ONCE) ---
        pdf_raw = pdf.output() 
        pdf_bytes = pdf_raw.encode('latin-1') if isinstance(pdf_raw, str) else pdf_raw
        pdf_stream = BytesIO(pdf_bytes)
        pdf_stream.seek(0)

        for f in temp_files:
            if os.path.exists(f):
                os.remove(f)

        return send_file(
            pdf_stream,
            mimetype="application/pdf",
            as_attachment=True,
            download_name="SFST_Master_Report.pdf"
        )

    except Exception as e:
        print(f"🔥 EXPORT FAILED: {str(e)}")
        return jsonify({"error": str(e)}), 500


# =====================================================
# SERVER START
# =====================================================

if __name__ == "__main__":
    print("\n🚀 Server running at http://127.0.0.1:5000")
    print(f"📂 Data directory: {DATA_DIR}\n")
    app.run(debug=True, port=5000)