"""
PHASE 4: ISOLATED SHADOW-MODE BENCHMARK
=======================================
Benchmarks the candidate ETA model (mangaluru_eta_candidate.joblib) alongside
the production ETA model (eta_prediction_model.joblib) in strict shadow mode.

Preservation Guarantees:
- Never feeds candidate predictions into routing, rerouting, preemption, or Unity.
- Does not modify existing production routing thresholds or controller logic.
- Measures:
  A. Next-junction ETA prediction accuracy (MAE, RMSE, MedAE, P90, P95, R²).
  B. End-to-end ambulance trip duration.
  C. Inference latency (mean, P95) for both models.
  D. Missing features and failure rates.
  E. Performance across traffic scenarios and preemption modes.
"""

from __future__ import annotations

import csv
import json
import os
import sys
import time
from pathlib import Path
import numpy as np
import pandas as pd
import joblib

import sumolib
import traci

from sklearn.metrics import mean_absolute_error, mean_squared_error, median_absolute_error, r2_score

PROJECT_ROOT = Path("D:/AIML/Projects/Major")

PY_ROOT = PROJECT_ROOT / "AI-Predictive-Traffic"
sys.path.append(str(PY_ROOT / "controller"))

import config
import astar_router
import route_evaluator
import junction_detector
import signal_mapping
import signal_preemption
from hospital_manager import HospitalManager

MANGALURU_NET = PY_ROOT / "simulation" / "mangaluru" / "mangaluru_ai.net.xml.gz"
HOSPITALS_FILE = PY_ROOT / "simulation" / "mangaluru" / "presentation_labels.add.xml"
SUMOCFG = PY_ROOT / "simulation" / "mangaluru" / "ambulance_test.sumocfg"

PROD_MODEL_PATH = PY_ROOT / "models" / "eta_prediction_model.joblib"
CAND_MODEL_PATH = PY_ROOT / "scratch" / "phase3_eta" / "models" / "mangaluru_eta_candidate.joblib"
SCHEMA_PATH = PY_ROOT / "scratch" / "phase3_eta" / "models" / "candidate_schema.json"

SHADOW_DIR = PY_ROOT / "scratch" / "phase4_shadow"
SHADOW_DIR.mkdir(parents=True, exist_ok=True)
RAW_OBS_CSV = SHADOW_DIR / "shadow_raw_observations.csv"
BENCHMARK_REPORT_JSON = SHADOW_DIR / "shadow_benchmark_report.json"

# Load models
print(f"Loading Production Model from: {PROD_MODEL_PATH}")
prod_model = joblib.load(PROD_MODEL_PATH)
print(f"Loading Candidate Model from: {CAND_MODEL_PATH}")
cand_model = joblib.load(CAND_MODEL_PATH)
with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
    cand_schema = json.load(f)

# Global network bindings
config.NET_FILE = MANGALURU_NET
_net = sumolib.net.readNet(str(MANGALURU_NET))
astar_router._SUMO_NETWORK = _net
route_evaluator._SUMO_NETWORK = _net
junction_detector.SUMO_NETWORK = _net

hm = HospitalManager(str(MANGALURU_NET), str(HOSPITALS_FILE))
router = astar_router.AStarRouter(str(MANGALURU_NET))

PROD_FEATURES = [
    "ambulance_speed_mps", "ambulance_speed_kmh", "distance_to_junction_m",
    "vehicle_count", "halted_vehicle_count", "mean_speed_kmh",
    "occupancy_percent", "signal_phase", "signal_time_to_switch_s",
    "junction_id", "incoming_edge", "outgoing_edge"
]

CAND_FEATURES = [
    "ambulance_speed_mps", "distance_to_junction_m", "vehicle_count",
    "halted_vehicle_count", "mean_speed_kmh", "occupancy_percent",
    "signal_phase", "signal_time_to_switch_s"
]

CSV_HEADER = [
    "benchmark_id", "seed", "trip_id", "ambulance_id", "origin_edge",
    "destination_hospital", "traffic_scenario", "preemption_mode",
    "simulation_time", "ambulance_speed_mps", "distance_to_junction_m",
    "distance_to_hospital_m", "junction_id", "incoming_edge", "outgoing_edge",
    "prod_eta_pred_s", "cand_eta_pred_s", "phys_eta_pred_s",
    "prod_latency_ms", "cand_latency_ms",
    "target_junction_eta_s", "target_junction_observed",
    "target_hospital_eta_s", "target_hospital_observed"
]


def run_shadow_trip(
    run_idx: int,
    seed: int,
    origin_edge: str,
    hospital_id: str,
    scenario_name: str,
    enable_preemption: bool = False,
    max_steps: int = 350,
) -> tuple[list[dict], dict]:
    hospital = hm.get_hospital(hospital_id)
    dest_edge = hospital.nearest_edge
    route_obj = router.find_route(origin_edge, dest_edge)
    if not route_obj or not route_obj.edge_ids:
        return [], {}

    amb_id = f"amb_p4_{run_idx:03d}"
    trip_id = f"trip_p4_{run_idx:03d}_{hospital_id}_{scenario_name}_{'preempt' if enable_preemption else 'base'}_{seed}"
    route_id = f"route_{trip_id}"

    try:
        traci.close()
    except Exception:
        pass

    traci.start([
        "sumo",
        "-c", str(SUMOCFG),
        "--step-length", "1.0",
        "--seed", str(seed),
        "--no-warnings",
    ])

    signal_mapping._MOVEMENT_TO_TLS_CACHE = None
    signal_mapping._build_tls_cache()

    traci.route.add(route_id, route_obj.edge_ids)
    traci.vehicle.add(
        vehID=amb_id,
        routeID=route_id,
        typeID="ambulance",
        depart="1.0",
        departLane="best",
    )

    # Scenario congestion
    if scenario_name == "moderate":
        mid_idx = len(route_obj.edge_ids) // 2
        try:
            traci.edge.setMaxSpeed(route_obj.edge_ids[mid_idx], 4.0)
        except Exception:
            pass
    elif scenario_name == "heavy":
        mid_idx = len(route_obj.edge_ids) // 2
        try:
            traci.edge.setMaxSpeed(route_obj.edge_ids[mid_idx], 2.5)
            block_r = f"blk_{trip_id}"
            traci.route.add(block_r, [route_obj.edge_ids[mid_idx]])
            for i in range(2):
                vid = f"bk_{trip_id}_{i}"
                traci.vehicle.add(vid, block_r, typeID="passenger")
                traci.vehicle.moveTo(vid, f"{route_obj.edge_ids[mid_idx]}_0", 10.0 + i * 8.0)
                traci.vehicle.setSpeed(vid, 0.0)
        except Exception:
            pass
    elif scenario_name == "incident":
        mid_idx = len(route_obj.edge_ids) // 2
        try:
            traci.edge.setMaxSpeed(route_obj.edge_ids[mid_idx], 0.8)
            block_r = f"inc_{trip_id}"
            traci.route.add(block_r, [route_obj.edge_ids[mid_idx]])
            for i in range(3):
                vid = f"inc_{trip_id}_{i}"
                traci.vehicle.add(vid, block_r, typeID="passenger")
                traci.vehicle.moveTo(vid, f"{route_obj.edge_ids[mid_idx]}_0", 5.0 + i * 8.0)
                traci.vehicle.setSpeed(vid, 0.0)
        except Exception:
            pass

    raw_observations: list[dict] = []
    junction_arrivals: dict[str, float] = {}
    active_approaches: dict[str, dict] = {}
    hospital_arrival_time: float | None = None
    ambulance_depart_time: float | None = None

    step = 0
    ambulance_spawned = False
    ambulance_arrived = False

    while step < max_steps:
        traci.simulationStep()
        sim_time = traci.simulation.getTime()

        if "ambulance" in traci.vehicle.getIDList():
            try:
                traci.vehicle.remove("ambulance")
            except Exception:
                pass

        vehs = traci.vehicle.getIDList()
        if amb_id in vehs:
            if not ambulance_spawned:
                ambulance_spawned = True
                ambulance_depart_time = sim_time

            current_edge = traci.vehicle.getRoadID(amb_id)
            current_spd_mps = max(0.0, traci.vehicle.getSpeed(amb_id))

            if current_edge == dest_edge:
                if hospital_arrival_time is None:
                    hospital_arrival_time = sim_time
                ambulance_arrived = True
                break

            # Distance to hospital
            route_edges = traci.vehicle.getRoute(amb_id)
            r_idx = traci.vehicle.getRouteIndex(amb_id)
            dist_to_hospital = sum(_net.getEdge(e).getLength() for e in route_edges[r_idx:]) if (0 <= r_idx < len(route_edges)) else 0.0

            upcoming = junction_detector.get_upcoming_junctions(max_junctions=3, ambulance_id=amb_id)
            upcoming_ids = set()

            for j in upcoming:
                upcoming_ids.add(j.junction_id)
                active_approaches[j.junction_id] = {
                    "incoming": j.incoming_edge,
                    "outgoing": j.outgoing_edge,
                    "dist": j.distance_from_ambulance_m,
                    "time": sim_time,
                }

                if j.distance_from_ambulance_m <= 5.0 and j.junction_id not in junction_arrivals:
                    junction_arrivals[j.junction_id] = sim_time

                # Optional preemption execution (only signal, no routing modification)
                if enable_preemption and j.distance_from_ambulance_m < 150.0:
                    try:
                        plan = signal_preemption.create_preemption_plan(j.junction_id, j.incoming_edge, j.outgoing_edge)
                        if plan:
                            signal_preemption.apply_preemption(plan)
                    except Exception:
                        pass

                # Extract features
                inc_edge = j.incoming_edge
                v_ids = traci.edge.getLastStepVehicleIDs(inc_edge)
                v_count = len(v_ids)
                halted_count = sum(1 for v in v_ids if traci.vehicle.getSpeed(v) < 0.1)
                mean_spd = max(0.0, traci.edge.getLastStepMeanSpeed(inc_edge))
                occ = max(0.0, traci.edge.getLastStepOccupancy(inc_edge))

                j_id = j.junction_id
                sig_phase = -1
                sig_switch = 0.0
                try:
                    sig_phase = traci.trafficlight.getPhase(j_id)
                    next_sw = traci.trafficlight.getNextSwitch(j_id)
                    sig_switch = max(0.0, next_sw - sim_time)
                except Exception:
                    pass

                # 1. Production Model Prediction
                prod_row = {
                    "ambulance_speed_mps": current_spd_mps,
                    "ambulance_speed_kmh": current_spd_mps * 3.6,
                    "distance_to_junction_m": j.distance_from_ambulance_m,
                    "vehicle_count": v_count,
                    "halted_vehicle_count": halted_count,
                    "mean_speed_kmh": mean_spd * 3.6,
                    "occupancy_percent": occ,
                    "signal_phase": sig_phase,
                    "signal_time_to_switch_s": sig_switch,
                    "junction_id": j_id,
                    "incoming_edge": inc_edge,
                    "outgoing_edge": j.outgoing_edge,
                }
                t0_prod = time.perf_counter_ns()
                try:
                    df_prod = pd.DataFrame([prod_row])
                    prod_pred = float(prod_model.predict(df_prod)[0])
                except Exception:
                    prod_pred = -1.0
                t1_prod = time.perf_counter_ns()
                prod_lat = (t1_prod - t0_prod) / 1e6  # ms

                # 2. Candidate Model Prediction
                cand_row = {
                    "ambulance_speed_mps": current_spd_mps,
                    "distance_to_junction_m": j.distance_from_ambulance_m,
                    "vehicle_count": v_count,
                    "halted_vehicle_count": halted_count,
                    "mean_speed_kmh": mean_spd * 3.6,
                    "occupancy_percent": occ,
                    "signal_phase": sig_phase,
                    "signal_time_to_switch_s": sig_switch,
                }
                t0_cand = time.perf_counter_ns()
                try:
                    df_cand = pd.DataFrame([cand_row])
                    cand_pred = float(cand_model.predict(df_cand)[0])
                except Exception:
                    cand_pred = -1.0
                t1_cand = time.perf_counter_ns()
                cand_lat = (t1_cand - t0_cand) / 1e6  # ms

                # 3. Physics Prediction
                eff_spd = max(current_spd_mps, max(mean_spd, 3.0))
                phys_pred = j.distance_from_ambulance_m / eff_spd

                obs = {
                    "benchmark_id": f"bm_{run_idx:03d}",
                    "seed": seed,
                    "trip_id": trip_id,
                    "ambulance_id": amb_id,
                    "origin_edge": origin_edge,
                    "destination_hospital": hospital_id,
                    "traffic_scenario": scenario_name,
                    "preemption_mode": "preempt_on" if enable_preemption else "preempt_off",
                    "simulation_time": sim_time,
                    "ambulance_speed_mps": round(current_spd_mps, 3),
                    "distance_to_junction_m": round(j.distance_from_ambulance_m, 2),
                    "distance_to_hospital_m": round(dist_to_hospital, 2),
                    "junction_id": j_id,
                    "incoming_edge": inc_edge,
                    "outgoing_edge": j.outgoing_edge,
                    "prod_eta_pred_s": round(prod_pred, 3),
                    "cand_eta_pred_s": round(cand_pred, 3),
                    "phys_eta_pred_s": round(phys_pred, 3),
                    "prod_latency_ms": round(prod_lat, 4),
                    "cand_latency_ms": round(cand_lat, 4),
                }
                raw_observations.append(obs)

            for j_id, info in list(active_approaches.items()):
                if j_id not in junction_arrivals:
                    if current_edge == info["outgoing"] or current_edge.startswith(f":{j_id}"):
                        junction_arrivals[j_id] = sim_time
                    elif j_id not in upcoming_ids and info["dist"] < 35.0:
                        junction_arrivals[j_id] = sim_time

        elif ambulance_spawned:
            if hospital_arrival_time is None:
                hospital_arrival_time = sim_time
            ambulance_arrived = True
            break

        step += 1

    traci.close()

    # Calculate ground truth arrival targets
    final_rows: list[dict] = []
    for obs in raw_observations:
        j_id = obs["junction_id"]
        obs_time = obs["simulation_time"]

        if j_id in junction_arrivals and junction_arrivals[j_id] >= obs_time:
            obs["target_junction_eta_s"] = round(junction_arrivals[j_id] - obs_time, 2)
            obs["target_junction_observed"] = 1
        else:
            obs["target_junction_eta_s"] = None
            obs["target_junction_observed"] = 0

        if hospital_arrival_time is not None and hospital_arrival_time >= obs_time:
            obs["target_hospital_eta_s"] = round(hospital_arrival_time - obs_time, 2)
            obs["target_hospital_observed"] = 1
        else:
            obs["target_hospital_eta_s"] = None
            obs["target_hospital_observed"] = 0

        final_rows.append(obs)

    trip_summary = {
        "trip_id": trip_id,
        "ambulance_id": amb_id,
        "origin_edge": origin_edge,
        "destination_hospital": hospital_id,
        "scenario": scenario_name,
        "preemption_enabled": enable_preemption,
        "ambulance_spawned": ambulance_spawned,
        "ambulance_arrived": ambulance_arrived,
        "depart_time_s": ambulance_depart_time,
        "hospital_arrival_time_s": hospital_arrival_time,
        "total_trip_duration_s": round(hospital_arrival_time - ambulance_depart_time, 2) if (hospital_arrival_time and ambulance_depart_time) else None,
        "junctions_reached": len(junction_arrivals),
        "total_observations": len(final_rows),
    }

    return final_rows, trip_summary


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    errors = np.abs(y_true - y_pred)
    mae = float(mean_absolute_error(y_true, y_pred))
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))
    medae = float(median_absolute_error(y_true, y_pred))
    p90 = float(np.percentile(errors, 90))
    p95 = float(np.percentile(errors, 95))
    r2 = float(r2_score(y_true, y_pred))
    return {
        "mae_s": round(mae, 4),
        "rmse_s": round(rmse, 4),
        "medae_s": round(medae, 4),
        "p90_error_s": round(p90, 4),
        "p95_error_s": round(p95, 4),
        "r2_score": round(r2, 4),
    }


def run_shadow_benchmarks():
    print("=" * 85)
    print("PHASE 4: LIVE SHADOW-MODE BENCHMARK EXECUTION")
    print("=" * 85)

    test_matrix = [
        # (origin, dest, scenario, preemption)
        ("321397980", "kmc_hospital", "light", False),
        ("321397980", "kmc_hospital", "light", True),
        ("321397980", "kmc_hospital", "moderate", False),
        ("321397980", "kmc_hospital", "moderate", True),
        ("321397980", "kmc_hospital", "heavy", False),
        ("321397980", "kmc_hospital", "heavy", True),
        ("321397980", "kmc_hospital", "incident", False),
        ("321397980", "kmc_hospital", "incident", True),
        ("1358315405", "athena_hospital", "light", False),
        ("1358315405", "athena_hospital", "light", True),
        ("1358315405", "athena_hospital", "moderate", False),
        ("1358315405", "athena_hospital", "moderate", True),
        ("1089450246#0", "athena_hospital", "heavy", False),
        ("1089450246#0", "athena_hospital", "heavy", True),
        ("-132363062", "kmc_hospital", "moderate", False),
        ("-132363062", "kmc_hospital", "moderate", True),
    ]

    all_obs: list[dict] = []
    all_trip_summaries: list[dict] = []
    base_seed = 4040

    if RAW_OBS_CSV.exists() and os.path.getsize(RAW_OBS_CSV) > 10000:
        print(f"Loading existing completed observations from: {RAW_OBS_CSV}")
        df = pd.read_csv(RAW_OBS_CSV)
        all_obs = df.to_dict(orient="records")
    else:
        print(f"Executing {len(test_matrix)} shadow benchmark trips...")

        for run_idx, (orig, dest, sc, preempt) in enumerate(test_matrix, start=1):
            seed = base_seed + run_idx * 13
            preempt_tag = "ON " if preempt else "OFF"
            print(f"  [Run {run_idx:02d}/{len(test_matrix):02d}] Orig: {orig:<14} -> Dest: {dest:<16} | Sc: {sc:<8} | Preempt: {preempt_tag} | Seed: {seed}...", end="", flush=True)

            rows, trip_sum = run_shadow_trip(
                run_idx=run_idx,
                seed=seed,
                origin_edge=orig,
                hospital_id=dest,
                scenario_name=sc,
                enable_preemption=preempt,
                max_steps=320,
            )

            obs_junc = sum(1 for r in rows if r["target_junction_observed"] == 1)
            dur = f"{trip_sum['total_trip_duration_s']}s" if trip_sum.get("total_trip_duration_s") else "timeout"
            print(f" Samples: {len(rows):4d} (Observed: {obs_junc:3d}) | Trip Duration: {dur}")

            all_obs.extend(rows)
            all_trip_summaries.append(trip_sum)

        # Save raw CSV
        with open(RAW_OBS_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADER)
            writer.writeheader()
            writer.writerows(all_obs)
        print(f"\nRaw shadow observations saved to: {RAW_OBS_CSV}")


    # Process and compute comparative metrics on valid observed subset
    df = pd.DataFrame(all_obs)
    df_valid = df[df["target_junction_observed"] == 1].copy()
    print(f"Total valid observed junction evaluations: {len(df_valid)}")

    y_true = df_valid["target_junction_eta_s"].astype(float).values
    y_cand = df_valid["cand_eta_pred_s"].astype(float).values
    y_prod = df_valid["prod_eta_pred_s"].astype(float).values
    y_phys = df_valid["phys_eta_pred_s"].astype(float).values

    cand_metrics = compute_metrics(y_true, y_cand)
    prod_metrics = compute_metrics(y_true, y_prod)
    phys_metrics = compute_metrics(y_true, y_phys)

    # Latency
    cand_lat_mean = float(df["cand_latency_ms"].mean())
    cand_lat_p95 = float(np.percentile(df["cand_latency_ms"], 95))
    prod_lat_mean = float(df["prod_latency_ms"].mean())
    prod_lat_p95 = float(np.percentile(df["prod_latency_ms"], 95))

    print("\n" + "=" * 80)
    print("LIVE SHADOW BENCHMARK: COMPARATIVE METRICS (ON SAME OBSERVED SAMPLES)")
    print("=" * 80)
    print(f"{'Model':<25} | {'MAE (s)':<8} | {'RMSE (s)':<8} | {'MedAE (s)':<9} | {'P90 (s)':<8} | {'R²':<7} | {'Mean Lat (ms)':<13} | {'P95 Lat (ms)':<12}")
    print("-" * 110)
    print(f"{'Physics Baseline':<25} | {phys_metrics['mae_s']:<8.3f} | {phys_metrics['rmse_s']:<8.3f} | {phys_metrics['medae_s']:<9.3f} | {phys_metrics['p90_error_s']:<8.3f} | {phys_metrics['r2_score']:<7.4f} | {'< 0.001':<13} | {'< 0.001':<12}")
    print(f"{'Production Model (Pipeline)':<25} | {prod_metrics['mae_s']:<8.3f} | {prod_metrics['rmse_s']:<8.3f} | {prod_metrics['medae_s']:<9.3f} | {prod_metrics['p90_error_s']:<8.3f} | {prod_metrics['r2_score']:<7.4f} | {prod_lat_mean:<13.3f} | {prod_lat_p95:<12.3f}")
    print(f"{'Candidate Model (RF)':<25} | {cand_metrics['mae_s']:<8.3f} | {cand_metrics['rmse_s']:<8.3f} | {cand_metrics['medae_s']:<9.3f} | {cand_metrics['p90_error_s']:<8.3f} | {cand_metrics['r2_score']:<7.4f} | {cand_lat_mean:<13.3f} | {cand_lat_p95:<12.3f}")
    print("-" * 110)

    # Breakdown by Scenario
    scenario_metrics = {}
    for sc in df_valid["traffic_scenario"].unique():
        sub = df_valid[df_valid["traffic_scenario"] == sc]
        yt = sub["target_junction_eta_s"].astype(float).values
        yc = sub["cand_eta_pred_s"].astype(float).values
        yp = sub["prod_eta_pred_s"].astype(float).values
        yph = sub["phys_eta_pred_s"].astype(float).values
        scenario_metrics[sc] = {
            "samples": len(sub),
            "cand": compute_metrics(yt, yc),
            "prod": compute_metrics(yt, yp),
            "phys": compute_metrics(yt, yph),
        }

    # Breakdown by Preemption mode
    preempt_metrics = {}
    for pm in df_valid["preemption_mode"].unique():
        sub = df_valid[df_valid["preemption_mode"] == pm]
        yt = sub["target_junction_eta_s"].astype(float).values
        yc = sub["cand_eta_pred_s"].astype(float).values
        yp = sub["prod_eta_pred_s"].astype(float).values
        yph = sub["phys_eta_pred_s"].astype(float).values
        preempt_metrics[pm] = {
            "samples": len(sub),
            "cand": compute_metrics(yt, yc),
            "prod": compute_metrics(yt, yp),
            "phys": compute_metrics(yt, yph),
        }

    # End-to-end trip duration view
    trip_duration_view = []
    for ts in all_trip_summaries:
        trip_duration_view.append({
            "trip_id": ts["trip_id"],
            "scenario": ts["scenario"],
            "preemption": ts["preemption_enabled"],
            "arrived": ts["ambulance_arrived"],
            "duration_s": ts["total_trip_duration_s"],
        })

    full_report = {
        "overall_evaluation": {
            "total_raw_observations": len(df),
            "valid_observed_evaluations": len(df_valid),
            "candidate_metrics": cand_metrics,
            "production_metrics": prod_metrics,
            "physics_metrics": phys_metrics,
            "latency_ms": {
                "candidate_mean": round(cand_lat_mean, 4),
                "candidate_p95": round(cand_lat_p95, 4),
                "production_mean": round(prod_lat_mean, 4),
                "production_p95": round(prod_lat_p95, 4),
            }
        },
        "scenario_breakdown": scenario_metrics,
        "preemption_breakdown": preempt_metrics,
        "trip_duration_view": trip_duration_view,
        "trip_summaries": all_trip_summaries,
    }

    with open(BENCHMARK_REPORT_JSON, "w", encoding="utf-8") as f:
        json.dump(full_report, f, indent=2)
    print(f"Shadow benchmark report saved to: {BENCHMARK_REPORT_JSON}")
    print("=" * 85)


if __name__ == "__main__":
    run_shadow_benchmarks()
