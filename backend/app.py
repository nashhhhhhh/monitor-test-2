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

def read_csv(file_name, value_key):
    path = os.path.join(DATA_DIR, file_name)
    data = []

    if not os.path.exists(path):
        print(f"❌ FILE MISSING: {path}")
        return data

    try:
        with open(path, mode="r", encoding="utf-8-sig", errors="ignore") as f:
            lines = f.readlines()

            header_idx = -1
            for i, line in enumerate(lines):
                if "timestamp" in line.lower():
                    header_idx = i
                    break

            if header_idx == -1:
                print(f"⚠️ HEADER NOT FOUND: {file_name}")
                return data

            content = "".join(lines[header_idx:])
            reader = csv.DictReader(io.StringIO(content))

            for row in reader:
                clean_row = {k.strip(): v for k, v in row.items() if k}

                ts_val = None
                real_val = None

                for k, v in clean_row.items():
                    kl = k.lower()
                    if "timestamp" in kl:
                        ts_val = v
                    if "value" in kl:
                        real_val = v

                if ts_val and real_val:
                    try:
                        time_part = ts_val.split(" ")[1] if " " in ts_val else ts_val
                        data.append({
                            "time": time_part,
                            value_key: float(real_val)
                        })
                    except:
                        continue

    except Exception as e:
        print(f"🔥 CSV ERROR ({file_name}): {e}")

    return data


# =====================================================
# WASTE WATER PLANT (WWTP) CONFIG & LOADER
# =====================================================

WWTP_FILES = {
    "effluent_pump_total": "EffluentPump_Total.csv",
    "control_panel_energy": "_PM-WWTP-CONTROL-PANEL_Energy.csv",
    "raw_wastewater_temp": "_RawWasteWater_Temp.csv",
    "raw_wastewater_pump": "_RawWaterWastePump-01_Total.csv",
    "pmg_energy": "PMG-WWTP_Energy.csv",
    "wg_wwtp": "WG-WWTP.csv"
}

wwtp_data = {}

def load_wwtp_csv(file_name):
    path = os.path.join(DATA_DIR, file_name)

    if not os.path.exists(path):
        print(f"❌ WWTP FILE MISSING: {file_name}")
        return None

    try:
        df = pd.read_csv(path)

        df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

        for col in df.columns:
            if "time" in col or "date" in col:
                df[col] = pd.to_datetime(df[col], errors="coerce")
                df = df.sort_values(col)
                break

        print(f"✅ WWTP LOADED: {file_name} ({len(df)} rows)")
        return df

    except Exception as e:
        print(f"🔥 WWTP LOAD ERROR ({file_name}): {e}")
        return None


for key, file in WWTP_FILES.items():
    wwtp_data[key] = load_wwtp_csv(file)


def wwtp_to_json(df, limit=500):
    if df is None or df.empty:
        return []
    return df.tail(limit).to_dict(orient="records")


def wwtp_summary(df):
    if df is None or df.empty:
        return {}

    numeric = df.select_dtypes(include="number")

    return {
        "latest": numeric.iloc[-1].to_dict(),
        "min": numeric.min().to_dict(),
        "max": numeric.max().to_dict(),
        "average": numeric.mean().to_dict()
    }


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


# =====================================================
# WASTE WATER PLANT (WWTP) APIs
# =====================================================

@app.route("/api/wwtp")
def wwtp_sources():
    return jsonify({"sources": list(WWTP_FILES.keys())})


@app.route("/api/wwtp/health")
def wwtp_health():
    return jsonify({
        k: "loaded" if v is not None else "error"
        for k, v in wwtp_data.items()
    })


@app.route("/api/wwtp/<source>")
def wwtp_data_source(source):
    df = wwtp_data.get(source)
    if df is None:
        return jsonify({"error": "Invalid WWTP source"}), 404
    return jsonify(wwtp_to_json(df))


@app.route("/api/wwtp/<source>/summary")
def wwtp_summary_api(source):
    df = wwtp_data.get(source)
    if df is None:
        return jsonify({"error": "Invalid WWTP source"}), 404
    return jsonify(wwtp_summary(df))

# =====================================================
# SPIRAL BLAST FREEZER API
# =====================================================

@app.route("/api/spiral_blast_freezer")
def spiral_blast_freezer():
    # --- 1. COMPRESSOR PERFORMANCE ---
    # Metrics: Runtime, Frequency (Hz), and Current (Amp)
    comp01_data = {
        "runtime": read_csv("sbf_comp1.csv", "RUNTIME"),
        "freq": read_csv("sbf_comp1.csv", "FRQ"),
        "current": read_csv("sbf_comp1.csv", "CURRENT")
    }
    comp02_data = {
        "runtime": read_csv("sbf_comp2.csv", "RUNTIME"),
        "freq": read_csv("sbf_comp2.csv", "FRQ"),
        "current": read_csv("sbf_comp2.csv", "CURRENT")
    }

    # --- 2. SPIRAL FREEZER UNITS (01, 02, 03) ---
    # Metrics: Internal Temps (TEF01) and Unit Runtimes
    spiral01 = {
        "temp": read_csv("sbf_spiral1.csv", "TEF01"),
        "runtime": read_csv("sbf_spiral1.csv", "Runtime")
    }
    spiral02 = {
        "temp": read_csv("sbf_spiral2.csv", "TEF01"),
        "runtime": read_csv("sbf_spiral2.csv", "Runtime")
    }
    spiral03 = {
        "temp": read_csv("sbf_spiral3.csv", "TEF01"),
        "runtime": read_csv("sbf_spiral3.csv", "Runtime")
    }

    # --- 3. REFRIGERATION SYSTEM STATUS ---
    # Metrics: Low Receiver Temperatures
    refrig_system = {
        "receiver_01": read_csv("sbf_refrig.csv", "NO.1"),
        "receiver_02": read_csv("sbf_refrig.csv", "NO.2"),
        "receiver_03": read_csv("sbf_refrig.csv", "NO.3")
    }

    # --- 4. MULTI-LAYER FREEZERS (MLF) ENERGY ---
    # Metrics: Total Energy Consumption (kWh)
    mlf_energy = {
        "mlf01_kwh": read_csv("sbf_mlf1.csv", "kWh."),
        "mlf02_kwh": read_csv("sbf_mlf2.csv", "kWh.")
    }

    # --- 5. CONVEYOR & PRODUCTION ---
    # Metrics: Line capacity (Pieces/Minute)
    conveyor_lines = {
        "line_1": read_csv("sbf_convey1.csv", "Capacity (Pcs/Min)"),
        "line_2": read_csv("sbf_convey2csv", "Capacity (Pcs/Min)"),
        "line_3": read_csv("sbf_convey3.csv", "Capacity (Pcs/Min)")
    }

    # --- 6. UTILITY / MDB POWER TOTALS ---
    mdb_power = {
        "panel_01": read_csv("sbf_mdb1.csv", "kWh."),
        "panel_02": read_csv("sbf_mdb2.csv", "kWh."),
        "monthly_summary": read_csv("sbf_power_monthly.csv", "kWh")
    }

    return jsonify({
        "compressors": {"c01": comp01_data, "c02": comp02_data},
        "spiral_freezers": {"s01": spiral01, "s02": spiral02, "s03": spiral03},
        "refrigeration": refrig_system,
        "energy_consumption": {"mlf": mlf_energy, "mdb": mdb_power},
        "production_output": conveyor_lines
    })


# =====================================================
# SERVER START
# =====================================================

if __name__ == "__main__":
    print("\n🚀 Server running at http://127.0.0.1:5000")
    print(f"📂 Data directory: {DATA_DIR}\n")
    app.run(debug=True, port=5000)
