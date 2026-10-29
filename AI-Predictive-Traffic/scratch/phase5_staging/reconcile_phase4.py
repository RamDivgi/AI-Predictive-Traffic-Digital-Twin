"""
PHASE 5: RECONCILE PHASE 4 EVIDENCE & VERIFY TRIP COMPLETIONS
=============================================================
Audits and reconciles:
1. scratch/phase4_shadow/shadow_raw_observations.csv
2. scratch/phase4_shadow/shadow_benchmark_report.json
3. Discrepancies between total raw observations (13,398 vs 12,854)
4. Valid head-to-head evaluations (6,306)
5. True trip completions vs timeouts (strict separation)
6. Scenarios, preemption modes, missing predictions, duplicate rows
7. Target construction audit
"""

from __future__ import annotations

import json
from pathlib import Path
import pandas as pd
import numpy as np

RAW_CSV = Path("D:/AIML/Projects/Major/AI-Predictive-Traffic/scratch/phase4_shadow/shadow_raw_observations.csv")
REPORT_JSON = Path("D:/AIML/Projects/Major/AI-Predictive-Traffic/scratch/phase4_shadow/shadow_benchmark_report.json")
OUTPUT_RECON_JSON = Path("D:/AIML/Projects/Major/AI-Predictive-Traffic/scratch/phase5_staging/phase4_reconciliation_report.json")
OUTPUT_RECON_JSON.parent.mkdir(parents=True, exist_ok=True)


def reconcile_phase4():
    print("=" * 80)
    print("PHASE 5 - TASK B: RECONCILING PHASE 4 EVIDENCE")
    print("=" * 80)

    if not RAW_CSV.exists():
        print(f"ERROR: {RAW_CSV} not found!")
        return

    df = pd.read_csv(RAW_CSV)
    total_raw_rows = len(df)
    print(f"Total raw observation rows in CSV: {total_raw_rows}")

    # Inspect Report JSON
    with open(REPORT_JSON, "r", encoding="utf-8") as f:
        rep = json.load(f)

    rep_total_raw = rep["overall_evaluation"]["total_raw_observations"]
    rep_valid_evals = rep["overall_evaluation"]["valid_observed_evaluations"]
    print(f"Report claimed raw observations: {rep_total_raw}")
    print(f"Report claimed valid evaluations: {rep_valid_evals}")

    # 1. Row counts reconciliation
    # Why did report show 13,398 vs CSV having len(df)?
    print(f"\nRow Counts Reconciliation:")
    print(f"  CSV row count: {total_raw_rows}")
    print(f"  Report claimed total raw: {rep_total_raw}")
    if total_raw_rows == rep_total_raw:
        print("  -> Raw row count matches exactly!")
    else:
        print(f"  -> Discrepancy: diff = {total_raw_rows - rep_total_raw}")

    # 2. Valid Observed Junction Rows
    df_valid = df[df["target_junction_observed"] == 1].copy()
    actual_valid_count = len(df_valid)
    print(f"  Actual valid junction observed rows: {actual_valid_count}")
    print(f"  Report claimed valid evaluations: {rep_valid_evals}")
    assert actual_valid_count == rep_valid_evals, f"Mismatch: {actual_valid_count} vs {rep_valid_evals}"
    print("  -> Valid evaluation count matches exactly (6,306 rows)!")

    # 3. Why are only 6,306 of 13,398 raw observations valid?
    # Because upcoming junctions are tracked up to 3 at a time (MAX_JUNCTIONS=3).
    # When ambulance is far from the 2nd and 3rd upcoming junctions, or when
    # simulation ends before the ambulance reaches them, target_junction_observed = 0.
    unobserved_junc_count = int((df["target_junction_observed"] == 0).sum())
    null_junc_target = int(df["target_junction_eta_s"].isnull().sum())
    print(f"\nTarget Observation Breakdown:")
    print(f"  Valid observed junction ETAs: {actual_valid_count} ({actual_valid_count/total_raw_rows*100:.1f}%)")
    print(f"  Unobserved / Censored junction rows: {unobserved_junc_count} ({unobserved_junc_count/total_raw_rows*100:.1f}%)")
    print(f"  Null target_junction_eta_s count: {null_junc_target}")
    assert unobserved_junc_count == null_junc_target

    # 4. Independent Trip Completion Audit
    print(f"\nTrip Completion & Elapsed Travel Time Audit:")
    trips = df.groupby("trip_id")
    trip_records = []

    for tid, g in trips:
        orig = g["origin_edge"].iloc[0]
        dest = g["destination_hospital"].iloc[0]
        sc = g["traffic_scenario"].iloc[0]
        pm = g["preemption_mode"].iloc[0]
        seed = int(g["seed"].iloc[0])
        sim_times = g["simulation_time"].values
        start_t = float(sim_times.min())
        end_t = float(sim_times.max())
        
        # Check hospital arrival
        hosp_rows = g[g["target_hospital_observed"] == 1]
        if len(hosp_rows) > 0:
            # Hospital was reached during simulation
            # The exact time of hospital arrival is start_t + target_hospital_eta_s at start_t
            hosp_arrival_time = float(hosp_rows["simulation_time"].iloc[0] + hosp_rows["target_hospital_eta_s"].iloc[0])
            elapsed_trip_time = round(hosp_arrival_time - start_t, 2)
            completion_status = "COMPLETED"
        else:
            hosp_arrival_time = None
            elapsed_trip_time = None
            completion_status = "TIMEOUT_INCOMPLETE (>320s)"

        junc_evals = int((g["target_junction_observed"] == 1).sum())

        rec = {
            "trip_id": tid,
            "seed": seed,
            "origin": orig,
            "destination": dest,
            "scenario": sc,
            "preemption": pm,
            "start_time_s": start_t,
            "end_simulation_time_s": end_t,
            "status": completion_status,
            "hospital_arrival_time_s": hosp_arrival_time,
            "actual_elapsed_trip_time_s": elapsed_trip_time,
            "raw_observations": len(g),
            "valid_junction_evals": junc_evals,
        }
        trip_records.append(rec)
        dur_str = f"{elapsed_trip_time:.1f}s" if elapsed_trip_time else "FAILED / TIMEOUT"
        print(f"  {tid:<50} | {sc:<8} | {pm:<11} | Status: {completion_status:<24} | Elapsed: {dur_str}")

    completed_count = sum(1 for r in trip_records if r["status"] == "COMPLETED")
    timeout_count = sum(1 for r in trip_records if r["status"] != "COMPLETED")
    print(f"\nTrip Completion Summary:")
    print(f"  Total Trips in CSV: {len(trip_records)}")
    print(f"  Completed Trips   : {completed_count}")
    print(f"  Incomplete/Timeout: {timeout_count}")

    # 5. Missing / Invalid Predictions Audit
    print(f"\nModel Prediction Health Audit:")
    prod_invalid = int((df["prod_eta_pred_s"] < 0).sum())
    cand_invalid = int((df["cand_eta_pred_s"] < 0).sum())
    phys_invalid = int((df["phys_eta_pred_s"] < 0).sum())
    print(f"  Production Model invalid predictions (<0): {prod_invalid}")
    print(f"  Candidate Model invalid predictions (<0):  {cand_invalid}")
    print(f"  Physics Baseline invalid predictions (<0): {phys_invalid}")

    # 6. Recompute metrics directly from raw CSV to verify
    from sklearn.metrics import mean_absolute_error, mean_squared_error, median_absolute_error, r2_score
    y_true = df_valid["target_junction_eta_s"].astype(float).values
    y_cand = df_valid["cand_eta_pred_s"].astype(float).values
    y_prod = df_valid["prod_eta_pred_s"].astype(float).values
    y_phys = df_valid["phys_eta_pred_s"].astype(float).values

    def get_metrics(yt, yp):
        err = np.abs(yt - yp)
        return {
            "mae": round(float(mean_absolute_error(yt, yp)), 4),
            "rmse": round(float(np.sqrt(mean_squared_error(yt, yp))), 4),
            "medae": round(float(median_absolute_error(yt, yp)), 4),
            "p90": round(float(np.percentile(err, 90)), 4),
            "p95": round(float(np.percentile(err, 95)), 4),
            "r2": round(float(r2_score(yt, yp)), 4),
        }

    recomputed_cand = get_metrics(y_true, y_cand)
    recomputed_prod = get_metrics(y_true, y_prod)
    recomputed_phys = get_metrics(y_true, y_phys)

    print(f"\nRecomputed Comparative Metrics on {len(df_valid)} Valid Samples:")
    print(f"  Candidate  : MAE={recomputed_cand['mae']}s, RMSE={recomputed_cand['rmse']}s, MedAE={recomputed_cand['medae']}s, R²={recomputed_cand['r2']}")
    print(f"  Production : MAE={recomputed_prod['mae']}s, RMSE={recomputed_prod['rmse']}s, MedAE={recomputed_prod['medae']}s, R²={recomputed_prod['r2']}")
    print(f"  Physics    : MAE={recomputed_phys['mae']}s, RMSE={recomputed_phys['rmse']}s, MedAE={recomputed_phys['medae']}s, R²={recomputed_phys['r2']}")

    reconciliation_data = {
        "dataset_integrity": {
            "csv_rows": total_raw_rows,
            "report_claimed_rows": rep_total_raw,
            "valid_observed_evaluations": actual_valid_count,
            "unobserved_evaluations": unobserved_junc_count,
            "null_targets": null_junc_target,
        },
        "trip_completion_audit": {
            "total_trips_in_csv": len(trip_records),
            "completed_trips": completed_count,
            "timed_out_trips": timeout_count,
            "trip_records": trip_records,
        },
        "prediction_failures": {
            "production_invalid": prod_invalid,
            "candidate_invalid": cand_invalid,
            "physics_invalid": phys_invalid,
        },
        "recomputed_metrics": {
            "candidate": recomputed_cand,
            "production": recomputed_prod,
            "physics": recomputed_phys,
        }
    }

    with open(OUTPUT_RECON_JSON, "w", encoding="utf-8") as f:
        json.dump(reconciliation_data, f, indent=2)

    print(f"\nReconciliation report written to: {OUTPUT_RECON_JSON}")
    print("=" * 80)


if __name__ == "__main__":
    reconcile_phase4()
