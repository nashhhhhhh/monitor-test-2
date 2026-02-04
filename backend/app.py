from flask import Flask, jsonify, send_from_directory
import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "frontend"))
DB_FILE = os.path.join(BASE_DIR, "temps.db")

app = Flask(
    __name__,
    static_folder=FRONTEND_DIR,
    static_url_path=""   # serve static files from root
)

# -------------------------
# Serve HTML
# -------------------------
@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")

# -------------------------
# API Endpoint
# -------------------------
@app.route("/api/rooms")
def get_rooms():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        "SELECT * FROM room_temperature"
    ).fetchall()

    conn.close()
    return jsonify([dict(r) for r in rows])

# -------------------------
# Run Server
# -------------------------
if __name__ == "__main__":
    print("====== Serving frontend from:", FRONTEND_DIR)
    app.run(port=5000, debug=True)
