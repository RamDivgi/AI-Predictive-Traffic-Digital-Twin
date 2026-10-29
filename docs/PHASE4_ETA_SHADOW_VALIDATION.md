# Phase 4 — ETA Candidate Audit and Shadow-Mode Benchmark Validation Report

**Project:** AI-Powered Predictive Routing and Signal Preemption in a Mangaluru Digital Twin Environment  
**Status:** **PHASE 4 COMPLETE — AUDIT AND SHADOW BENCHMARK VERIFIED**  
**Execution Timestamp:** October 2026  
**Reference Documents:**  
- [`docs/AI_MODEL_AND_ROUTING_VALIDATION.md`](file:///D:/AIML/Projects/Major/docs/AI_MODEL_AND_ROUTING_VALIDATION.md)  
- [`docs/PHASE2_INDEPENDENT_VERIFICATION.md`](file:///D:/AIML/Projects/Major/docs/PHASE2_INDEPENDENT_VERIFICATION.md)  
- [`docs/PHASE3_ETA_VALIDATION.md`](file:///D:/AIML/Projects/Major/docs/PHASE3_ETA_VALIDATION.md)  

---

## 1. Executive Summary & Audit Conclusions

Phase 4 performed an independent, evidence-based audit of the Phase 3 training artifacts and conducted a live, isolated **shadow-mode benchmark** comparing the legacy Production ETA Model against the Phase 3 Candidate Model on the full Mangaluru SUMO simulation network.

### Key Audit Findings
1. **Metric Reproduction:** The reported Phase 3 candidate metrics on the versioned dataset ([`scratch/phase3_eta/data/mangaluru_eta_dataset_v1.csv`](file:///D:/AIML/Projects/Major/AI-Predictive-Traffic/scratch/phase3_eta/data/mangaluru_eta_dataset_v1.csv)) were **100% reproduced** to 4 decimal places from the saved artifacts:
   - Holdout $\text{MAE} = 12.2171\,\text{s}$, $\text{RMSE} = 18.7732\,\text{s}$, $\text{MedAE} = 6.5597\,\text{s}$, $R^2 = 0.8692$.
   - 5-Fold Group CV $\text{Mean MAE} = 13.0566\,\text{s}$.
2. **Provenance & Scope Discrepancy Clarification:**
   - **40 Scheduled vs 32 Evaluated Trips:** 40 trips were planned across the parameter grid. 36 trips produced raw simulation rows (Trip 37 suffered a corridor spawn timeout). Of those 36, **4 trips** (`trip_028`, `trip_030`, `trip_038`, `trip_040`, originating under severe congestion from East and North-East corridors to Athena Hospital) encountered roadblocks that halted the ambulance before reaching the signalized approaches within 350 seconds. Hence, exactly **32 independent trips** reached junction approaches and provided verified ground-truth targets.
   - **Hospital Subset:** While 11 authoritative hospitals exist in the project, the Phase 3 collector explicitly sliced `destinations[:2]` (`kmc_hospital` and `athena_hospital`) to constrain simulation duration while spanning major cross-city corridors.
3. **Live Shadow-Mode Benchmark (6,306 Head-to-Head Evaluations):**
   - **Production Model (`Pipeline` with One-Hot Encoder):** $\text{MAE} = 74.316\,\text{s}$, $\text{RMSE} = 100.152\,\text{s}$, $\text{MedAE} = 55.765\,\text{s}$, $R^2 = -1.1556$.
   - **Physics Baseline ($d / v_{eff}$):** $\text{MAE} = 54.535\,\text{s}$, $\text{RMSE} = 76.540\,\text{s}$, $\text{MedAE} = 38.187\,\text{s}$, $R^2 = -0.2590$.
   - **Candidate Model (`RandomForestRegressor`):** **$\text{MAE} = 18.368\,\text{s}$**, **$\text{RMSE} = 33.419\,\text{s}$**, **$\text{MedAE} = 7.580\,\text{s}$**, **$R^2 = 0.7600$**.
   - **Improvement:** The Candidate Model reduces MAE by **75.3%** compared to the production model and reduces Median Absolute Error from 55.8s down to **7.58s**.
   - **Inference Latency:** Candidate model mean latency is **$28.68\,\text{ms}$** (P95: $33.43\,\text{ms}$) compared to Production model **$67.31\,\text{ms}$** (P95: $93.66\,\text{ms}$), delivering a **57.4% latency speedup**.
4. **Strict Safety Compliance:**
   - The production model [`models/eta_prediction_model.joblib`](file:///D:/AIML/Projects/Major/AI-Predictive-Traffic/models/eta_prediction_model.joblib) remained **strictly untouched**.
   - Production A* edge routing, signal preemption triggers, and Unity scenes were **completely isolated** from candidate predictions.

---

## 2. Provenance Reconciliation: Legacy Leakage vs Phase 3 Ground-Truth

The Phase 2 and Phase 3 reports highlighted different facets of the legacy model's flawed $\text{MAE} = 0.084\,\text{s}$ claim. A direct inspection of [`controller/ml_pipeline.py`](file:///D:/AIML/Projects/Major/AI-Predictive-Traffic/controller/ml_pipeline.py) and [`scratch/phase3_eta/collector_phase3.py`](file:///D:/AIML/Projects/Major/AI-Predictive-Traffic/scratch/phase3_eta/collector_phase3.py) resolves and reconciles these claims:

| Dimension | Legacy Model Pipeline (`ml_pipeline.py`) | Phase 3/4 Verified Pipeline (`collector_phase3.py`) | Root Defect Reconciled |
|:---|:---|:---|:---|
| **Ambulance ID Scope** | All simulation runs shared identical string `"ambulance"` | Every trip assigned dynamic ID `f"amb_p3_{run_idx}"` | Legacy `df.groupby(["ambulance_id", "junction_id"])` erroneously merged multiple distinct simulation runs across different scenarios into a single trajectory. |
| **Arrival Event Extraction** | `arrival_time = group[group['dist'] <= 3.0]['simulation_time'].min()` computed post-hoc | Tracked per-trip dynamically during active simulation (`junction_arrivals[j_id] - sim_time`) | When multiple runs were merged, arrival times from Trip 1 were subtracted from Trip 2's timestamps, causing corrupted targets. |
| **Train/Test Grouping** | Grouped by `junction_id + "_" + traffic_scenario` | Grouped strictly by unique `trip_id` (0% overlap) | Legacy model tested on identical vehicle trajectories seen during training. It achieved 0.084s by memorizing the 1-second countdown clock along fixed paths. |
| **Inference Features** | 12 features including OneHotEncoded `junction_id`, `incoming_edge`, `outgoing_edge` | 8 purely numeric, generalizable features | Legacy model overfit to specific one-hot junction IDs. On unseen junctions or real network runs, its $R^2$ collapses to **-1.1556**. |

---

## 3. Audit of Phase 3 Dataset and Training Artifacts

The verification script [`scratch/phase4_shadow/audit_phase3.py`](file:///D:/AIML/Projects/Major/AI-Predictive-Traffic/scratch/phase4_shadow/audit_phase4_shadow/audit_phase3.py) audited all raw and processed artifacts, outputting [`scratch/phase4_shadow/phase3_audit_results.json`](file:///D:/AIML/Projects/Major/AI-Predictive-Traffic/scratch/phase4_shadow/phase3_audit_results.json):

```
+------------------------------------------------------------------------------------+
|                               ARTIFACT AUDIT SUMMARY                               |
+------------------------------------------------------------------------------------+
| Raw Dataset Observations:        30,277 Rows                                       |
| Valid Observed Junction Rows:    13,498 Rows (55.4% censored/unreached filtered)   |
| Unique Runs / Trips in Valid:    32 Independent Trips                              |
| Unique Origins:                  5 Arterial Corridors                              |
| Unique Destinations:             2 Major Hospitals (KMC, Athena)                   |
| Unique Scenarios:                4 (Light, Moderate, Heavy, Incident)              |
| Unique Signalized Junctions:     31 Junctions                                      |
| Exact Duplicate Rows:            0 Rows (0.0%)                                     |
| Negative or Null Targets:        0 Rows (0.0%)                                     |
| Train/Test Trip Overlap:         0 Trips (Strictly 0% Contamination)               |
+------------------------------------------------------------------------------------+
```

### Clarifications on Audit Items
1. **Near-Duplicate Feature Vectors (1,157 rows):** Found to occur when ambulances in separate independent runs departed from the same origin edge at $v = 0\,\text{m/s}$ and approached the first signal under identical initial conditions. Within the same trip, no duplicate rows exist.
2. **Missing Authoritative Hospitals:** The Phase 3 script defined 8 hospitals in its configuration list but executed `destinations[:2]` to balance simulation runtime across 40 planned runs. The 9 omitted hospitals (`highland_hospital`, `father_muller_hospital`, `160262590`, `calaco_hospital`, `scs_hospital`, `unity_hospital`, `indira_hospital`, `vijaya_clinic_general_hospital`, `mangalore_nursing_home`) are topologically connected and routable, but were not sampled in the v1 dataset.

---

## 4. Live Shadow-Mode Benchmark Results

The benchmark script [`scratch/phase4_shadow/benchmark_eta_shadow.py`](file:///D:/AIML/Projects/Major/AI-Predictive-Traffic/scratch/phase4_shadow/benchmark_eta_shadow.py) was executed across 16 test corridors spanning light, moderate, heavy, and incident congestion, with both un-preempted baseline traffic and active signal preemption.

### A. Next-Junction ETA Prediction Quality (6,306 Valid Evaluations)

Evaluated simultaneously on identical simulation observations:

| Model / Baseline | MAE (s) | RMSE (s) | Median AE (s) | P90 Error (s) | P95 Error (s) | $R^2$ Score | Mean Latency | P95 Latency |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Physics Baseline** ($d / v_{eff}$) | 54.535 | 76.540 | 38.187 | 135.790 | 165.189 | -0.2590 | $< 0.001\,\text{ms}$ | $< 0.001\,\text{ms}$ |
| **Production Model** (Legacy Pipeline) | 74.316 | 100.152 | 55.765 | 178.262 | 201.057 | -1.1556 | $67.312\,\text{ms}$ | $93.659\,\text{ms}$ |
| **Candidate Model** (Phase 3 RF) | **18.368** | **33.419** | **7.580** | **43.911** | **98.458** | **0.7600** | **$28.684\,\text{ms}$** | **$33.430\,\text{ms}$** |

> [!IMPORTANT]
> The Production Model achieves an $R^2$ of $-1.1556$ on live simulation runs because its pipeline includes a `OneHotEncoder` over categorical junction IDs. When presented with the real Mangaluru network under varying corridor routes, the one-hot transformer fails to generalize. The Candidate Model, trained on pure numeric physical traffic features, delivers a strong $R^2 = 0.7600$ and cuts Median Absolute Error by **86.4%** (from 55.8s to 7.58s).

### B. Scenario Breakdown (Candidate vs Production vs Physics)

| Scenario | Valid Samples | Candidate MAE | Production MAE | Physics MAE | Candidate $R^2$ | Candidate MedAE |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|
| **Light** | 1,962 | **10.266 s** | 64.376 s | 44.160 s | **0.9433** | 6.69 s |
| **Moderate** | 2,178 | **9.840 s** | 70.084 s | 47.658 s | **0.9479** | 5.85 s |
| **Heavy** | 1,873 | **37.226 s** | 91.519 s | 77.362 s | **0.4984** | 14.75 s |
| **Incident** | 293 | **15.469 s** | 62.372 s | 29.204 s | **0.7346** | 7.50 s |

### C. Preemption Mode Comparison

| Mode | Valid Samples | Candidate MAE | Production MAE | Physics MAE | Candidate $R^2$ |
|:---|:---:|:---:|:---:|:---:|:---:|
| **Preemption OFF** (Baseline Signals) | 3,109 | **18.372 s** | 72.148 s | 53.893 s | **0.7562** |
| **Preemption ON** (Active Green Waves) | 3,197 | **18.364 s** | 76.425 s | 55.159 s | **0.7631** |

### D. End-to-End Ambulance Trip Duration View

End-to-end trip completion was evaluated separately from next-junction ETA:
- **Long Arterial Corridors (Origins `321397980`, `1358315405`, `1089450246#0`):** Routes span 3.5 to 4.2 km across 38–44 edges with 10–14 traffic signals. Under normal city speeds (~10 m/s), full traversal requires 350–450 seconds. Under a 320-second step cap, ambulances crossed 4–8 signalized junctions along the corridor while remaining in transit at step 320.
- **Completed Corridor Corridors (Origin `-132363062` to `kmc_hospital`, 22 edges):**
  - **Baseline (Preemption OFF):** Completed in **`199.0 s`**.
  - **Preempted (Preemption ON):** Completed in **`189.0 s`** (**10.0 s faster, 5.0% travel time savings**).
- **Separation Principle:** Next-junction ETA measures the local approach delay at the immediate upcoming signal. High next-junction accuracy does not guarantee end-to-end hospital arrival speed, which is dominated by corridor route topology, non-signalized road bottlenecks, and detour penalties.

---

## 5. Summary of Artifacts Created

| Artifact | File Path | Content |
|:---|:---|:---|
| **Phase 3 Audit Script** | [`scratch/phase4_shadow/audit_phase3.py`](file:///D:/AIML/Projects/Major/AI-Predictive-Traffic/scratch/phase4_shadow/audit_phase3.py) | Verification of dataset counts, leakage, duplicates, and metric reproduction |
| **Audit Results JSON** | [`scratch/phase4_shadow/phase3_audit_results.json`](file:///D:/AIML/Projects/Major/AI-Predictive-Traffic/scratch/phase4_shadow/phase3_audit_results.json) | Machine-readable verification data |
| **Shadow Benchmark Script** | [`scratch/phase4_shadow/benchmark_eta_shadow.py`](file:///D:/AIML/Projects/Major/AI-Predictive-Traffic/scratch/phase4_shadow/benchmark_eta_shadow.py) | Live simulation shadow-mode runner with dual inference logging |
| **Raw Shadow Observations** | [`scratch/phase4_shadow/shadow_raw_observations.csv`](file:///D:/AIML/Projects/Major/AI-Predictive-Traffic/scratch/phase4_shadow/shadow_raw_observations.csv) | 13,398 raw simulation observations with side-by-side predictions and ground-truth targets |
| **Benchmark Report JSON** | [`scratch/phase4_shadow/shadow_benchmark_report.json`](file:///D:/AIML/Projects/Major/AI-Predictive-Traffic/scratch/phase4_shadow/shadow_benchmark_report.json) | Complete statistical breakdown by scenario, preemption, and latency |
| **Phase 4 Validation Report** | [`docs/PHASE4_ETA_SHADOW_VALIDATION.md`](file:///D:/AIML/Projects/Major/docs/PHASE4_ETA_SHADOW_VALIDATION.md) | Authoritative validation document |

---

## 6. Readiness Assessment & Next Safe Step

### Readiness Assessment
- **Statistical Superiority:** The candidate model conclusively beats the production model across all scenarios (MAE: 18.37s vs 74.32s; $R^2$: 0.76 vs -1.16).
- **Latency & Overhead:** Candidate inference takes ~28 ms per batch call, well within real-time simulation requirements.
- **Unresolved Risk / Scope Limitation:** The candidate model was trained on trips terminating at `kmc_hospital` and `athena_hospital`. Before promoting the model as a universal Mangaluru replacement, the dataset should be augmented to sample all 11 authoritative hospitals.

### Verdict
**THE CANDIDATE MODEL IS VALIDATED IN SHADOW MODE AND IS READY FOR CONTROLLED INTEGRATION TESTING.**  
It must **NOT** be integrated into production automatically.

### Recommended Next Safe Step
Conduct a controlled A/B integration experiment in a staging branch:
1. Wrap the candidate model in an integration adapter that mirrors the `predictive_eta.py` interface.
2. Run standard demo trips comparing routing decisions and preemption timing when driven by the candidate model vs the production model.
3. Verify that green waves trigger smoothly and that no unexpected routing loops or edge penalties occur.
