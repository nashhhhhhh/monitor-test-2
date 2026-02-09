# SATS Stage 2 SFST | Industrial Monitoring Command Center

A centralized, real-time industrial IoT dashboard developed for **SATS Food Solutions (Thailand)**. This system integrates diverse data streams—including SQLite databases, PLC-generated CSV logs, and Excel reports—into a unified "Mission Control" interface.



## 🚀 System Overview
The **Unified Command Center** acts as the central brain for the Stage 2 facility. It provides a "glanceable" health status for 8 critical factory domains, allowing operators to monitor system integrity and navigate to detailed analytics with a single click.

### Monitored Subsystems:
* **Power & Energy (MDB):** Energy load profiles and generator status.
* **Water Treatment (WTP):** Chlorine levels and supply pressure.
* **Cold Chain (Temperature):** Environmental monitoring of storage rooms.
* **Production (Spiral Blast Freezer):** Freezer temperatures and conveyor throughput.
* **Utilities:** Boiler steam/gas consumption and Air Compressor metrics.
* **Security:** CCTV online status tracking.
* **Wastewater (WWTP):** Effluent temperatures and plant energy.

---

## 🏗 Project Structure

```text
Stage-2-System/
├── backend/                # Flask Server & Data Logic
│   ├── app.py              # Main API & Routing
│   ├── temperature_api.py  # SQLite Temperature Logic
│   └── temps.db            # Room sensor database
├── frontend/               # UI Layers
│   ├── Overview/           # Central Command Center (Home)
│   ├── Utilities/          # MDB, Boiler, WTP, WWTP, Air Compressor
│   ├── Spiral Blast Freezer/
│   ├── Temperature/        # Cold Chain Dashboard
│   ├── CCTV/               # Security Status Dashboard
│   └── Kitchen Equipment/  # Checkweigh, Hobart, Steambox, X-Ray
├── data/                   # Industrial Sensor Logs (CSV/XLSX)
└── README.md
🛠 Technical Stack
Backend: Python (Flask)

Data Processing: Pandas, NumPy (Sensor data normalization)

Database: SQLite3

Frontend: HTML5, CSS3 (Modular Layouts), Vanilla JavaScript (ES6+)

Visualization: Chart.js

Data Integrity: Custom "Heartbeat" engine with NaN-patching for industrial CSV reliability.

⚙️ Setup & Installation
Clone the Repository:

Bash
git clone [https://github.com/your-username/Stage-2-System.git](https://github.com/your-username/Stage-2-System.git)
cd Stage-2-System
Install Dependencies:

Bash
pip install flask pandas openpyxl numpy
Data Placement: Place PLC/Sensor output files in the /data folder. Ensure filenames match the configurations in app.py.

Run the Server:

Bash
cd backend
python app.py
Access the dashboard at http://127.0.0.1:5000.

🖥 Key Features
📡 Unified Heartbeat Engine
The Overview tab pings all 8 API endpoints every 30 seconds. It features a Status Indicator Light (Green/Red) and an Alert Banner that activates when system parameters exceed safety thresholds.

🛡 Industrial-Grade Resilience
Built to handle real-world factory data:

NaN Protection: Automatically patches invalid JSON tokens caused by sensor gaps.

CSV Tokenize Fix: Robust parsing that handles irregular metadata lines and PLC "bad lines" without crashing the server.

🔗 Deep-Link Navigation
Modular architecture allows for immediate "Investigation" by linking Overview cards directly to deep-dive sub-directories (e.g., /Utilities/Boiler/index.html).

📝 Project Status
Current Phase: Baseline Synchronization. All systems are currently reporting NORMAL status to verify connectivity. Threshold-based alerting logic is built-in and ready for final setpoint calibration.

Developed by: Jeremy Ng

Organization: SATS Food Solutions (Thailand) Co., Ltd.

Project: SFST Digital Transformation (Stage 2)
