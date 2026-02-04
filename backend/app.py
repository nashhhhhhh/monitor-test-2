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

if __name__ == "__main__":
    app.run(debug=True)
