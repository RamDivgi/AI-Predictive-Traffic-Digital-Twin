# AI VALIDATION AUDIT: ETA MODEL LEAKAGE & INDEPENDENT ROUTING EXPERIMENTS

**Project:** AI-Powered Predictive Routing and Signal Preemption in a Mangaluru Digital Twin Environment  
**Date of Audit:** October 25, 2026  
**Auditor:** Autonomous Systems & AI Architecture Pair Programmer  
**Target Environments:**
- Python / SUMO Project: `D:\AIML\Projects\Major\AI-Predictive-Traffic`
- Unity 3D Project: `D:\AIML\Projects\Major\MangaluruDigitalTwin3D`

---

## Executive Summary & Classification Matrix

| Area | Status | Key Audit Finding |
|---|---|---|
| **Target Leakage** | **PASS** | No direct target column or future arrival timestamps leaked into input features. |
| **Model Training Provenance** | **FAIL (Identified)** | The production model (`models/eta_prediction_model.joblib`) was trained in `ml_pipeline.py` using random row `train_test_split`, causing temporal and cross-trajectory leakage. This explains why it achieved 0.017s MAE on the test set. |
| **Data Duplication** | **PARTIAL** | 727 exact duplicate rows (13.33%) exist in `data/ml_training_dataset.csv` due to multi-run concatenation without seed indexing. |
| **ETA Target Definition** | **VERIFIED** | Target is **time to next junction** (1.0s – 27.0s, mean 10.41s), **NOT** total ambulance trip duration to the hospital. |
| **ETA Model Accuracy** | **PASS (Clean Re-eval)** | Deduplicated clean GroupShuffleSplit: **MAE = 0.074s**, **RMSE = 0.200s**, **R² = 0.9993**, **MedAE = 0.002s**, **P90 = 0.269s**, **MAPE = 3.32%**. 5-Fold Group CV: **Mean MAE = 0.333 ± 0.465s**, **Mean RMSE = 0.969 ± 1.299s**, **Mean R² = 0.9424**. |
| **Congestion Rerouting Claims** | **DISPROVEN / RECLASSIFIED** | Previous "29.2%–44.0% travel time savings" were calculated against **simulation timeouts (689.0s)** where the baseline ambulance was 100% blocked and never completed the trip. In moderate flow (2.5 m/s), AI detours actually increased travel time by -16.3% (-57.0s). AI routing's true strength is **gridlock resilience** (100% arrival rate vs 0% baseline arrival rate). |
| **Signal Preemption & Unity Integration** | **PASS** | Unity Play Mode remains stable (>60s), telemetry ports 5005-5010 verified, and hospital models remain correctly placed. |
| **Real-World Deployment Readiness** | **NOT VALIDATED (Simulation Only)** | Software is an offline synthetic simulation prototype; no physical hardware, C-V2X, or real-world traffic data validation has occurred. |

---

## 1. Inventory of the Actual ETA Pipeline

### 1.1 Code and Artifact Inventory
1. **Model File:** `D:\AIML\Projects\Major\AI-Predictive-Traffic\models\eta_prediction_model.joblib`
2. **Dataset File:** `D:\AIML\Projects\Major\AI-Predictive-Traffic\data\ml_training_dataset.csv` (5,452 samples, 20 columns)
3. **Raw Dataset File:** `D:\AIML\Projects\Major\AI-Predictive-Traffic\data\training_dataset.csv` (7,787 samples, 18 columns)
4. **Data Generation Code:** `controller/generate_training_dataset.py` calling `controller/multi_scenario_collector.py`
5. **Training Pipeline:** `controller/ml_pipeline.py`
6. **Validation Pipeline:** `controller/ml_validation.py`
7. **Production Inference:** `controller/predictive_eta.py` (`predict_eta()`, `calculate_junction_etas()`)

### 1.2 Prediction Task & Target Variable
- **Target Variable:** `target_arrival_time_s`
- **Units:** Seconds (float, strictly positive)
- **Range:** Min = 1.00s, Max = 27.00s, Mean = 10.41s, Std = 7.29s, Median = 9.00s.
- **Definition:** The elapsed time between the current simulation time step and the timestamp when the ambulance arrives within 3.0 meters of the upcoming junction along its approach.
- **Critical Distinction:** The model predicts **junction traversal time** along immediate approaches. It does **not** predict the total remaining trip time to the hospital.

### 1.3 Feature Parity & Availability Audit

| Feature Name | Type | In Production? | Source in SUMO / Python | Availability at Prediction Time | Leakage Assessment |
|---|---|---|---|---|---|
| `ambulance_speed_mps` | `float` | Yes | `traci.vehicle.getSpeed("ambulance")` | Instantaneous (live) | Low risk |
| `ambulance_speed_kmh` | `float` | Yes | `speed_mps * 3.6` | Instantaneous (live) | Low risk (linear scaling) |
| `distance_to_junction_m` | `float` | Yes | `junction.distance_from_ambulance_m` | Route distance to junction node | Low risk; physically bounded |
| `vehicle_count` | `int` | Yes | `traci.edge.getLastStepVehicleIDs(edge)` | Instantaneous edge state | Low risk |
| `halted_vehicle_count` | `int` | Yes | Count of vehicles with speed < 0.1 m/s | Instantaneous edge state | Low risk |
| `mean_speed_kmh` | `float` | Yes | `traci.edge.getLastStepMeanSpeed(edge) * 3.6` | Prior step average | Low risk |
| `occupancy_percent` | `float` | Yes | `traci.edge.getLastStepOccupancy(edge)` | Prior step average | Low risk |
| `signal_phase` | `int` | Yes | `traci.trafficlight.getPhase(junction_id)` | Instantaneous phase index | Low risk |
| `signal_time_to_switch_s`| `float` | Yes | `getNextSwitch() - getTime()` | Controller schedule state | Medium risk (assumes fixed/known cycle) |
| `junction_id` | `str` | Yes | `junction.junction_id` | Topologically known from route | Low risk |
| `incoming_edge` | `str` | Yes | `junction.incoming_edge` | Topologically known from route | Low risk |
| `outgoing_edge` | `str` | Yes | `junction.outgoing_edge` | Topologically known from route | Low risk |

**Excluded from Features (Verified):**
- `ambulance_eta_s` (Physics baseline calculation) — Excluded in `prepare_features()`.
- `simulation_time` (Global simulation clock) — Excluded in `prepare_features()`.
- `target_is_observed` (Filtering flag) — Excluded in `prepare_features()`.

---

## 2. Leakage and Provenance Audit Findings

### 2.1 Target Leakage
- **Direct Formula Inspection:**
  In `ml_pipeline.py`:
  ```python
  arrival_candidates = group[group["distance_to_junction_m"] <= 3.0]
  arrival_time = arrival_candidates["simulation_time"].min()
  target = arrival_time - current_time
  ```
  The target is strictly constructed from future observation timestamps. None of the feature columns encode `arrival_time` or the target directly.
- **Feature Correlations:**
  - `distance_to_junction_m`: **+0.9251** (Strongest predictor)
  - `occupancy_percent`: **-0.5049**
  - `vehicle_count`: **-0.4762**
  - `signal_phase`: **-0.3626**
  - `signal_time_to_switch_s`: **-0.2536**
  - `halted_vehicle_count`: **-0.2320**
  - `ambulance_speed_mps`: **+0.2454**
  - `mean_speed_kmh`: **-0.0630**

The high correlation (+0.9251) with `distance_to_junction_m` is physically authentic: with signal preemption active and ambulances driving near maximum speed (~13.8 m/s), distance along a short fixed 200m approach is the dominant physical determinant of traversal time.

### 2.2 Provenance Leakage in the Production Model
A major training leakage defect was discovered during the audit of `controller/ml_pipeline.py`:
- In `ml_pipeline.py` (Line 563), the saved model `models/eta_prediction_model.joblib` was trained using:
  ```python
  X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.20, random_state=42)
  ```
- **Consequence:** `train_test_split` shuffled individual rows randomly without grouping. Observations from timestamp $t$ went to training, while timestamp $t+1$ of the *exact same vehicle on the same approach* went to testing.
- **Effect on Previous Metrics:** When `ml_validation.py` loaded `models/eta_prediction_model.joblib` and evaluated it against its 3 "held-out" test groups (`C__normal`, `E__heavy`, `B__congested`), the saved model had **already trained on 80% of the rows from those exact groups**. This caused the model to achieve an artificial test error of **0.017 seconds**.

### 2.3 Duplicate Data Analysis
- In `data/training_dataset.csv`: **854 duplicate rows (10.97%)**.
- In `data/ml_training_dataset.csv`: **727 duplicate rows (13.33%)**.
- **Root Cause:** `generate_training_dataset.py` executed `multi_scenario_collector.py` for 25 runs and appended the outputs. Because the simulation is deterministic for identical traffic conditions and the ambulance travels identical routes, duplicate state vectors were recorded.
- **Remediation:** Deduplication in `scratch/evaluate_eta_independent.py` removed all 727 exact duplicate rows (retaining 4,725 unique rows).

### 2.4 Simulation Network Provenance
- `data/ml_training_dataset.csv` contains only 3 junction IDs (`B`, `C`, `E`) and 5 scenarios (`low`, `normal`, `moderate`, `heavy`, `congested`), totaling 15 groups.
- The dataset was generated on `simulation/network/test.net.xml` (a toy 3-junction synthetic grid), **not** on the full 215-junction Mangaluru road network (`mangaluru_ai.net.xml.gz`).
- While this toy network establishes proof-of-concept ETA learning, the model cannot be claimed to have learned topological characteristics of Mangaluru's specific junctions.

---

## 3. Independent ETA Model Evaluation

To eliminate all data leakage and duplication, `scratch/evaluate_eta_independent.py` performed an independent evaluation using:
1. Complete deduplication (4,725 unique samples).
2. Clean `GroupShuffleSplit` (80% train / 20% test, with strictly 0 group overlap).
3. Fresh model training fitted solely on the training partition.
4. Comprehensive baseline comparisons receiving identical inputs.

### 3.1 Held-Out Group Evaluation Results

| Estimator / Model | MAE (s) | RMSE (s) | R² | MedAE (s) | P90 (s) | MAPE (%) | Mean Bias (s) |
|---|---|---|---|---|---|---|---|
| **Historical Mean Baseline** | 6.316 | 7.409 | -0.0001 | 6.314 | 11.314 | 156.76% | +0.068 |
| **Physics ($d / v$) Baseline** | 3.420 | 4.853 | 0.5709 | 2.274 | 9.025 | 84.82% | +2.085 |
| **Linear Regression** | 0.967 | 1.269 | 0.9707 | 0.749 | 2.048 | 24.05% | -0.466 |
| **Gradient Boosting** | 0.649 | 0.871 | 0.9862 | 0.452 | 1.437 | 11.23% | -0.335 |
| **Random Forest (Clean Split)** | **0.074** | **0.200** | **0.9993** | **0.002** | **0.269** | **3.32%** | **+0.009** |
| *Production Saved Model\** | *0.017* | *0.074* | *0.9999* | *0.000* | *0.044* | *0.71%* | *-0.005* |

*\*Note: Production Saved Model was contaminated by random row-splitting during original training.*

### 3.2 5-Fold Group Cross-Validation
To test generalization across all 15 scenario groups rather than a single favorable split, 5-Fold Group Cross-Validation was conducted:

| Fold | Test Groups | Test Samples | MAE (s) | RMSE (s) | R² |
|---|---|---|---|---|---|
| **Fold 1** | 4 groups | 1,025 | 0.020 | 0.049 | 1.0000 |
| **Fold 2** | 3 groups | 995 | 0.067 | 0.200 | 0.9993 |
| **Fold 3** | 3 groups | 980 | 0.236 | 0.811 | 0.9881 |
| **Fold 4** | 2 groups | 785 | 1.253 | 3.515 | 0.7261 |
| **Fold 5** | 3 groups | 940 | 0.089 | 0.268 | 0.9988 |
| **Mean ± Std** | **All 15 Groups** | **4,725** | **0.333 ± 0.465** | **0.969 ± 1.299** | **0.9424 ± 0.1083** |

### 3.3 Residual Analysis (Random Forest on Held-Out Test Set)
- **Mean Residual (Bias):** +0.0089 s
- **Residual Std Dev:** 0.2001 s
- **Range:** [-1.4148 s, +1.2141 s]
- **Accurate within ±0.20s:** 879 samples (**88.34%**)
- **Under-prediction (< -0.50s):** 18 samples (**1.81%**)
- **Over-prediction (> +0.50s):** 28 samples (**2.81%**)

### 3.4 Verdict on the Reported 0.084-second MAE
- The previously reported **0.084s MAE** is **empirically reproduced** on the specific random-state 80/20 GroupShuffleSplit (evaluating to 0.074s on deduplicated data).
- **However**, this accuracy applies strictly to **short junction approach traversal (1.0s – 27.0s)** in a 3-junction synthetic grid.
- When tested across diverse groups via 5-Fold Group CV, the realistic generalizable error is **0.333 seconds MAE**, with certain difficult scenario combinations reaching **1.253 seconds MAE**.

---

## 4. Congestion-Aware Routing Independent Experiments

### 4.1 Audit of the Previous Savings Claim (29.2% – 44.0%)
In earlier reports, the baseline ambulance travel time in congested scenarios was recorded as exactly **689.0 seconds**.
- **Investigation:**
  In `scratch/evaluate_rerouting_experiments.py`, `max_steps` was set to 700. When severe congestion or roadblocks were applied to edge `184750308#18`, the static baseline ambulance became permanently gridlocked and **never reached the destination (`reached = False`)**.
  `travel_time = 700.0 - 11.0 = 689.0 seconds`.
- **Finding:** The reported savings of 29.2%–44.0% were **not** calculated between two completed trips. They were calculated between a **simulation timeout** (where the baseline ambulance failed to arrive) and an AI trip that reached the hospital.

### 4.2 Rigorous Repeated Experiment Matrix
To measure true performance, `scratch/evaluate_rerouting_matrix.py` executed 30 full SUMO simulations across 5 scenarios and 3 distinct random seeds (Seeds 42, 101, 2024).

The scenarios evaluated:
1. **Light Traffic:** Clear road network, baseline free-flow speed.
2. **Moderate Slowdown:** Speed limit reduced to 2.5 m/s on corridor `184750308#18` (traffic moves slowly, but does **not** stop completely).
3. **Severe Congestion:** Speed limit reduced to 0.5 m/s with 2 blocker vehicles on `184750308#18`.
4. **Roadblock Bottleneck:** Speed limit set to 0.001 m/s with 3 blocker vehicles (complete blockage).
5. **Detour Not Beneficial:** Alternate corridor `1369161863#1` slowed to 1.0 m/s with 1 blocker; primary corridor remains clear.

### 4.3 Measured Experimental Results

| Scenario | Base Reached | AI Reached | Mean Base Time (s) | Mean AI Time (s) | Mean Stopped Base (s) | Mean Stopped AI (s) | Travel Time Saved (s) | Travel Time Savings (%) | Mean Reroutes | Operational Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| **1. Light Traffic** | 3/3 (100%) | 3/3 (100%) | 309.3 | 320.3 | 8.0 | 12.3 | -11.0 | **-3.6%** | 4.3 | Completed (-3.6%) |
| **2. Moderate Slowdown (2.5 m/s)** | 3/3 (100%) | 3/3 (100%) | 350.0 | 407.0 | 28.0 | 41.7 | -57.0 | **-16.3%** | 5.0 | Completed (-16.3%) |
| **3. Severe Congestion (0.5 m/s)** | 0/3 (0%) | 3/3 (100%) | 689.0 (Timeout) | 455.7 | 567.0 | 54.3 | +233.3 | **+33.9%\*** | 12.0 | **Base Stuck (100% Failure vs 100% AI Arrival)** |
| **4. Roadblock Bottleneck** | 0/3 (0%) | 3/3 (100%) | 689.0 (Timeout) | 455.0 | 572.0 | 51.0 | +234.0 | **+34.0%\*** | 12.7 | **Base Stuck (100% Failure vs 100% AI Arrival)** |
| **5. Detour Not Beneficial** | 3/3 (100%) | 3/3 (100%) | 311.3 | 325.7 | 9.7 | 14.0 | -14.3 | **-4.6%** | 4.3 | Completed (-4.6%) |

*\*Savings in Scenarios 3 & 4 represent improvement over a timed-out, permanently stuck baseline.*

### 4.4 Key Insights & Behavioral Analysis
1. **The Gridlock Resilience Value:**
   In Scenarios 3 and 4, the baseline ambulance has a **0% completion rate** (stuck indefinitely). The AI controller senses the stopped queue, re-evaluates the network graph via A*, computes a bypass route, and delivers the patient to Highland Hospital in ~455 seconds (100% completion rate). This is the true operational benefit of the system.
2. **The "Detour Penalty" in Moderate Traffic:**
   In Scenario 2 (2.5 m/s slowdown), the baseline ambulance stayed on the direct arterial road and reached the hospital in 350.0 seconds. The AI controller detected the slowdown and detoured into winding residential sidestreets, which added 57.0 seconds of travel time (-16.3%). 
   *Recommendation:* Increase the rerouting threshold `min_improvement_s` from 5.0s to 15.0s or incorporate road hierarchy penalties to prevent detouring onto lower-capacity sidestreets for minor delays.
3. **Route Stability and Oscillation:**
   The hysteresis threshold (`min_improvement_s = 5.0s`, `min_improvement_percent = 2.0%`, `cooldown_s = 15.0s`) successfully suppressed pathological flip-flopping. In Scenario 5, when an alternate road was congested, the controller evaluated the route and repeatedly logged:
   `[REROUTING] Reroute decision: NO. Reason: Improvement below threshold.`

---

## 5. Signal Preemption and Digital Twin Integration Audit

### 5.1 Signal Preemption Verification
Preemption edge cases were verified against live TraCI traffic lights:
- **Approach Preemption:** Approaching red signals immediately transition to green for the ambulance approach.
- **Standby on Green:** Approaching green signals are held in phase without unnecessary cycling.
- **Multi-Lane Mapping:** Approaches sharing a physical geometry receive synchronized green phases.
- **Program Recovery:** Following ambulance exit, normal traffic light cycle programs are restored within 1.0 simulation second.

### 5.2 Unity 3D Project Verification
- **Play Mode Stability:** Verified active Play mode > 60 continuous seconds; Scene reload clean.
- **Port Mapping:**
  - `5005`: Ambulance live telemetry (position, speed, heading)
  - `5006`: Civilian vehicle telemetry
  - `5007`: Traffic light phase states
  - `5008`: Active route waypoints
  - `5010`: Real-time HUD Dashboard telemetry
- **Hospital Landmarks:** 15 visual hospital landmarks rendered with dedicated 3D models and orientation towards road frontages.
- **Stale Telemetry Safeguard:** `DashboardController.cs` automatically detects telemetry interruptions exceeding 5.0s and displays `"TELEMETRY PAUSED / STALE"` warning in the HUD.

---

## 6. Regression Testing Verification

All 5 core regression test suites were independently executed and achieved Exit Code 0:

| Test Suite | Command | Exit Code | Outcome |
|---|---|---|---|
| **Phase 1 Coordinates** | `python scratch/validate_phase1_coordinates.py` | 0 | **PASS** (215 junctions match, 0.0000mm drift, scale = 1.000000) |
| **Phase 2 City Generation** | `python scratch/test_phase2_city_generation.py` | 0 | **PASS** (1,209 buildings, min clearance 1.63m, telemetry ports 5005-5010 verified) |
| **Phase 2C Road Clearance** | `python scratch/validate_phase2c_road_clearance.py` | 0 | **PASS** (0 unconfirmed road penetrations, 52 source conflicts preserved) |
| **Hospital Placement** | `python scratch/validate_hospital_placement.py` | 0 | **PASS** (15 hospitals verified, min clearance 2.60m, generic buildings suppressed) |
| **Full AI Integration** | `python controller/test_mangaluru_full_ai.py` | 0 | **PASS** (Multi-hospital A* rerouting bypasses congestion, ambulance arrives) |

---

## 7. Real-World Feasibility and Deployment Boundaries

### 7.1 What the Current System Demonstrates (Simulation Prototype)
- Demonstrates a closed-loop digital twin linking SUMO microscopic traffic simulation to Unity 3D visualization.
- Demonstrates dynamic A* pathfinding incorporating live TraCI edge travel time estimates.
- Demonstrates emergency vehicle approach detection and automated green-wave preemption.
- Demonstrates supervised learning for short-range junction approach ETA prediction.

### 7.2 What is NOT Validated in the Real World
1. **Uncalibrated Traffic Demand:** Vehicle flows, origins, destinations, and congestion patterns in SUMO are synthetically generated and have not been calibrated against empirical Mangaluru traffic counts.
2. **Synthetic ETA Model:** The ML model was trained on a 3-junction synthetic grid (`test.net.xml`), not real GPS traces from Mangaluru 108 emergency service ambulances.
3. **No Physical Traffic Controller Interface:** The preemption logic issues TraCI software API calls; it does not interface with NTCIP 1202, 2070, or TS2 traffic signal controller cabinets.
4. **No Real-World Communication:** Telemetry relies on local loopback UDP; it does not account for real-world cellular packet loss, DSRC/C-V2X latency, or GPS multipath errors in dense urban corridors.

### 7.3 Mandatory Prerequisites for Safe Real-World Deployment
- Formal authorization and data-sharing agreements with Mangaluru City Police and emergency medical services.
- Real-world GPS trajectory data collection for ETA model retraining.
- Deployment of secure, authenticated C-V2X roadside units (RSUs) and on-board units (OBUs).
- Hardware-in-the-loop (HIL) testing with fail-safe hardware watchdog relays that prevent conflicting greens or signal controller lockup.

---

## 8. Audit Conclusion and Verdict

1. **ETA Model Accuracy:** The 0.084s MAE is reproducible on single held-out test groups, but represents **short-range junction traversal time (1-27s)** rather than full trip ETA. On 5-Fold cross validation across all groups, true expected error is **0.333s MAE**.
2. **Training Leakage Remediation:** The production training script `ml_pipeline.py` must be updated to use `GroupShuffleSplit` or `GroupKFold` by default to prevent cross-trajectory contamination.
3. **Rerouting Value Clarification:** The dynamic router should be characterized as an **incident/gridlock bypass engine** (preventing 100% mission failure during severe blockages) rather than an optimizer for minor speed fluctuations.
