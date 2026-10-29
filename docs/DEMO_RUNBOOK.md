# Mangaluru AI Digital Twin — Demonstration Runbook
**Project:** AI-Powered Predictive Routing and Signal Preemption in a Digital Twin Environment  
**Workspace:** `D:\AIML\Projects\Major\AI-Predictive-Traffic` & `D:\AIML\Projects\Major\MangaluruDigitalTwin3D`  
**Date:** October 2026  

---

## 1. Prerequisites & Environment Setup

Ensure the following prerequisites are installed and verified:

| Software / Tool | Required Version | Verification Command | Expected Output |
| :--- | :--- | :--- | :--- |
| **Python** | 3.11+ (or conda env) | `python --version` | Python 3.11.x or 3.12.x |
| **Eclipse SUMO** | 1.20.0+ | `sumo --version` | Eclipse SUMO Version 1.20+ |
| **Unity Editor** | Unity 6 (6000.x) URP | Unity Hub | MangaluruDigitalTwin3D loaded |
| **Web Browser** | Chrome / Edge / Firefox | Any modern browser | For Dashboard (`localhost:8000`) |

### Environment Variables
Verify that the `SUMO_HOME` environment variable is set:
```powershell
$env:SUMO_HOME
# Expected: C:\Program Files (x86)\Eclipse\Sumo or similar
```

---

## 2. Demonstration Scenarios

### Recommended Scenario: Corridor Kankanady -> Highland Hospital
- **Origin Edge:** `1089450246#0` (Kankanady bypass)
- **Destination:** Highland Hospital (`-26299202#3`)
- **Key Traffic Lights:** `9979735204`, `12811104666`, `286953320`, `298371899`
- **Observable Behaviors:**
  1. Ambulance spawns and calculates traffic-aware A* route.
  2. Approaching traffic signals switch to green dynamically ~10–15s prior to ambulance arrival.
  3. Traffic signals restore to standard cyclical programs immediately after ambulance crosses.
  4. Unity 3D mirrors ambulance position, traffic flow, and signal states in real time.
  5. Web dashboard displays real-time telemetry, ETA countdown, and preemption logs.

---

## 3. Step-by-Step Execution Guide

### Option A: Standard Full Demonstration (SUMO + Unity + Web Dashboard)

#### Step 1: Open Unity Editor (Digital Twin Frontend)
1. Launch **Unity Hub**.
2. Open the project located at `D:\AIML\Projects\Major\MangaluruDigitalTwin3D`.
3. In the Unity Project window, navigate to `Assets/Scenes/`.
4. Double-click **`SampleScene`** to open it.
5. Click the **Play** button at the top of the Unity Editor.
   - *Status:* Unity is now actively listening on UDP ports 5005 (Ambulance), 5006 (Traffic), 5007 (Signals), 5008 (Route), and 5010 (Telemetry).

#### Step 2: Start SUMO Controller & Telemetry Bridge (Backend)
Open a PowerShell terminal in the project directory:
```powershell
cd D:\AIML\Projects\Major\AI-Predictive-Traffic
python visualization/unity_bridge.py --gui
```
*(Note: Omit `--gui` if you wish to run SUMO headlessly in the background without the 2D SUMO window).*

**Expected Terminal Output:**
```text
============================================================
STARTING SUMO -> UNITY BRIDGE
============================================================
Starting UDP server, targeting Unity at 127.0.0.1:5005
Listening for commands from Unity on port 5009
Initializing AI Controller...
[SYSTEM] Starting Web Dashboard API on port 8000...
[SYSTEM] Opening Web Dashboard in Browser...
[HH:MM:SS] Entering simulation loop...
```

#### Step 3: Trigger Ambulance Dispatch
- **Via Web Dashboard:**  
  The browser automatically opens `http://localhost:8000/dashboard`.  
  Select **Highland Hospital** or **Athena Hospital** from the dropdown and click **Dispatch Ambulance**.
- **Via Unity In-Game UI:**  
  Click the onscreen **Dispatch** button on the Unity dashboard overlay.

---

### Option B: Bounded Headless Demonstration (Fast Academic Verification)

If Unity is not running or if you need an immediate, reproducible validation of the full AI pipeline:
```powershell
cd D:\AIML\Projects\Major\AI-Predictive-Traffic
python controller/test_mangaluru_full_ai.py
```
This self-contained test executes 3 distinct scenarios:
1. Scenario 1: Heavy Congestion with dynamic A* rerouting to Highland Hospital (-36.7s improvement).
2. Scenario 2: Moderate Congestion to KMC Hospital.
3. Scenario 3: Baseline traffic to Highland Hospital.

**Expected Terminal Output:**
```text
============================================================
MANGALURU FULL AI VALIDATION
============================================================
A* Rerouting: PASS
ML ETA: PASS
Hospital Arrival: PASS
OVERALL: PASS
SUCCESS: All AI pipeline components validated for multiple hospitals.
```

---

### Option C: Standalone Web Dashboard & RBAC Authentication

To launch and demonstrate the authenticated Web Dashboard interface independently:
```powershell
cd D:\AIML\Projects\Major\AI-Predictive-Traffic
$env:PYTHONPATH="."
uvicorn api.main:app --host 0.0.0.0 --port 8000
```
Open a browser and navigate to:
```
http://localhost:8000/dashboard
```

**Demonstration Credentials (from `api/test_dashboard_auth.py`):**
- **Administrator:** Username: `admin` | Password: `admin123` (Full system access & telemetry)
- **Emergency Operator 1:** Username: `operator1` | Password: `op123` (Scoped to ambulance unit `AMB-01`)
- **Emergency Operator 2:** Username: `operator2` | Password: `op123` (Scoped to ambulance unit `AMB-02`)

*Security Safeguard:* Operators cannot dispatch or modify units other than their authenticated assigned vehicle. All 19 security and RBAC unit tests can be validated with:
```powershell
python -m pytest api/test_dashboard_auth.py
```

---

## 4. Verifying Communication & Diagnostics

### Network Port Allocation

| Port | Protocol | Source | Destination | Purpose |
| :---: | :---: | :---: | :---: | :--- |
| **5005** | UDP | Python | Unity | Ambulance coordinates ($x, y, z$, speed, heading) |
| **5006** | UDP | Python | Unity | Civilian vehicle fleet positions and orientations |
| **5007** | UDP | Python | Unity | Signalized junction light states (Red, Yellow, Green) |
| **5008** | UDP | Python | Unity | Active A* route coordinate polyline |
| **5009** | UDP | Unity | Python | Command channel (dispatch, hospital selection, manual congestion) |
| **5010** | UDP | Python | Unity | High-frequency telemetry packets |
| **8000** | HTTP/WS | Browser | Python | FastAPI Web Dashboard UI and WebSocket stream |

### How to Verify UDP Activity
In PowerShell:
```powershell
Get-NetUDPEndpoint -LocalPort 5005,5006,5007,5008,5009,5010
```

---

## 5. Troubleshooting & Recovery

| Issue | Root Cause | Solution |
| :--- | :--- | :--- |
| **`TraCIException: Connection refused`** | Stale SUMO process already bound to port | Run: `Stop-Process -Name sumo* -Force` and restart the script. |
| **`Address already in use: 8000`** | Stale uvicorn process running | Run: `Get-Process python \| Stop-Process -Force` |
| **Unity vehicles not moving** | Unity not in Play mode or port blocked | Ensure Unity is actively playing `SampleScene`. Check Windows Firewall rules for UDP 127.0.0.1. |
| **Ambulance stops before hospital** | Road blockage injected directly on hospital edge | Use bypass route or clear blockers using dashboard button. |

---

## 6. How to Safely Stop the Demo

1. In the Python terminal: Press **`Ctrl + C`**.  
   *The script triggers `atexit` cleanup, terminates uvicorn, and closes TraCI cleanly.*
2. In the Unity Editor: Click the **Play** button to stop simulation.
