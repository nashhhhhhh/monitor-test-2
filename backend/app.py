from flask import Flask, jsonify, send_from_directory
import sqlite3
import os

# ==============================
# Flask App Configuration
# ==============================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(
    __name__,
    static_folder="../frontend",
    static_url_path=""
)

# ==============================
# Helpers
# ==============================

def get_db_connection():
    db_path = os.path.join(BASE_DIR, "temps.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

# ==============================
# Page Routes
# ==============================

@app.route("/")
def overview():
    # Serve Overview page as default
    return send_from_directory(
        app.static_folder + "/Overview",
        "index.html"
    )

@app.route("/Overview/")
def overview_page():
    return send_from_directory(
        app.static_folder + "/Overview",
        "index.html"
    )

@app.route("/Temperature/")
def temperature_page():
    return send_from_directory(
        app.static_folder + "/Temperature",
        "index.html"
    )

@app.route("/CCTV/")
def cctv_page():
    return send_from_directory(
        app.static_folder + "/CCTV",
        "index.html"
    )

# ==============================
# API ROUTES
# ==============================

@app.route("/api/temperature/rooms")
def api_temperature_rooms():
    """
    Used by:
    - Overview KPIs
    - Temperature floorplan
    """

    conn = get_db_connection()
    rows = conn.execute("""
        SELECT
            base_room,
            room_name,
            "Actual Temp" AS actual_temp,
            Requirement,
            status
        FROM room_temperature
    """).fetchall()
    conn.close()

    data = []
    for r in rows:
        data.append({
            "room": r["base_room"],
            "name": r["room_name"],
            "actual": r["actual_temp"],
            "setpoint": r["Requirement"],
            "status": r["status"]
        })

    return jsonify(data)

# ==============================
# HEALTH CHECK (OPTIONAL)
# ==============================

@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})

# ==============================
# Run Server
# ==============================

if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True
    )
