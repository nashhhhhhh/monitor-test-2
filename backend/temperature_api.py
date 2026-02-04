from flask import Blueprint, jsonify
import sqlite3
import os

temperature_bp = Blueprint("temperature", __name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "temps.db")

@temperature_bp.route("/api/temperature/rooms")
def get_rooms():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM room_temperature").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])
