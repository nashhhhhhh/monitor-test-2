from flask import Flask, send_from_directory
import os
from temperature_api import temperature_bp

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "frontend"))

app = Flask(__name__)

# =========================
# REGISTER BLUEPRINTS
# =========================
app.register_blueprint(temperature_bp)

# =========================
# ROUTES – PAGES
# =========================
@app.route("/")
def overview():
    return send_from_directory(os.path.join(FRONTEND_DIR, "Overview"), "index.html")

@app.route("/<module>")
def module_page(module):
    module_path = os.path.join(FRONTEND_DIR, module)
    if os.path.exists(module_path):
        return send_from_directory(module_path, "index.html")
    return "Module not found", 404

@app.route("/<module>/<submodule>")
def submodule_page(module, submodule):
    sub_path = os.path.join(FRONTEND_DIR, module, submodule)
    if os.path.exists(sub_path):
        return send_from_directory(sub_path, "index.html")
    return "Submodule not found", 404

# =========================
# STATIC FILES
# =========================
@app.route("/frontend/<path:path>")
def frontend_files(path):
    return send_from_directory(FRONTEND_DIR, path)

# =====================================================
# TEMPERATURE API
# =====================================================

@app.route("/api/temperature/rooms")
def temperature_rooms():
    conn = sqlite3.connect(os.path.join(BASE_DIR, "temps.db"))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM room_temperature").fetchall()
    conn.close()

    return jsonify([dict(r) for r in rows])

# =====================================================
# AIR COMPRESSOR API
# =====================================================

def read_csv(path, value_key):
    data = []
    if not os.path.exists(path):
        return data
    with open(path, newline="", encoding="utf-8") as f:
        lines = f.readlines()[2:] # Skip metadata
        reader = csv.DictReader(lines)
        for row in reader:
            try:
                # Ensure we have data before processing
                if row.get("Timestamp") and row.get("Value"):
                    data.append({
                        "time": row["Timestamp"].split(" ")[1],
                        value_key: float(row["Value"])
                    })
            except (ValueError, IndexError):
                continue
    return data

@app.route("/api/aircompressor")
def aircompressor():
    energy = read_csv(
        os.path.join(DATA_DIR, "aircompressor_energy.csv"),
        "energy"
    )
    flow = read_csv(
        os.path.join(DATA_DIR, "airmeter_flow.csv"),
        "flow"
    )
    dew = read_csv(
        os.path.join(DATA_DIR, "air_dewpoint.csv"),
        "dewpoint"
    )

    return jsonify({
        "energy": energy,
        "flow": flow,
        "dewpoint": dew
    })

# =====================================================

if __name__ == "__main__":
    app.run(debug=True)
