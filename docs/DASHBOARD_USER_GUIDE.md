# AI-Powered Predictive Routing and Signal Preemption in a Digital Twin Environment — Dashboard User Guide

**Project Name:** AI-Powered Predictive Routing and Signal Preemption in a Digital Twin Environment  
**Corridor:** Mangaluru Kankanady Corridor & Road Network  
**Target URL:** `http://localhost:8000/dashboard`  
**Date:** October 2026  

---

## 1. Overview & Interface Architecture

The redesigned control-room console provides a minimal, professional interface tailored for academic demonstration, evaluation, and operational emergency dispatch.

### Core Architecture & Refinements
- **Exact Project Title:** Standardized to **AI-Powered Predictive Routing and Signal Preemption in a Digital Twin Environment** across the application header, login page, and system documents.
- **Ordered 3-Tab Workflow:** Navigation is strictly arranged in operational order:
  1. **Dispatch** (Default landing tab immediately following login)
  2. **Live Simulation** (2D network digital twin with moving vehicle and route overlays)
  3. **Trip History** (Persistent audit log of recorded journeys)
- **Signal-Free 2D Canvas:** Traffic signal icons, markers, and phase overlays are completely removed from the 2D map visualization to maintain an uncluttered emergency routing view, while the backend SUMO traffic-light controller, dynamic preemption algorithms, and Unity signal communications remain fully active.
- **Dedicated Operator Login:** Operators sign in with their Full Name, Username, Password, and Assigned Ambulance (`AMB-01`, `AMB-02`, `AMB-03`). The session securely binds the vehicle assignment and enforces role-based access control (RBAC). One-click demo autofill buttons have been completely removed.
- **Emergency Dispatch Action:** The primary dispatch button is prominently labelled **"Emergency Dispatch"**.

---

## 2. Launching the System

### Method A: Full Integrated Pipeline (SUMO + Unity Bridge + Dashboard)
Run the master bridge script from PowerShell:
```powershell
cd D:\AIML\Projects\Major\AI-Predictive-Traffic
python visualization/unity_bridge.py --gui
```
*The script initializes the AI controller, connects to SUMO, boots the FastAPI service on port 8000, and opens `http://localhost:8000/dashboard` in your browser.*

### Method B: Standalone Dashboard API
To run the dashboard independently (e.g. during frontend inspection):
```powershell
cd D:\AIML\Projects\Major\AI-Predictive-Traffic
python -m uvicorn api.main:app --port 8000
```
Open `http://localhost:8000/dashboard` in Google Chrome or Microsoft Edge.

---

## 3. Demonstration Accounts & Local Testing Credentials

Authentication uses standard library **PBKDF2-HMAC-SHA256** (100,000 rounds) with cryptographically secure salts. Pre-configured demonstration accounts for evaluation:

| Username | Password | Default Unit | Authorized Role | Capabilities |
| :--- | :--- | :--- | :--- | :--- |
| **`dispatcher`** | `dispatch123` | `AMB-01` (ALS) | **Emergency Dispatcher** | Select origin & destination hospital; execute Emergency Dispatch; toggle preemption; abort active trips; inspect trip history. |
| **`traffic_admin`**| `admin123` | `AMB-02` (BLS) | **Traffic Systems Admin** | Full access: dispatch any assigned ambulance + pause/resume/reset simulation + inject incidents + override signals. |
| **`evaluator`** | `viewer123` | `AMB-03` (MICU)| **Academic Evaluator / Viewer** | **Read-only**: Inspect live simulation telemetry, canvas map, signal states, and historical trip logs. Dispatch controls are disabled. |

*(Note: In accordance with presentation standards, one-click demo login buttons are removed from the frontend UI; operators enter credentials manually into the clean login form).*

---

## 4. Primary Operational Demonstration Workflow

### Step 1: Secure Operator Login
1. Navigate to `http://localhost:8000/dashboard`.
2. Enter your **Operator Full Name** (e.g. `Officer Vikram Rao`).
3. Enter your **Username** (`dispatcher`) and **Password** (`dispatch123`).
4. Select your **Assigned Ambulance** (`AMB-01` ALS, `AMB-02` BLS, or `AMB-03` MICU).
5. Click **Sign In & Launch Command Center**.
6. The system authenticates your credentials, binds the vehicle assignment to your session, and navigates directly to the **Dispatch** console.

### Step 2: Configure & Execute Emergency Dispatch
1. On the **Dispatch** tab, note the non-editable **Assigned Unit Card**:
   - `Assigned Unit: AMB-01 — Advanced Life Support (Father Muller Medical Base)`
   - *(The client contains no dropdown to alter the unit; backend authorization prevents tampering).*
2. **Select Incident Origin**: Choose from available pickup locations (e.g. `Base (Father Muller Road)`, `Start Point 1 (Kankanady Bypass)`).
3. **Select Destination Hospital**: Choose from available facilities (Highland Hospital, KMC Hospital, Athena Hospital).
4. **Inspect AI Recommendation**: The AI recommendation banner displays the dynamically computed optimal destination with predicted ETA. Click **Select Recommended Hospital** to apply it.
5. **Green Corridor Preemption**: Keep the preemption switch toggled **ON**.
6. Click **Emergency Dispatch**.

### Step 3: Monitor Live Simulation
1. Switch to the **Live Simulation** tab.
2. The canvas renders the complete Mangaluru road network, hospital entry gates, moving ambulance marker with interpolated heading, and active route overlay.
3. Traffic signals are omitted from the map for clean visual cartography; signal preemption continues executing in the backend and in the Unity 3D simulator.
4. Use the floating map controls:
   - **Fit**: Auto-center the network.
   - **`+` / `−`**: Zoom in and zoom out.
   - **Mouse Drag**: Pan across the Mangaluru network.

### Step 4: Audit Trip History
1. Upon vehicle arrival (or clicking **Abort Trip**), switch to the **Trip History** tab.
2. The audit table displays:
   - **Trip ID** (e.g. `TRIP-001`)
   - **Operator Name** (e.g. `Officer Vikram Rao`)
   - **Assigned Unit** (e.g. `AMB-01`)
   - **Origin & Destination Hospital**
   - **Start Time & Duration**
   - **Outcome** (`COMPLETED` or `ABORTED`)
3. Click **Logout** in the header to revoke the session token and return to the login screen.
