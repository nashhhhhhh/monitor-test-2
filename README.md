# Stage 2 System – Industrial Monitoring Command Center

A centralized industrial IoT dashboard designed for **SATS Food Solutions (Thailand)**.  
This system aggregates data from diverse sources—including **SQLite databases**, **real-time CSV logs from factory sensors**, and **Excel status reports**—into a unified, actionable **Industrial Command Center**.

---

## 🚀 Overview

The **Stage 2 System** provides a high-level **System Health** overview that monitors **8 critical factory domains**.  
It enables operators to move seamlessly from a bird’s-eye view of factory health to deep-dive analytics for individual departments with a single click.

### Key Monitored Domains

- **Power Systems (MDB)**  
  Energy load profiles and generator runtimes

- **Water Treatment (WTP)**  
  Quality metrics such as residual chlorine and supply pressure

- **Cold Chain (Temperature)**  
  Real-time monitoring of room temperatures via SQLite

- **Production (Spiral Blast Freezer)**  
  Internal freezer temperatures and conveyor throughput

- **Utilities**  
  Boiler gas/steam consumption and air compressor flow & dew point

- **Security**  
  CCTV online status monitoring via automated log parsing

- **Wastewater (WWTP)**  
  Effluent inflow temperatures and plant energy usage

---

## 🏗 Project Structure

```plaintext
Stage-2-System/
├── backend/                # Flask Server & Data Processing
│   ├── app.py              # Main API & Routing
│   ├── temperature_api.py  # SQLite Temperature Logic
│   └── temps.db            # Local database for room sensor data
├── frontend/               # UI Layers
│   ├── Overview/           # Central Command Center (Home)
│   ├── Utilities/          # MDB, Boiler, WTP, WWTP, Air Compressor
│   ├── Spiral Blast Freezer/
│   ├── Temperature/        # Cold Chain Dashboard
│   ├── CCTV/               # Security Status Dashboard
│   └── Kitchen Equipment/  # X-Ray, Hobart, Steambox, Checkweigh
├── data/                   # Sensor Data (CSV/XLSX)
└── README.md
```

🛠 Technical Stack
Backend: Python (Flask)

Data Science: Pandas, NumPy
(sensor data normalization and NaN patching)

Database: SQLite3

Frontend: HTML5, CSS3 (modular layouts), Vanilla JavaScript (ES6+)

Visualization: Chart.js

Reliability:
Custom Heartbeat Sync Engine with JSON NaN-patching for industrial data integrity

⚙️ Installation & Setup
1. Clone the Repository
git clone https://github.com/your-username/Stage-2-System.git
cd Stage-2-System
2. Install Python Dependencies
pip install flask pandas openpyxl numpy
3. Initialize the Environment
Ensure all sensor data files are placed in the /data directory and follow the naming conventions expected by app.py.

4. Run the Server
cd backend
python app.py
The system will be available at:
http://127.0.0.1:5000

🖥 Dashboard Features
1. Unified Command Center
The home dashboard features a Heartbeat Engine that pings all subsystems every 30 seconds.

Status Light

🟢 Green – Normal

🔴 Red – Critical / Attention Required

⚪ Gray – Offline

Drill-Down Navigation
Each status card acts as a portal to its corresponding department dashboard.

2. Industrial Data Integrity
Designed to handle real-world industrial data challenges:

NaN Protection
Automatically patches invalid JSON tokens (NaN) caused by sensor gaps

Tokenized Error Handling
Robust CSV parsing that skips corrupted metadata lines from PLC outputs

3. Responsive Navigation
Shared navbar across 12+ sub-dashboards

Seamless transitions between Utilities, Production, and Kitchen Equipment

Optimized for large industrial displays and operator workstations
