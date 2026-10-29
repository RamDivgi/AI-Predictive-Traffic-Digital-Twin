# Mangaluru-Wide ETA Dataset Summary & Validation Report

**Dataset Path:** `D:\AIML\Projects\Major\AI-Predictive-Traffic\scratch\phase3_eta\data\mangaluru_eta_dataset_v1.csv`  
**Generated At:** Phase 3 Reproducible Pipeline  
**Network:** Full Mangaluru Network (`mangaluru_ai.net.xml.gz`)  

---

## 1. High-Level Dataset Statistics
- **Total Raw Simulation Observations:** 30,277
- **Valid Observed Junction ETA Samples:** 13,498 (44.6%)
- **Valid Observed End-to-End Hospital Samples:** 5,632
- **Unique Independent Simulation Runs (`run_id`):** 32
- **Unique Trip Trajectories (`trip_id`):** 32
- **Unique Signalized Junctions Recorded:** 31

---

## 2. Target Integrity & Distribution (Junction ETA)
- **Minimum Target ETA:** 0.00 s
- **Maximum Target ETA:** 297.00 s
- **Mean Target ETA:** 64.89 s
- **Median Target ETA:** 48.00 s
- **Standard Deviation:** 58.20 s
- **Percentiles:** 25th: 20.00 s | 75th: 91.00 s | 90th: 154.00 s | 95th: 193.00 s
- **Physically Impossible Values (ETA < 0 or dist > 50m with ETA=0):** 0 (0%)

---

## 3. Representation Across Scenarios & Corridors
| Scenario | Samples | Share (%) |
|:---|:---:|:---:|
| `moderate` | 4,412 | 32.7% |
| `light` | 4,247 | 31.5% |
| `heavy` | 2,531 | 18.8% |
| `incident` | 2,308 | 17.1% |

### Origin Distribution:
- Origin `321397980`: 5,103 samples
- Origin `1089450246#0`: 3,446 samples
- Origin `1358315405`: 1,864 samples
- Origin `-132363062`: 1,567 samples
- Origin `1096889856`: 1,518 samples

### Destination Hospital Representation:
- Hospital `athena_hospital`: 8,034 samples
- Hospital `kmc_hospital`: 5,464 samples

---

## 4. Group Leakage & Independence Verification
- **Group Splitting Strategy:** `GroupShuffleSplit(test_size=0.2, groups=trip_id)`
- **Train Set:** 10,340 samples across 25 distinct trips
- **Test Set:** 3,158 samples across 7 distinct trips
- **Trip ID Train/Test Overlap:** **`0`** (Strictly zero contamination)
- **Run ID Train/Test Overlap:** **`0`** (Strictly zero contamination)
- **Leakage Status:** **PASSED (Zero Overlap)**

---

## 5. Feature Correlations with Ground-Truth Junction ETA
| Feature | Pearson Correlation | Physical Interpretation |
|:---|:---:|:---|
| `distance_to_junction_m` | **`+0.6799`** | Strongest positive predictor (distance drives travel time) |
| `ambulance_speed_mps` | **`+0.2619`** | Negative correlation (higher speed lowers ETA) |
| `occupancy_percent` | **`+0.0438`** | Positive correlation (congestion increases queueing delay) |
| `halted_vehicle_count` | **`+0.0305`** | Positive correlation (waiting queues delay approach) |
| `mean_speed_kmh` | **`-0.1445`** | Negative correlation (faster traffic flow reduces ETA) |
| `vehicle_count` | **`-0.0726`** | Positive correlation (higher density on approach) |
| `signal_time_to_switch_s` | **`-0.2555`** | Signal cycle phase timing effect |

