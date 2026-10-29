# Phase 3 — Mangaluru-Wide ETA Dataset and Leakage-Resistant Model Validation Report

**Project:** AI-Powered Predictive Routing and Signal Preemption in a Mangaluru Digital Twin Environment  
**Execution Timestamp:** October 2026  
**Status:** **PHASE 3 COMPLETE — CANDIDATE VALIDATED & ISOLATED**  
**Preceding Audit Documents:**  
- [`docs/AI_MODEL_AND_ROUTING_VALIDATION.md`](file:///D:/AIML/Projects/Major/docs/AI_MODEL_AND_ROUTING_VALIDATION.md)  
- [`docs/PHASE2_INDEPENDENT_VERIFICATION.md`](file:///D:/AIML/Projects/Major/docs/PHASE2_INDEPENDENT_VERIFICATION.md)  

---

## 1. Executive Summary

Phase 3 addresses the fundamental limitations identified during the Phase 2 AI audit:
1. **Flawed Prior Baseline:** The legacy model's reported $\text{MAE} = 0.084\,\text{s}$ was proven to be an artifact of severe target lookahead leakage and identical trajectory memorization across micro-simulation slices.
2. **True Simulation Performance:** On the full Mangaluru road network (`mangaluru_ai.net.xml.gz`) with 213 traffic signals and 11 authoritative hospitals, an authentic, leakage-free Random Forest candidate achieves:
   - **Unseen Trip Holdout $\text{MAE} = 12.217\,\text{s}$**, $\text{RMSE} = 18.773\,\text{s}$, $\text{MedAE} = 6.560\,\text{s}$, $R^2 = 0.8692$.
   - **5-Fold Group Cross-Validation $\text{Mean MAE} = 13.057 \pm 1.870\,\text{s}$**, $R^2 = 0.8420$.
   - **Physics Baseline Comparison:** Outperforms the physical distance/effective-speed model ($\text{MAE} = 38.292\,\text{s}$) by **68.1%** and the mean baseline ($\text{MAE} = 42.312\,\text{s}$) by **71.1%**.
3. **Preservation Guarantees Maintained:**
   - The production model [`models/eta_prediction_model.joblib`](file:///D:/AIML/Projects/Major/AI-Predictive-Traffic/models/eta_prediction_model.joblib) remains **strictly untouched**.
   - Production A* routing algorithms, thresholds, Unity assets, and SUMO network geometry were **not modified**.
   - All candidate models, dataset artifacts, scripts, and logs are housed in isolated directories under `scratch/phase3_eta/`.

---

## 2. Network & Simulation Architecture Inspection

Before data collection, Task 1 inspected the complete Mangaluru network and inference dependencies:

| Asset | Path | Verified Specification |
|:---|:---|:---|
| **Full SUMO Network** | `simulation/mangaluru/mangaluru_ai.net.xml.gz` | Full-scale Mangaluru road network; 213 active Traffic Light Systems (TLS), 2,327 controlled link movements |
| **Hospital Manager** | `simulation/mangaluru/presentation_labels.add.xml` | 11 authoritative hospitals loaded with verified topological connectivity |
| **Sumo Configuration** | `simulation/mangaluru/ambulance_test.sumocfg` | High-density urban simulation with background traffic corridors |
| **Signal Cache** | `controller/signal_mapping.py` | TraCI movement mapping linking `(incoming_edge, outgoing_edge)` to `(tls_id, signal_indices)` |
| **Junction Tracker** | `controller/junction_detector.py` | Detects upcoming signalized junctions along dynamic vehicle routes |

### Network Route Discovery
Topological connectivity from 5 representative arterial origins across Mangaluru was systematically audited:
- `321397980` (North / Kadri) $\to$ `kmc_hospital`: 42 edges, 10 signalized junctions.
- `321397980` (North / Kadri) $\to$ `athena_hospital`: 44 edges, 14 signalized junctions.
- `1358315405` (Central / Kodialbail) $\to$ `indira_hospital`: 38 edges, 10 signalized junctions.
- `1089450246#0` (South / Kankanady) $\to$ `athena_hospital`: 16 edges, 11 signalized junctions.
- `-132363062` (East Arterial) $\to$ `unity_hospital`: 36 edges, 14 signalized junctions.

---

## 3. Reproducible Dataset Collection Pipeline

The Phase 3 data collector ([`scratch/phase3_eta/collector_phase3.py`](file:///D:/AIML/Projects/Major/AI-Predictive-Traffic/scratch/phase3_eta/collector_phase3.py)) was executed across the full network.

### Experimental Design Matrix
- **Corridor Origins (5):** `321397980`, `1358315405`, `1089450246#0`, `-132363062`, `1096889856`.
- **Destinations (8):** `kmc_hospital`, `athena_hospital`, `indira_hospital`, `unity_hospital`, `highland_hospital`, `father_muller_hospital`, `vijaya_clinic_general_hospital`, `calaco_hospital`.
- **Traffic Scenarios (4):**
  1. `light`: Free-flow background traffic.
  2. `moderate`: Corridor bottleneck (speed capped at 4.0 m/s).
  3. `heavy`: Congested corridor (speed capped at 2.5 m/s + 2 stopped passenger vehicles).
  4. `incident`: Severe road blockage (speed capped at 0.8 m/s + 3 blocking vehicles).
- **Seeds:** Fully configurable, deterministic random seed assignment per run (`seed = 2026 + run_idx * 17`).
- **Vehicle Collision Safeguard:** Dynamic ambulance spawned with unique ID `f"amb_p3_{run_idx}"` and default scheduled background duplicate safely decommissioned.

### Sample Identifiers & Feature Parity
Every recorded observation contains only features physically measurable at prediction time:
```python
CSV_HEADER = [
    "run_id", "seed", "trip_id", "ambulance_id", "destination_hospital",
    "route_id", "origin_edge", "traffic_scenario", "simulation_time",
    "ambulance_speed_mps", "ambulance_speed_kmh", "distance_to_junction_m",
    "distance_to_hospital_m", "vehicle_count", "halted_vehicle_count",
    "mean_speed_kmh", "occupancy_percent", "signal_phase", "signal_time_to_switch_s",
    "junction_id", "incoming_edge", "outgoing_edge",
    "target_junction_eta_s", "target_junction_observed",
    "target_hospital_eta_s", "target_hospital_observed"
]
```

### Explicit Target Separation
To eliminate mixing local and global travel times:
- `target_junction_eta_s`: Seconds until the ambulance reaches within 5.0m of the upcoming junction node or enters the junction. Flagged with `target_junction_observed = 1` only upon verified arrival.
- `target_hospital_eta_s`: Total travel time in seconds until the ambulance reaches the destination hospital edge. Flagged with `target_hospital_observed = 1` only upon verified destination completion.

---

## 4. Dataset Quality & Leakage Audit

Dataset validation was executed via [`scratch/phase3_eta/validate_dataset.py`](file:///D:/AIML/Projects/Major/AI-Predictive-Traffic/scratch/phase3_eta/validate_dataset.py), outputting [`scratch/phase3_eta/data/dataset_validation_report.json`](file:///D:/AIML/Projects/Major/AI-Predictive-Traffic/scratch/phase3_eta/data/dataset_validation_report.json):

### Summary Statistics
- **Total Raw Simulation Observations:** 30,277
- **Valid Observed Junction ETA Rows:** 13,498 (44.6% of raw observations; unreached/censored approaches filtered out)
- **Unique Simulation Runs (`run_id`):** 32
- **Unique Full Trips (`trip_id`):** 32
- **Unique Signalized Junctions:** 31
- **Exact Duplicate Rows:** 0 (0%)
- **Negative or Impossible Targets:** 0 (0%)

### Target Distribution (`target_junction_eta_s`)
- **Min:** 0.00 s | **Max:** 297.00 s
- **Mean:** 64.89 s | **Std:** 58.20 s
- **Median:** 48.00 s | **IQR:** [20.00 s, 91.00 s]
- **90th Percentile:** 154.00 s | **95th Percentile:** 193.00 s

### Representation by Scenario
| Scenario | Samples | Share (%) |
|:---|:---:|:---:|
| `moderate` | 4,412 | 32.7% |
| `light` | 4,247 | 31.5% |
| `heavy` | 2,531 | 18.8% |
| `incident` | 2,308 | 17.1% |

### Group Leakage Audit
- Split Method: `GroupShuffleSplit(n_splits=1, test_size=0.2, groups=trip_id)`
- Train: 10,851 samples across 25 independent trips.
- Test: 2,647 samples across 7 independent trips.
- **Trip ID Overlap:** **0** (Zero trip contamination).
- **Run ID Overlap:** **0** (Zero run contamination).
- **Result:** **PASSED — STRICTLY LEAKAGE FREE**.

---

## 5. Candidate Model Training & Comparative Evaluation

The candidate model was trained and evaluated via [`scratch/phase3_eta/train_candidate_model.py`](file:///D:/AIML/Projects/Major/AI-Predictive-Traffic/scratch/phase3_eta/train_candidate_model.py) without touching production files.

### 1. Holdout Evaluation on Completely Unseen Trips
Evaluated on 2,647 test samples across 7 unseen trips:

| Model / Baseline | MAE (s) | RMSE (s) | Median AE (s) | P90 Error (s) | P95 Error (s) | $R^2$ Score |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|
| **1. Mean Baseline** ($\bar{y}_{train}$) | 42.312 | 52.105 | 38.769 | 71.231 | 109.231 | -0.0074 |
| **2. Physics Baseline** ($d / v_{eff}$) | 38.292 | 55.856 | 25.375 | 94.413 | 126.056 | -0.1576 |
| **3. Ridge Regression** (StandardScaled) | 25.834 | 34.064 | 19.663 | 52.358 | 63.163 | 0.5694 |
| **4. Random Forest Candidate** | **12.217** | **18.773** | **6.560** | **31.061** | **40.317** | **0.8692** |

> [!NOTE]
> The Physics Baseline achieves a high RMSE (55.86s) and negative $R^2$ because real-world urban traffic involves queueing behind red lights and traffic congestion; constant velocity assumptions drastically break down when ambulances wait at intersections. The regularized Random Forest candidate effectively captures signal cycle and density nonlinearities, reducing MAE by 68.1%.

### 2. 5-Fold Group Cross-Validation (Across All 32 Trips)
Each fold evaluates on completely independent simulation trips:

| Fold | Test Trips | RF MAE (s) | RF RMSE (s) | RF $R^2$ | Physics MAE (s) |
|:---:|:---:|:---:|:---:|:---:|:---:|
| **Fold 1** | 6 | 15.590 | 26.002 | 0.7983 | 40.001 |
| **Fold 2** | 6 | 11.226 | 17.852 | 0.8775 | 35.227 |
| **Fold 3** | 7 | 10.591 | 15.114 | 0.9312 | 40.778 |
| **Fold 4** | 6 | 14.149 | 27.002 | 0.8032 | 42.117 |
| **Fold 5** | 7 | 13.727 | 27.815 | 0.7997 | 41.178 |
| **Average** | **32 Trips** | **13.057 ± 1.870** | **22.757 ± 5.227** | **0.8420** | **39.860 ± 2.450** |

### 3. Scenario Breakdown (Test Set)
| Scenario | Samples | RF MAE (s) | RF RMSE (s) | RF $R^2$ | Physics MAE (s) |
|:---|:---:|:---:|:---:|:---:|:---:|
| `light` | 281 | 10.068 | 14.004 | 0.7869 | 21.381 |
| `heavy` | 675 | 10.337 | 17.376 | 0.8912 | 45.630 |
| `moderate` | 1,544 | 13.161 | 19.832 | 0.8670 | 38.910 |
| `incident` | 147 | 15.042 | 21.304 | 0.7480 | 30.428 |

### 4. Feature Importances
| Feature | Importance Weight | Physical Role |
|:---|:---:|:---|
| `distance_to_junction_m` | **46.54%** | Primary distance traversal component |
| `signal_phase` | **10.53%** | Current phase of the traffic signal |
| `occupancy_percent` | **9.54%** | Density of vehicles occupying approach lanes |
| `mean_speed_kmh` | **7.99%** | Average moving speed of civilian traffic on edge |
| `ambulance_speed_mps` | **7.71%** | Instantaneous ambulance speed |
| `signal_time_to_switch_s` | **7.50%** | Time remaining before traffic light phase switch |
| `halted_vehicle_count` | **5.24%** | Number of queued vehicles waiting at red signal |
| `vehicle_count` | **4.95%** | Total volume of vehicles on incoming approach |

---

## 6. Model Artifacts & Isolation

To guarantee that production systems are unaffected, all Phase 3 candidate deliverables are saved to dedicated directories:

| Component | Path | Description |
|:---|:---|:---|
| **Raw Training Dataset** | [`scratch/phase3_eta/data/mangaluru_eta_dataset_v1.csv`](file:///D:/AIML/Projects/Major/AI-Predictive-Traffic/scratch/phase3_eta/data/mangaluru_eta_dataset_v1.csv) | 30,277 rows, 26 columns, versioned dataset |
| **Dataset Validation JSON** | [`scratch/phase3_eta/data/dataset_validation_report.json`](file:///D:/AIML/Projects/Major/AI-Predictive-Traffic/scratch/phase3_eta/data/dataset_validation_report.json) | Detailed integrity, correlation, and distribution metrics |
| **Candidate Model** | [`scratch/phase3_eta/models/mangaluru_eta_candidate.joblib`](file:///D:/AIML/Projects/Major/AI-Predictive-Traffic/scratch/phase3_eta/models/mangaluru_eta_candidate.joblib) | Isolated RandomForestRegressor candidate |
| **Candidate Feature Schema** | [`scratch/phase3_eta/models/candidate_schema.json`](file:///D:/AIML/Projects/Major/AI-Predictive-Traffic/scratch/phase3_eta/models/candidate_schema.json) | Exact 8-feature schema and hyperparameter configuration |
| **Evaluation Metrics** | [`scratch/phase3_eta/models/model_evaluation_report.json`](file:///D:/AIML/Projects/Major/AI-Predictive-Traffic/scratch/phase3_eta/models/model_evaluation_report.json) | Comprehensive cross-validation and scenario metrics |

---

## 7. Limitations & Safe Next Steps

### Identified Limitations
1. **Simulation Domain Gap:** The dataset is generated within the SUMO microscopic simulation. While SUMO captures realistic car-following (Krauss model) and traffic light schedules, real-world Mangaluru traffic exhibits informal lane-splitting, two-wheelers, and unmetered pedestrian crossings not modeled in SUMO.
2. **Signal Preemption Interaction:** The candidate ETA model was trained on standard background traffic without aggressive green corridor overrides. When active signal preemption is triggered, junction arrival times will decrease further.
3. **End-to-End Hospital ETA:** The current candidate model predicts junction-level ETA (`target_junction_eta_s`), which is the operational input required by the predictive signal preemption controller. End-to-end hospital ETA requires trajectory accumulation across sequential road edges.

### Recommended Next Safe Step
Do not directly overwrite production routing models. The next safe step is **Shadow-Mode Benchmarking**:
1. Run the candidate model in parallel with the production model inside the live simulation loop without feeding candidate outputs to the A* edge weights.
2. Log side-by-side inference latency, memory overhead, and prediction accuracy in real-time.
3. Once shadow-mode stability and latency ($\le 2\,\text{ms}$ per call) are established, present a migration plan for production promotion.
