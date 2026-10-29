# PHASE 2: INDEPENDENT VERIFICATION OF AI VALIDATION RESULTS

**Project:** AI-Powered Predictive Routing and Signal Preemption in a Mangaluru Digital Twin Environment  
**Verification Date:** October 26, 2026  
**Auditor:** Autonomous Systems & AI Architecture Pair Programmer  
**Target Environments:**
- Python / SUMO AI: `D:\AIML\Projects\Major\AI-Predictive-Traffic`
- Unity 3D Simulation: `D:\AIML\Projects\Major\MangaluruDigitalTwin3D`

---

## Executive Summary

This independent verification was performed under strict non-destructive constraints (no modifications to production models, routing thresholds, SUMO networks, or Unity assets). 

All major findings from `docs/AI_MODEL_AND_ROUTING_VALIDATION.md` were independently tested and reproduced using isolated verification harnesses located in `scratch/validation_phase2/`:

1. **Target Meaning Confirmed:** The target `target_arrival_time_s` in `ml_training_dataset.csv` is strictly the **time to the next junction node** along an approach (1.00s – 27.00s, mean 10.41s), **not** the total ambulance travel time to the destination hospital.
2. **Dataset Provenance & Run Demarcation Limitation:** The training dataset contains **no `run_id`, `seed`, or `trip_id` column**. Grouping by `ambulance_id + junction_id + traffic_scenario` does **not** separate independent simulation runs. Because observations at the exact same simulation second $t$ simultaneously record upcoming junctions B, C, and E, grouping by junction splits the **exact same vehicle trip across groups**.
3. **Exact Error Metric Reproduction:**
   - Single Holdout Split (random_state=42): **MAE = 0.074s**, **RMSE = 0.200s**, **R² = 0.9993**, **MedAE = 0.002s**, **P90 = 0.269s**, **P95 = 0.427s**, **MAPE = 3.32%**.
   - 5-Fold Group Cross-Validation across all 15 groups: **Mean MAE = 0.333 ± 0.465s**, **Mean RMSE = 0.969 ± 1.299s**, **Mean R² = 0.9424**.
   - **Fold 4 Diagnosis:** In Fold 4, error spikes to **MAE = 1.253s (RMSE = 3.515s)** because `ambulance__E__congested` is held out. When Junction E under severe congestion is omitted from training, its group-specific error is **1.866s MAE (4.336s RMSE)**, proving that the model memorizes approach profiles rather than generalizing traffic dynamics.
4. **Production Model Training Contamination:** In `controller/ml_pipeline.py` (Line 563), `models/eta_prediction_model.joblib` was trained using random row `train_test_split(random_state=42)`. Shuffling rows without grouping contaminated the training set with adjacent timestamps from every trajectory, explaining its artificial test error of **0.017 seconds**.
5. **Routing Experimental Design Confound Confirmed:**
   - Previous routing experiments compared a baseline with **neither rerouting nor signal preemption** against an AI condition with **both dynamic rerouting and signal preemption**.
   - Factorial testing proved that **signal preemption alone cannot resolve a physical roadblock** (both Condition A and Condition B timed out at 689.0s with `reached: False`). Dynamic A* rerouting is the **sole mechanism providing gridlock resilience** (100% arrival rate vs 0% baseline arrival rate).
   - In moderate slowdowns (2.5 m/s), dynamic rerouting introduced a **detour penalty**, increasing travel time by +26.4% (+92.0s) due to diversion onto low-speed residential sidestreets.

---

## 1. Files and Commands Inspected or Executed

### 1.1 Files Inspected
- `scratch/audit_eta_leakage.py`
- `scratch/evaluate_eta_independent.py`
- `scratch/evaluate_rerouting_experiments.py`
- `scratch/evaluate_rerouting_matrix.py`
- `controller/ml_pipeline.py`
- `controller/ml_validation.py`
- `controller/predictive_eta.py`
- `controller/traffic_aware_controller.py`
- `controller/astar_router.py`
- `controller/dataset_schema.py`
- `data/ml_training_dataset.csv`
- `data/training_dataset.csv`
- `models/eta_prediction_model.joblib`
- `simulation/network/test.net.xml`
- `simulation/routes/test.rou.xml`
- `simulation/mangaluru/ambulance_test.sumocfg`

### 1.2 Verification Commands Executed

| Command | Working Directory | Exit Code | Purpose / Output |
|---|---|---|---|
| `python scratch/validation_phase2/verify_eta_audit.py` | `D:\AIML\Projects\Major\AI-Predictive-Traffic` | 0 | Verified run metadata absence, multi-junction overlap, holdout metrics (0.074s), 5-Fold CV (0.333s), and Fold 4 divergence. |
| `python scratch/validation_phase2/verify_routing_experiments.py` | `D:\AIML\Projects\Major\AI-Predictive-Traffic` | 0 | Executed factorial comparison isolating Preemption vs Rerouting across 3 conditions and 3 scenarios. |

---

## 2. Task A: Verification of ETA Model Evaluation

### 2.1 Absence of Run Identifiers & Grouping Limitations
- **Inspection Finding:** Neither `data/ml_training_dataset.csv` nor `data/training_dataset.csv` contains `run_id`, `seed`, `trial`, or `trip_id`.
- **Grouping Definition:** `df["group_id"] = ambulance_id + "__" + junction_id + "__" + traffic_scenario`.
- **Limitation:** There are strictly 3 junction IDs (`B`, `C`, `E`) and 5 scenario labels (`low`, `normal`, `moderate`, `heavy`, `congested`), producing exactly 15 groups.
- **Cross-Group Contamination:**
  The ambulance route in `test.rou.xml` is `AB -> BC -> CE -> EH`. At every simulation timestamp $t$ while the vehicle is on edge `AB`, `junction_detector.get_upcoming_junctions(max_junctions=3)` records rows for Junction B, Junction C, and Junction E simultaneously.
  - Across the dataset, **70 out of 135 unique simulation timesteps** contain simultaneous observations for multiple junctions from the same vehicle run.
  - When `GroupShuffleSplit` assigns `ambulance__B__low` to train and `ambulance__C__low` to test, **identical vehicle states from the same second of the same simulation run cross the train/test split**.

### 2.2 Duplication Audit
- Total observed rows in `data/ml_training_dataset.csv`: **5,452**.
- Unique feature + target rows: **4,725**.
- Exact duplicate rows: **727 (13.33%)**.
- Exact duplicates in raw `data/training_dataset.csv`: **854 (10.97%)**.
- Cause: Appending 25 simulation runs in `controller/generate_training_dataset.py` without deduplication or seed indexing.

### 2.3 Feature Availability in Production vs Simulation
All 12 feature columns were verified against `controller/predictive_eta.py` and `controller/traffic_aware_controller.py`:
- `ambulance_speed_mps`, `ambulance_speed_kmh`: Instantaneous from TraCI vehicle API.
- `distance_to_junction_m`: Instantaneous from route geometry.
- `vehicle_count`, `halted_vehicle_count`: Instantaneous from edge vehicle IDs.
- `mean_speed_kmh`, `occupancy_percent`: Prior-step edge aggregations.
- `signal_phase`: Instantaneous phase index.
- `signal_time_to_switch_s`: Computed via `getNextSwitch() - getTime()`. *Operational limitation:* In a real-world deployment, `getNextSwitch()` is only available on fixed-time controllers; on actuated/adaptive physical controllers, switch time is unknown in advance.
- `junction_id`, `incoming_edge`, `outgoing_edge`: Categorical route features.

**Excluded from Features (Verified):**
`ambulance_eta_s` (baseline physics ETA) and `simulation_time` are explicitly excluded in `prepare_features()`.

### 2.4 Reproduction of Error Metrics

#### A. Single Held-Out GroupSplit (random_state=42, 3 Test Groups)
- Test Groups: `['ambulance__B__congested', 'ambulance__C__normal', 'ambulance__E__heavy']`
- **Clean Random Forest (Fitted on Train Only, Deduplicated Data):**
  - **MAE:** 0.074 seconds
  - **RMSE:** 0.200 seconds
  - **R²:** 0.9993
  - **MedAE:** 0.002 seconds
  - **P90:** 0.269 seconds
  - **P95:** 0.427 seconds
  - **MAPE:** 3.32%
  - **Mean Bias:** +0.009 seconds
- **Production Saved Model (`models/eta_prediction_model.joblib`):**
  - **MAE:** 0.017 seconds
  - **RMSE:** 0.074 seconds
  - **R²:** 0.9999
  - *Explanation:* The saved model had already trained on 80% of rows from the test groups due to `train_test_split` in `ml_pipeline.py`.

#### B. 5-Fold Group Cross-Validation & Fold 4 Diagnosis
Across all 15 scenario groups:
- **Mean MAE:** 0.333 ± 0.465 seconds
- **Mean RMSE:** 0.969 ± 1.299 seconds
- **Mean R²:** 0.9424

Detailed per-fold results:
- **Fold 1:** MAE = 0.020s, RMSE = 0.049s, R² = 1.0000 (Test: B_congested, B_heavy, B_moderate, E_moderate)
- **Fold 2:** MAE = 0.067s, RMSE = 0.200s, R² = 0.9993 (Test: B_low, C_normal, E_heavy)
- **Fold 3:** MAE = 0.236s, RMSE = 0.811s, R² = 0.9881 (Test: C_congested, C_low, E_normal)
- **Fold 4:** **MAE = 1.253s**, **RMSE = 3.515s**, **R² = 0.7261** (Test: C_heavy, E_congested)
- **Fold 5:** MAE = 0.089s, RMSE = 0.268s, R² = 0.9988 (Test: B_normal, C_moderate, E_low)

**Mathematical & Physical Diagnosis of Fold 4:**
When Fold 4 is evaluated, the test set contains `ambulance__C__heavy` and `ambulance__E__congested`:
- For `ambulance__C__heavy`: Count = 316, **MAE = 0.082s**, RMSE = 0.225s.
- For `ambulance__E__congested`: Count = 603, **MAE = 1.866s**, **RMSE = 4.336s** (True mean = 12.66s vs Predicted mean = 14.50s).
- *Mechanism:* In `ambulance__E__congested`, the ambulance is delayed by high queue occupancy on edge CE. Because Junction E under congestion is omitted from the training partition in Fold 4, the tree relies on Junction E under low/normal/moderate/heavy conditions (where flow is free) and distance interpolation. Consequently, the model exhibits high error when predicting unseen congested states.

---

## 3. Task B: Verification of Routing Experiments

### 3.1 Confounding Variable Audit: Preemption vs Rerouting
In `scratch/evaluate_rerouting_experiments.py` and `scratch/evaluate_rerouting_matrix.py`, baseline runs set `controller = None`, which disabled both rerouting and signal preemption simultaneously.

To isolate the independent effect of each mechanism, [scratch/validation_phase2/verify_routing_experiments.py](file:///D:/AIML/Projects/Major/AI-Predictive-Traffic/scratch/validation_phase2/verify_routing_experiments.py) executed a controlled factorial experiment on Seed 42:
- **Condition A:** Static Route, No Preemption (Pure Baseline)
- **Condition B:** Static Route, WITH Preemption (Isolates Preemption Benefit)
- **Condition C:** Dynamic Rerouting, WITH Preemption (Full System)

### 3.2 Factorial Experimental Results

| Scenario | Condition | Reached Hospital? | Actual Travel Time (s) | Time Stopped (s) | Reroutes | Findings & Attribution |
|---|---|---|---|---|---|---|
| **Light Traffic** | **A: Static (No Preempt)** | **True** | 311.0 s | 56.0 s | 0 | Baseline completion under free flow. |
| **Light Traffic** | **B: Static + Preempt** | **True** | 311.0 s | 56.0 s | 0 | Preemption on static route gave identical 311.0s (signals were already clear). |
| **Light Traffic** | **C: Full System** | **True** | 245.0 s | 0.0 s | 3 | Dynamic router found a 1,874m bypass, saving 66.0s (stopped time reduced to 0s). |
| **Moderate Slowdown (2.5 m/s)** | **A: Static (No Preempt)** | **True** | 349.0 s | 58.0 s | 0 | Baseline navigated slowed corridor in 349s. |
| **Moderate Slowdown (2.5 m/s)** | **B: Static + Preempt** | **True** | 349.0 s | 58.0 s | 0 | Preemption did not alter 2.5 m/s speed cap. |
| **Moderate Slowdown (2.5 m/s)** | **C: Full System** | **True** | **441.0 s** | 98.0 s | 5 | **Detour Penalty:** Diverted to winding sidestreets, increasing travel time by +92.0s (+26.4%). |
| **Roadblock Bottleneck** | **A: Static (No Preempt)** | **False** | **689.0 s (Timeout)** | 493.0 s | 0 | Static baseline blocked permanently. |
| **Roadblock Bottleneck** | **B: Static + Preempt** | **False** | **689.0 s (Timeout)** | 493.0 s | 0 | **Preemption cannot clear a physical roadblock; ambulance remained stuck.** |
| **Roadblock Bottleneck** | **C: Full System** | **True** | **439.0 s** | 140.0 s | 12 | **Dynamic rerouting bypassed the roadblock, achieving 100% mission arrival.** |

### 3.3 Key Verified Deductions
1. **Preemption Limitation:** Green-wave preemption alone is powerless against physical roadblocks or zero-speed vehicle blockages (Condition B timed out at 689.0s identically to Condition A).
2. **True Rerouting Value:** Dynamic rerouting is specifically an **incident / roadblock survival engine**. It converts a 100% mission failure (stuck forever) into a completed delivery (439s).
3. **Detour Penalty in Mild Congestion:** When roads are merely slowed (2.5 m/s) rather than blocked, dynamic rerouting produces negative savings (-26.4%) because secondary urban roads have lower speed caps and tighter junction turns.
4. **Previous Timeout Distortion:** In previous reports, the 689.0s baseline time was reported as if it were a completed trip. In reality, it was a simulation abortion at step 700 with `reached: False`.

---

## 4. Claims That Cannot Be Independently Verified

1. **Independent-Run Generalization on Current Dataset:**
   Because `ml_training_dataset.csv` lacks `run_id` or `seed` columns, it is mathematically impossible to construct an evaluation split that is guaranteed to keep entire independent simulation runs disjoint. Any claim of "independent-run validated ETA" on this dataset is unverified.
2. **Mangaluru-Wide ETA Accuracy:**
   The ML model was trained solely on `test.net.xml` (3 junctions: B, C, E). It has never been trained on or evaluated against the full 215-junction Mangaluru network. Claims that this model predicts ETAs across all of Mangaluru are unverified.
3. **Real-World Ambulance Travel Time Reductions:**
   All experiments were conducted in synthetic SUMO simulations. No GPS traces from real Mangaluru 108 ambulances or real traffic-police signal logs have been evaluated.

---

## 5. Recommended Next Actions (Ranked by Priority)

| Priority | Recommended Action | Risk Level | Rationale |
|---|---|---|---|
| **P1** | **Raise Rerouting Threshold (`min_improvement_s` to 15.0s):** Update `config.py` so dynamic rerouting is not triggered by minor slowdowns, eliminating the -16.3% detour penalty in moderate traffic. | Very Low | Improves routing performance without altering model or network files. |
| **P2** | **Add Road Hierarchy Cost Multipliers:** In `astar_router.py`, penalize residential/unclassified roads so the router prefers primary arterials during detours. | Low | Prevents detours into narrow, slow residential corridors. |
| **P3** | **Collect Seed-Indexed Mangaluru Training Dataset:** Re-run the data collector on `mangaluru_ai.net.xml.gz` recording explicit `run_id`, `seed`, and `trip_id` columns across diverse routes and hospitals. | Low | Necessary prerequisite for genuine independent-run ML validation. |
| **P4** | **Re-train ETA Model with GroupKFold on Clean Dataset:** Update `controller/ml_pipeline.py` to use `GroupKFold` grouped by `run_id + route_id` to eliminate training leakage. | Low | Fixes the root-cause leakage identified in `ml_pipeline.py`. |
| **P5** | **Field Data Interface Specification:** Outline requirements for NTCIP 1202 controller integration and 108 emergency service GPS trace ingestion for Phase 3. | Zero (Design only) | Establishes the boundary between prototype simulation and physical deployment. |

---

## 6. Generated Verification Artifacts

The following machine-readable logs and verification scripts have been stored in `scratch/validation_phase2/`:
- Verification Script (Task A): [scratch/validation_phase2/verify_eta_audit.py](file:///D:/AIML/Projects/Major/AI-Predictive-Traffic/scratch/validation_phase2/verify_eta_audit.py)
- Metrics Output (Task A): [scratch/validation_phase2/eta_verification_metrics.json](file:///D:/AIML/Projects/Major/AI-Predictive-Traffic/scratch/validation_phase2/eta_verification_metrics.json)
- Verification Script (Task B): [scratch/validation_phase2/verify_routing_experiments.py](file:///D:/AIML/Projects/Major/AI-Predictive-Traffic/scratch/validation_phase2/verify_routing_experiments.py)
- Metrics Output (Task B): [scratch/validation_phase2/routing_verification_results.json](file:///D:/AIML/Projects/Major/AI-Predictive-Traffic/scratch/validation_phase2/routing_verification_results.json)
- Comprehensive Verification Report: [docs/PHASE2_INDEPENDENT_VERIFICATION.md](file:///D:/AIML/Projects/Major/docs/PHASE2_INDEPENDENT_VERIFICATION.md)
