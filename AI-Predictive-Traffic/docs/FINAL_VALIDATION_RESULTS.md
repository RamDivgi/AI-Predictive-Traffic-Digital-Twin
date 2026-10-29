# Final Validation Results: Empirical Evaluation & Benchmarks
**Project:** AI-Powered Predictive Routing and Signal Preemption in a Digital Twin Environment  
**Workspace:** `D:\AIML\Projects\Major\AI-Predictive-Traffic`  
**Date:** October 2026  

---

## 1. Overview of Experimental Verification

To evaluate the predictive routing and signal preemption framework, two rigorous stages of empirical validation were conducted:
1. **Phase 4 Shadow Benchmark (Offline ETA Evaluation):** Head-to-head comparison between Production Model, Candidate Model, and Physics Baseline across 6,306 ground-truth observed junction arrivals.
2. **Phase 5 Controlled A/B Experiment (Closed-Loop Preemption Simulation):** 16 matched pairs (32 simulation runs) in SUMO micro-simulation comparing ambulance travel times, signal lead times, and civilian traffic impacts between Production Model Preemption (Control) and Candidate Model Preemption (Treatment).

All metrics in this report are computed directly from raw logged data in `scratch/phase4_shadow/shadow_raw_observations.csv` and `scratch/phase5_staging/ab_raw_experiment_results.csv`. **No data has been fabricated or inferred.**

---

## 2. Phase 4: Shadow ETA Prediction Benchmark

### A. Data Integrity & Sampling Audit
- **Total Raw Observation Rows Logged:** 13,398 rows.
- **Valid Ground-Truth Observed Junction Arrivals:** 6,306 observations (47.1%).
- **Censored / Unobserved Junction Rows:** 7,092 rows (52.9%).
  - *Audit Rationale:* The simulation tracks the next 3 upcoming junctions simultaneously. For junctions where the ambulance was diverted or where simulation steps ended before arrival, `target_junction_observed = 0` and `target_junction_eta_s = null`. Censored entries were strictly excluded from ground-truth metric calculation.

### B. Head-to-Head Error Metrics (6,306 Valid Observations)

$$\text{Error} = |y_{\text{true}} - y_{\text{pred}}|$$

| Metric | Production Model (`models/`) | Physics Baseline ($\text{Dist}/\text{Speed}$) | Candidate Model (`scratch/phase3_eta/`) | Candidate Improvement vs Production |
| :--- | :---: | :---: | :---: | :---: |
| **MAE (Mean Absolute Error)** | **74.32 s** | **54.54 s** | **18.37 s** | **-75.28% (-55.95s)** |
| **RMSE (Root Mean Squared Error)** | **100.15 s** | **76.54 s** | **33.42 s** | **-66.63% (-66.73s)** |
| **MedAE (Median Absolute Error)** | **55.77 s** | **38.19 s** | **7.58 s** | **-86.41% (-48.19s)** |
| **P90 Error (90th Percentile)** | **178.26 s** | **135.79 s** | **43.91 s** | **-75.37% (-134.35s)** |
| **P95 Error (95th Percentile)** | **201.06 s** | **165.19 s** | **98.46 s** | **-51.03% (-102.60s)** |
| **$R^2$ Score (Coefficient of Determination)** | **-1.156** | **-0.259** | **+0.760** | **+1.916 ($R^2$ shifted positive)** |

### C. Analysis of Offline ETA Performance
- The Candidate Model demonstrated substantial improvements across all error percentiles, reducing 90th percentile errors from 178.3s down to 43.9s.
- The Production Model exhibited substantial negative $R^2$ due to out-of-distribution drift on long-range junction queries where queuing delays were unrepresented in its original training distribution.

---

## 3. Phase 5: Controlled A/B Preemption Experiment

### A. Experimental Protocol
- **Control Condition:** Production Model Preemption Controller (`models/eta_prediction_model.joblib`).
- **Treatment Condition:** Candidate Model Preemption Controller loaded via isolated Staging Adapter (`scratch/phase5_staging/staging_adapter.py`).
- **Controlled Variables:** Identical road networks, origin edges, hospital destinations, background traffic schedules, vehicle seeds (5001, 5002), and simulation step limits (450s).
- **Predeclared Primary Metric:** Paired Completed Ambulance Trip Travel Time (s).
- **Secondary Metrics:** Preemption activation count, premature preemption count, mean lead time (s), signal restoration success rate, civilian average halted queue, and civilian network mean speed (km/h).

### B. Summary of Simulation Execution

| Execution Parameter | Planned | Executed / Verified | Status |
| :--- | :---: | :---: | :--- |
| **Total Matched Pairs** | 16 | 16 | 100% Terminal |
| **Total Simulation Runs** | 32 | 32 | 100% Terminal |
| **Completed Matched Pairs** | 16 | 16 (100.0%) | 8 Pairs Corridor Kankanady; 8 Pairs Corridor Kodialbail |
| **Incomplete / Timed-Out Pairs** | 0 | 0 (0.0%) | Zero timeouts; 100% genuine hospital arrival |

### C. Primary Metric: Paired Travel Time on All 16 Completed Trips

$$\Delta_{\text{duration}} = t_{\text{Treatment}} - t_{\text{Control}}$$

| Pair ID | Corridor | Scenario | Seed | Control Duration ($t_{\text{Ctrl}}$) | Treatment Duration ($t_{\text{Treat}}$) | Paired $\Delta$ | % Change | Faster Condition |
| :---: | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **01** | Corridor_Kankanady | light | 5001 | 137.0 s | 154.0 s | +17.0 s | +12.41% | Control |
| **02** | Corridor_Kankanady | light | 5002 | 137.0 s | 152.0 s | +15.0 s | +10.95% | Control |
| **03** | Corridor_Kankanady | moderate | 5001 | 137.0 s | 134.0 s | **-3.0 s** | -2.19% | **Treatment** |
| **04** | Corridor_Kankanady | moderate | 5002 | 136.0 s | 152.0 s | +16.0 s | +11.76% | Control |
| **05** | Corridor_Kankanady | heavy | 5001 | 413.0 s | 423.0 s | +10.0 s | +2.42% | Control |
| **06** | Corridor_Kankanady | heavy | 5002 | 403.0 s | 419.0 s | +16.0 s | +3.97% | Control |
| **07** | Corridor_Kankanady | incident | 5001 | 234.0 s | 231.0 s | **-3.0 s** | -1.28% | **Treatment** |
| **08** | Corridor_Kankanady | incident | 5002 | 197.0 s | 213.0 s | +16.0 s | +8.12% | Control |
| **09** | Corridor_Kodialbail | light | 5001 | 212.0 s | 226.0 s | +14.0 s | +6.60% | Control |
| **10** | Corridor_Kodialbail | light | 5002 | 211.0 s | 225.0 s | +14.0 s | +6.64% | Control |
| **11** | Corridor_Kodialbail | moderate | 5001 | 218.0 s | 220.0 s | +2.0 s | +0.92% | Control |
| **12** | Corridor_Kodialbail | moderate | 5002 | 215.0 s | 245.0 s | +30.0 s | +13.95% | Control |
| **13** | Corridor_Kodialbail | heavy | 5001 | 277.0 s | 251.0 s | **-26.0 s** | -9.39% | **Treatment** |
| **14** | Corridor_Kodialbail | heavy | 5002 | 225.0 s | 230.0 s | +5.0 s | +2.22% | Control |
| **15** | Corridor_Kodialbail | incident | 5001 | 323.0 s | 325.0 s | +2.0 s | +0.62% | Control |
| **16** | Corridor_Kodialbail | incident | 5002 | 322.0 s | 322.0 s | **0.0 s** | 0.00% | Tied |
| **Aggregate** | **All 16 Matched Pairs** | — | — | **$\mu = 237.31\text{s}$** | **$\mu = 245.12\text{s}$** | **$\mu = +7.81\text{s}$** | **$+4.23\%$** | **Control (12/16)** |

- **Statistical Significance:**
  - Paired two-tailed $t$-test: $t = 2.472$, **$p = 0.0266$** (statistically significant at $\alpha = 0.05$).
  - Wilcoxon signed-rank test: $W = 16.0$, **$p = 0.0265$** (statistically significant at $\alpha = 0.05$).
  - Mean travel time difference is $+7.81\text{s}$ ($95\%\text{ CI}: [1.25\text{s}, 14.37\text{s}]$).

---

## 4. Operational Trade-Offs & Root-Cause Analysis

Why did the candidate model—despite a 75% reduction in offline ETA error—produce slightly slower ambulance trips in closed-loop simulation? Inspection of the operational telemetry reveals the mechanism:

| Operational Metric | Control (Production) | Treatment (Candidate) | Difference / Interpretation |
| :--- | :---: | :---: | :--- |
| **Preemptions Activated / Run** | **30.56** | **17.12** | Candidate fired **44.0% fewer** preemption requests, drastically reducing signal disruption. |
| **Mean Preemption Lead Time** | **27.59 s** | **9.70 s** | Control preempted signals ~28s in advance; Candidate waited until ~10s (64.8% reduction in hold time). |
| **Signal Restoration Rate** | **100.0%** | **100.0%** | Perfect signal restoration across all 32 runs. |
| **Civilian Average Halted Queue** | **56.35 veh** | **56.79 veh** | Civilian traffic queues were virtually identical (+0.78%). |
| **Civilian Network Mean Speed** | **27.32 km/h** | **27.20 km/h** | Civilian traffic network speed was preserved in both conditions. |
| **Candidate Inference Latency** | — | **Mean: 4.98 ms, P95: 6.42 ms** | Real-time single-sample inference easily met sub-10ms requirements. |
| **Clamped Predictions / Exceptions** | — | **0 / 0** | Zero runtime crashes, NaN values, or unhandled exceptions across 9,667 inferences. |

### Engineering Insight & Conclusion:
- **The Queue Dissipation Latency Problem:**  
  When preemption is triggered with a tight 9.7s lead time based on accurate ETA, the signal turns green, but **the vehicles queued at the red light require 2.5s per vehicle to accelerate and clear the intersection**. Consequently, when the ambulance arrives at the intersection 10 seconds later, it encounters dissipating queue vehicles that obstruct its path.
- In contrast, the Production Model's over-estimated ETA triggered early preemption (~28s in advance). Although this held signals red for cross-traffic longer, it cleared the approach completely before the ambulance arrived, allowing high-speed traversal.
- **Production Integration Decision:**  
  **The Candidate Model is NOT promoted to production.**  
  Offline ETA MAE is an insufficient metric for closed-loop signal control. Preemption algorithms require a calibrated safety buffer proportional to standing queue length rather than purely minimum-error arrival prediction.

---

## 5. Verification of Safety & Regression Guards

The staging adapter safety guards were verified with 100% pass rates:
1. **Dry-Run Isolation:** When `dry_run=True`, the adapter returned `False` on all preemption requests, verifying that SUMO signal states remain completely unaffected during testing.
2. **Feature Schema Adherence:** All 8 numeric features (`ambulance_speed_mps`, `distance_to_junction_m`, `vehicle_count`, `halted_vehicle_count`, `mean_speed_kmh`, `occupancy_percent`, `signal_phase`, `signal_time_to_switch_s`) were validated against `candidate_schema.json`.
3. **Corrupt / Missing Input Fallbacks:** Null inputs, empty dictionaries, NaN speeds, and infinite values were caught without crashing and defaulted to physically bounded estimates.
4. **Clamping Bounds:** Output ETAs were strictly clamped to $[0.0\text{s}, 300.0\text{s}]$.
5. **Conflicting-Approach Protection:** Preemption requests were automatically suppressed when queues exceeded 5 halted vehicles or when distance exceeded 500m.
