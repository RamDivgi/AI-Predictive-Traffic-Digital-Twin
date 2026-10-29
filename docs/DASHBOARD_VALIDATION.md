# AI-Powered Predictive Routing and Signal Preemption in a Digital Twin Environment — Dashboard Validation Report

**Project Name:** AI-Powered Predictive Routing and Signal Preemption in a Digital Twin Environment  
**Corridor:** Mangaluru Kankanady Corridor  
**Validation Date:** October 27, 2026  
**Test Suites:** `api/test_dashboard_auth.py` (19 automated tests) & `api/test_api.py` (6 core endpoints)  

---

## 1. Executive Summary

The **AI-Powered Predictive Routing and Signal Preemption in a Digital Twin Environment** dashboard has been refined, validated, and verified against all functional, visual, and architectural requirements. All automated test suites passed with a **100% success rate (19/19 tests in the auth & UI structure suite, 6/6 endpoints in the API suite)**.

### Primary Refinements Validated
1. **Standardized Project Title:** Consistent across HTML `<title>`, header branding, login card, and system documentation: *"AI-Powered Predictive Routing and Signal Preemption in a Digital Twin Environment"*.
2. **Navigation Order & Default Tab:** Arranged strictly in the order of **Dispatch &rarr; Live Simulation &rarr; Trip History**, with **Dispatch** active immediately upon successful login.
3. **Emergency Dispatch Action:** The primary dispatch button is designated **"Emergency Dispatch"** (`aria-label="Emergency Dispatch"` and `title="Emergency Dispatch"`).
4. **Signal-Free 2D Live Simulation:** Traffic signal dots, signal markers, and phase overlays were cleanly removed from the 2D canvas cartography. The underlying SUMO traffic light controller, `/signals` API, WebSocket streaming, and Unity UDP 5007 communication remain 100% active.
5. **Clean Login Screen:** The login card accepts Operator Full Name, Username, Password, and Assigned Ambulance (`AMB-01`, `AMB-02`, `AMB-03`). The "One-Click Demo Accounts" section has been removed completely, preventing automatic credential fill.
6. **Backend Anti-Tampering:** Session-bound ambulance assignment prevents client tampering with `HTTP 403 Forbidden`.

---

## 2. Automated Test Execution Results

### Test Suite: `api/test_dashboard_auth.py`
Command: `python -m pytest api/test_dashboard_auth.py -v`  
Environment: Python 3.11.5, pytest-9.1.1, FastAPI TestClient  

| # | Test Case Name | Target Behavior | Result | Status |
| :---: | :--- | :--- | :--- | :---: |
| 1 | `test_password_hashing` | PBKDF2-HMAC-SHA256 (100k rounds, unique salt) | Correctly hashes & verifies passwords | **PASS** |
| 2 | `test_health_endpoint` | Backend health & simulation status check | HTTP 200, status: ok | **PASS** |
| 3 | `test_demo_accounts_endpoint` | Query demo account metadata & roles | HTTP 200, 3 accounts returned | **PASS** |
| 4 | `test_login_invalid_credentials` | Rejection of bad password | HTTP 401 Unauthorized | **PASS** |
| 5 | `test_login_valid_credentials` | Login with demo dispatcher credentials | HTTP 200, access token issued | **PASS** |
| 6 | `test_login_with_operator_and_assigned_ambulance` | Login with operator name & assigned ambulance | HTTP 200, binds operator & unit | **PASS** |
| 7 | `test_dispatch_uses_session_assigned_ambulance` | Dispatch omits ambulance in body | Automatically dispatches session unit | **PASS** |
| 8 | `test_dispatch_blocks_tampered_ambulance` | Client alters ambulance in request | Backend blocks with 403 Forbidden | **PASS** |
| 9 | `test_unauthenticated_dispatch_blocked` | Dispatch attempt without session token | HTTP 401 Unauthorized | **PASS** |
| 10 | `test_viewer_role_dispatch_blocked` | Viewer/Evaluator dispatch attempt | HTTP 403 Forbidden | **PASS** |
| 11 | `test_viewer_role_sim_control_blocked` | Viewer/Evaluator simulation reset attempt | HTTP 403 Forbidden | **PASS** |
| 12 | `test_dispatcher_role_allowed_dispatch` | Dispatcher issues dispatch command | HTTP 200 OK, trip created | **PASS** |
| 13 | `test_dispatcher_role_sim_control_blocked` | Dispatcher simulation reset attempt | HTTP 403 Forbidden | **PASS** |
| 14 | `test_admin_role_allowed_sim_control` | Traffic Admin simulation reset | HTTP 200 OK, command dispatched | **PASS** |
| 15 | `test_ambulances_fleet_endpoint` | Query fleet registry | HTTP 200, configured units returned | **PASS** |
| 16 | `test_trip_history_and_analytics` | Retrieve audited trips and aggregated metrics | HTTP 200, history list returned | **PASS** |
| 17 | `test_logout` | Session revocation | HTTP 200, token removed from store | **PASS** |
| 18 | `test_dashboard_html_structure_and_terminology` | Verifies exact title, tab order, Emergency Dispatch button, no demo buttons, no signal layer toggle | All DOM criteria validated | **PASS** |
| 19 | `test_signals_backend_operational_after_canvas_removal` | Verifies `/signals` returns active traffic lights after removal of canvas signal icons | 55 active signals verified in backend | **PASS** |

**Summary: 19 passed, 0 failed in 4.69 seconds.**

---

### Core API Validation: `api/test_api.py`
Command: `python api/test_api.py`  
Live Backend Instance: `http://127.0.0.1:8000`  

- `GET /health` &rarr; Status 200 (Pass, simulation active)
- `GET /state` &rarr; Status 200 (Pass, telemetry sync active)
- `GET /ambulance` &rarr; Status 200 (Pass, telemetry fields populated)
- `GET /traffic` &rarr; Status 200 (Pass, edge speeds monitored)
- `GET /signals` &rarr; Status 200 (Pass, 55 active Mangaluru TLS junctions)
- `GET /decisions` &rarr; Status 200 (Pass)

**Result: API VALIDATION: PASS**

---

## 3. Runtime Verification Status

1. **Browser Dashboard:**  
   Fully verified at runtime. HTTP 200, 3-tab navigation (Dispatch default), Emergency Dispatch button operational, session ambulance locked, and 2D canvas displaying road network without signal markers.
2. **Python / SUMO Simulation:**  
   Fully verified at runtime via `unity_bridge.py` and TraCI. Dynamic A* routes generated, ambulance inserted into SUMO network, and telemetry streamed via WebSockets.
3. **Unity 3D Engine (`MangaluruDigitalTwin3D`):**  
   The UDP bridge emits packets across ports 5005–5010. Unity scene runtime acceptance was independently validated in Phase 2; during web headless testing, Unity Editor was passive.
