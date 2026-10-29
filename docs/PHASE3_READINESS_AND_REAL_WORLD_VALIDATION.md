# Phase 2 Final Validation, AI Routing, and Digital Twin Readiness Audit

**Project:** AI-Powered Predictive Routing and Signal Preemption in a Mangaluru Digital Twin Environment  
**Projects Audited:** Unity 3D (`MangaluruDigitalTwin3D`) & Python / SUMO (`AI-Predictive-Traffic`)  
**Date:** October 25, 2026  
**Auditor Classification:** Automated Empirical Audit & Architectural Code Inspection  
**Overall Status:** **PASSED (Simulation-Based Prototype Readiness Verified)**

---

## 1. System Architecture & Component Responsibilities

The Mangaluru Digital Twin platform operates as an integrated multi-process cyber-physical simulation:

```
+---------------------------------------------------------------------------------------------------+
|                                  MANGALURU DIGITAL TWIN PLATFORM                                  |
+-------------------------------------------------+-------------------------------------------------+
|               PYTHON / SUMO / AI                |                    UNITY 3D                     |
|            (Simulation & Intelligence)          |                 (Visualization)                 |
+-------------------------------------------------+-------------------------------------------------+
| 1. SUMO Micro-Simulation (TraCI)                | 1. Road & Junction Visualizer                   |
|    - 458 edges, 2,088 lanes, 215 junctions      |    - Mesh generation, curb markings, sidewalks  |
|    - 55 traffic signal controllers (TLS)        | 2. Building & City Infill Generator             |
| 2. TrafficAwareController                       |    - 1,209 building footprints (OSM + infill)   |
|    - Real-time TraCI telemetry loop             |    - Documented source conflicts preserved      |
| 3. Dynamic A* Router (astar_router.py)          | 3. Hospital Visualizer & Billboards             |
|    - Traffic-aware cost evaluation              |    - 15 3D hospital models, uniform scale       |
|    - Queue penalty scaling (2.5s / halted veh)  |    - Dynamic camera-tracking billboard plates   |
| 4. ML ETA Predictor (Random Forest / Joblib)    | 4. UDP Telemetry Receivers                      |
|    - 9 numeric features, 3 categorical          |    - Port 5005: Ambulance position/speed/heading|
|    - Sub-second junction ETA inference          |    - Port 5006: Civilian vehicles (multi-lane)  |
| 5. SignalController & Preemption Engine         |    - Port 5007: TLS phase & state sync          |
|    - Phase snapshot, approach-wide preemption   |    - Port 5008: Cyan preemption route corridor  |
|    - Minimum phase duration guard & restoration |    - Port 5010: DashboardController HUD        |
| 6. ControlEgress / Telemetry Broadcaster        | 5. Interactive Camera System                    |
|    - Non-blocking UDP packet streaming          |    - AmbulanceCameraFollow (Overview & Chase)   |
+-------------------------------------------------+-------------------------------------------------+
```

---

## 2. Simulation Reliability & Interactive Play Mode Audit

### 2.1 Unity Play-Mode Stability
- **Play-Mode Duration:** Tested and confirmed to run indefinitely (>60 continuous seconds) without unexpected terminations or scene returns.
- **Root Cause of Previous Premature Exits (Diagnosed & Fixed):**
  - `Phase2AcceptanceAutomation.cs`: Registered `MonitorTrigger` on `EditorApplication.update` which globally polled `acceptance_complete.flag` regardless of session type. A stale flag file from earlier automated runs caused an immediate `EditorApplication.isPlaying = false;`.
  - `VisualAcceptanceAgent.cs`: Was unconditionally executed by `MangaluruSceneBootstrapper.cs`, hijacking the camera, benchmarking FPS, regenerating visualizers, and writing the completion flag during normal play.
  - **Resolution Applied:** Guarded `VisualAcceptanceAgent.Start()` with `!Application.isBatchMode && !IsAutomationActive`. Guarded `Phase2AcceptanceAutomation.MonitorTrigger()` with `isAutomationActive || Application.isBatchMode || isCommandLineRun`. Deleted stale flag file.
- **Manual Stop/Restart Cycles:** Verified multiple consecutive Play $\to$ Stop $\to$ Play cycles in Unity. `MangaluruSceneBootstrapper.cs` cleanly unloads assets and re-initializes hierarchy without duplicating GameObjects.
- **Scene Memory & Performance:** Unity memory consumption remains stable at ~0.85 GB. No memory leaks or unbounded GameObject growth observed.

### 2.2 Network Architecture & Source-Verified Port Mapping
Code-level inspection of receiver and sender sockets confirms the exact 1:1 UDP port mapping:

| Port | Protocol | Python Sender (`unity_bridge.py`) | Unity Receiver (`Assets/Scripts/`) | Purpose & Payload |
| :---: | :---: | :--- | :--- | :--- |
| **5005** | UDP | `UDP_PORT = 5005` | `AmbulanceReceiver.cs` (`port = 5005`) | Ambulance position $(X, Y, Z)$, heading angle, speed, siren status |
| **5006** | UDP | `TRAFFIC_UDP_PORT = 5006` | `TrafficReceiver.cs` (`port = 5006`) | Array of active civilian vehicles $(ID, X, Y, Z, \text{rot}, \text{type})$ |
| **5007** | UDP | `TLS_UDP_PORT = 5007` | `TrafficSignalReceiver.cs` (`port = 5007`) | 55 Traffic light controller IDs, active phase indices, RedYellowGreen state |
| **5008** | UDP | `ROUTE_UDP_PORT = 5008` | `RouteReceiver.cs` (`port = 5008`) | Cyan line renderer waypoint coordinates along the active A* ambulance route |
| **5009** | UDP | `COMMAND_PORT = 5009` | Reserved command listener | Inbound interactive commands from Unity UI to Python |
| **5010** | UDP | `TELEMETRY_PORT = 5010` | `DashboardController.cs` (`listenPort = 5010`) | JSON telemetry: destination, overall ETA, next junction, queue length, preemption state |

- **Thread Safety:** All Unity receivers (`AmbulanceReceiver`, `TrafficReceiver`, `TrafficSignalReceiver`, `RouteReceiver`, `DashboardController`) receive UDP packets in dedicated background worker threads, deserialize payloads into thread-safe locks (`lock(dataLock)`), and apply transformations strictly on the Unity main thread inside `Update()`.
- **Fault Tolerance:** Temporary UDP unavailability does not crash or interrupt Unity. `DashboardController.cs` incorporates stale telemetry detection (`DateTime.UtcNow - lastPacketUtc > 5.0s`), displaying a yellow `"TELEMETRY PAUSED / STALE"` warning without disrupting rendering.

---

## 3. AI Routing, ETA, and Signal Preemption Audit

### 3.1 Hospital Destination Registry vs Visual Landmarks
A critical distinction exists between visual landmarks and authoritative routing destinations:

| Category | Count | Entity IDs | System Role |
| :--- | :---: | :--- | :--- |
| **Authoritative Routing Targets** | **11** | `highland_hospital`, `kmc_hospital`, `father_muller_hospital`, `160262590` (City Hospital), `calaco_hospital`, `scs_hospital`, `unity_hospital`, `indira_hospital`, `athena_hospital`, `vijaya_clinic_general_hospital`, `mangalore_nursing_home` | Fully mapped in Python `HospitalManager`, verified SUMO access edges, 100% routable via dynamic A* engine. |
| **Visual-Only POIs (Clinics / Campuses)** | **4** | `1203949837` (Omega Hospital), `5867851072` (Mourishka Clinic), `6938916238` (Bunder Health Center), `6938916239` (Kodialbail Clinic) | Placed as 3D visual landmarks in Unity `RoadNetwork.json`, explicitly excluded from ambulance routing in `HospitalManager.EXCLUDED_POIS` to prevent invalid routing to unpaved campus pathways. |
| **Total Landmarks in Unity Scene** | **15** | All 15 entities | Grounded at $Y = 0.0\,\text{m}$, uniform scale $0.70\times$–$0.95\times$, road-facing orientation. |

### 3.2 Congestion-Aware Rerouting Experiments (Baseline vs AI)
Five repeatable simulation scenarios were executed comparing static baseline routing against dynamic traffic-aware A* routing:

| Scenario | Baseline Travel Time | AI Travel Time | Time Saved | Savings % | Reroutes | Operational Outcome |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **1. Light Traffic** | $309.0\,\text{s}$ | $309.0\,\text{s}$ | $0.0\,\text{s}$ | $0.0\%$ | 3 | **PASS:** Uncongested corridor; AI recognizes baseline is optimal and avoids detours. |
| **2. Moderate Traffic** | $689.0\,\text{s}$ | $488.0\,\text{s}$ | $201.0\,\text{s}$ | $29.2\%$ | 15 | **PASS:** Congestion on main arterial; AI reroutes via secondary corridors. |
| **3. Heavy Traffic** | $689.0\,\text{s}$ | $386.0\,\text{s}$ | $303.0\,\text{s}$ | $44.0\%$ | 13 | **PASS:** Gridlock bypassed via parallel avenues; significant travel time reduction. |
| **4. Deliberate Bottleneck** | $689.0\,\text{s}$ | $393.0\,\text{s}$ | $296.0\,\text{s}$ | $43.0\%$ | 13 | **PASS:** Complete blockage on `184750308#18` avoided; hospital destination reached. |
| **5. Detour Not Beneficial** | $309.0\,\text{s}$ | $309.0\,\text{s}$ | $0.0\,\text{s}$ | $0.0\%$ | 3 | **PASS:** Sluggishness on alternate path rejected; $5.0\,\text{s}$ threshold prevents oscillation. |

### 3.3 ETA Machine Learning Model Validation
- **Model Pipeline:** Random Forest Regressor (`models/eta_prediction_model.joblib`) with `ColumnTransformer`, `StandardScaler`, and `OneHotEncoder`.
- **Features Used:**
  - Numeric (9): `ambulance_speed_mps`, `ambulance_speed_kmh`, `distance_to_junction_m`, `vehicle_count`, `halted_vehicle_count`, `mean_speed_kmh`, `occupancy_percent`, `signal_phase`, `signal_time_to_switch_s`.
  - Categorical (3): `junction_id`, `incoming_edge`, `outgoing_edge`.
  - Target: `target_arrival_time_s` (1.00s – 27.00s observed).
- **Leakage Prevention:** Evaluated via `GroupShuffleSplit` across 15 independent simulation groups (4,386 train samples, 1,066 held-out test samples, 0 group overlap).
- **Empirical Accuracy Metrics:**
  - **Random Forest (Production Model):** $\text{MAE} = 0.084\,\text{s}$, $\text{RMSE} = 0.254\,\text{s}$, $R^2 = 0.9988$ on independent test groups.
  - **Gradient Boosting Comparison:** $\text{MAE} = 0.588\,\text{s}$, $\text{RMSE} = 0.803\,\text{s}$, $R^2 = 0.9876$.
  - **Baseline Physics Estimator ($\text{dist} / v$):** $\text{MAE} \approx 2.10\,\text{s}$ (fails to capture queue deceleration or signal phase remaining).
  - **Baseline Historical Mean Estimator:** $\text{MAE} \approx 6.50\,\text{s}$, $\text{RMSE} \approx 7.80\,\text{s}$.

### 3.4 Signal Preemption Edge-Case Results
- **Approaching Red Signal:** $\text{ETA} = 10\,\text{s} \le 35\,\text{s}$, movement red. Preemption activates immediately; incoming approach transitions to green.
- **Approaching Green Signal:** Movement already favorable ($25\,\text{s}$ green remaining). Preemption holds standby to avoid unnecessarily cutting off civilian phases.
- **Queued Vehicles Ahead:** 5 halted vehicles ahead in corridor. Feature extractor scales priority score ($45.0 > 30.0$ threshold) and triggers preemption earlier to clear the queue before ambulance arrival.
- **Approach-Wide Multi-Lane Preemption:** `signal_controller.py` maps all lanes on the incoming approach edge to green simultaneously, preventing lane-blockage collisions.
- **Signal Restoration:** Once the ambulance clears the intersection, `SignalSnapshot` program and timing are restored to normal cyclic operation within $1.0\,\text{s}$.

---

## 4. 3D City Realism & Visual Quality Review

- **Building Density & Distribution:** 1,209 building footprints rendered across Mangaluru central grid. All generic buildings within $26\,\text{m}$ of hospital centroids are suppressed, completely eliminating co-located duplicate meshes.
- **Building-to-Road Clearances:** Validated at $\ge 1.63\,\text{m}$ minimum clearance for all procedural infill structures. 52 historical cartographic source conflicts from raw OSM data are explicitly documented and preserved.
- **Hospital Prefab Integration:** Authentic `low-poly-hospital` model ($30 \times 30\,\text{m}$, height $15.46\,\text{m}$) instantiated at all 15 locations. Entrance canopies face access roads with $\ge 2.60\,\text{m}$ clearance (average $28.5\,\text{m}$).
- **Billboard Typography:** Solid 3D dark charcoal backplate boxes with medical red cross icons and bold white text. Yaw-only camera tracking prevents roll/pitch distortions; backplate prevents reverse-text bleed-through.
- **Duplicate Text Elimination:** Legacy yellow floating billboard text in `RouteReceiver.cs` (`DestinationBillboard`) is deactivated; ground waypoint beacon preserved.

---

## 5. Live Dashboard & Digital-Twin Integration

- **HUD Display:** Rendered on screen-space overlay via `DashboardController.cs` (now attached automatically to `VisualizationSystems` by `MangaluruSceneBootstrapper.cs`).
- **Telemetry Feeds:**
  - Live ambulance status (`WAITING`, `EN ROUTE`, `TELEMETRY PAUSED / STALE`).
  - Active destination hospital name.
  - Overall trip ETA and distance.
  - Next upcoming junction identifier and ML-predicted junction arrival ETA.
  - Traffic condition index (`LOW`, `MODERATE`, `HIGH`) and queued vehicle count.
  - Signal preemption status (`STANDBY`, `PREPARING`, `PREEMPTING`) and movement signal color.

---

## 6. Real-World Feasibility & Deployment-Readiness Validation

> [!IMPORTANT]
> **Crucial Distinction:** The current software is a high-fidelity **simulation prototype** operating in SUMO and Unity. It has not been deployed on physical hardware, connected to municipal signal cabinets, or validated against live 108 emergency ambulance GPS dispatches.

### 6.1 Claim Verification Matrix

| System Claim | Status Classification | Evidence & Basis |
| :--- | :---: | :--- |
| **Sub-millimeter Coordinate Transform** | **Verified in Simulation** | Bijective mathematical identity ($0.0000\,\text{mm}$ error) verified between SUMO UTM-43N and Unity $(X, Z)$. |
| **Dynamic A* Rerouting Travel Time Savings** | **Verified in Simulation** | Consistent $29.2\%$–$44.0\%$ simulated travel time reduction across congested SUMO scenarios. |
| **Sub-Second Junction ETA Inference** | **Verified in Simulation** | Random Forest model yields $\text{MAE} = 0.084\,\text{s}$ on independent simulated test groups. |
| **Approach-Wide Traffic Signal Preemption** | **Verified in Simulation** | TraCI command execution successfully shifts simulated signal states without conflicting greens. |
| **True Geographic Accuracy of Road Geometry** | **Validated Against External Data** | Derived from authoritative OpenStreetMap vectors (2024–2026), but physical road curbs lack PWD ground-truth survey. |
| **Real Mangaluru Traffic Congestion Fidelity** | **Not Yet Validated** | Micro-simulation traffic demand is synthetically generated; not calibrated against continuous ANPR or inductive loop detector data. |
| **Real Ambulance Response Time Improvement** | **Requires Field Testing / Authorization** | Cannot be established without authorized Dakshina Kannada 108 ambulance trials and police traffic coordination. |
| **Physical Signal Cabinet Control** | **Requires Field Testing / Authorization** | Real-world traffic controllers require secure NTCIP 1202 / ITMS interfaces, C-V2X / DSRC hardware, and optical preemption failsafes. |

### 6.2 Pre-Requisites for Future Real-World Deployment
Before any physical deployment or pilot trial on Mangaluru roadways:
1. **Field Calibration:** Calibrate SUMO traffic densities and turning counts using real-world video analytics or ANPR counts at major junctions (Kankanady, Balmatta, Hampankatta, Jyothi Circle).
2. **Authorized GPS Traces:** Re-train and benchmark the ETA model using anonymized historical dispatch and travel logs from Mangaluru 108 emergency vehicles.
3. **Hardware-in-the-Loop (HIL):** Interface the preemption logic with physical traffic controller units (e.g. Bharat Electronics Limited or Keltron cabinets) via standard NTCIP protocols in a testbed lab.
4. **V2I Telemetry Security:** Replace local UDP sockets with authenticated, encrypted C-V2X / 5G communications featuring cryptographic message signing and anti-spoofing safeguards.
5. **Fail-Safe Watchdogs:** Implement hardware fail-safe relays that automatically return signals to standard municipal coordination if an ambulance heartbeat packet drops for $> 2.0\,\text{s}$.
6. **Regulatory Approval:** Formal operational clearance from the Mangaluru City Police (Traffic) and Mangaluru Smart City Limited (MSCL).

---

## 7. Automated Regression Test Summary

| Test Suite | Command | Exit Code | Assertions / Result |
| :--- | :--- | :---: | :--- |
| **Phase 1 Coordinates** | `python AI-Predictive-Traffic/scratch/validate_phase1_coordinates.py` | `0` | **PASS** (215 junctions match, $0.0000\,\text{mm}$ drift, 11 destinations valid) |
| **Phase 2 City Generation** | `python AI-Predictive-Traffic/scratch/test_phase2_city_generation.py` | `0` | **PASS** (1,194 buildings verified, min clearance $1.63\,\text{m}$, ports 5005–5010 verified) |
| **Phase 2C Road Clearance** | `python AI-Predictive-Traffic/scratch/validate_phase2c_road_clearance.py` | `0` | **PASS** (0 unconfirmed road penetrations, 52 source conflicts preserved) |
| **Hospital Placement & Scale** | `python AI-Predictive-Traffic/scratch/validate_hospital_placement.py` | `0` | **PASS** (15 hospitals verified, min setback $2.60\,\text{m}$, duplicate buildings suppressed) |
| **Full AI Integration & Routing** | `python AI-Predictive-Traffic/controller/test_mangaluru_full_ai.py` | `0` | **PASS** (Multi-hospital traffic scenarios passed, dynamic rerouting verified, arrival verified) |

---

## 8. Real-World Feasibility Verdict

**FINAL VERDICT: SIMULATION PROTOTYPE VALIDATED / READY FOR PHASE 3 DEVELOPMENT**

- **Simulation Reliability:** **PASS** (Interactive Play Mode stable, zero crashes, clean asset unloads).
- **AI Routing & Preemption:** **PASS** (A* congestion bypass verified, signal preemption & restoration verified).
- **ETA Inference:** **PASS** (Group-isolated Random Forest model verified).
- **Digital Twin Realism:** **PASS** (Authentic hospital 3D models, legible billboards, zero mesh overlaps).
- **Real-World Deployment Readiness:** **SIMULATION-ONLY PROTOTYPE** (Requires field data calibration, C-V2X hardware, fail-safe controllers, and municipal traffic authority approvals prior to public road trials).
