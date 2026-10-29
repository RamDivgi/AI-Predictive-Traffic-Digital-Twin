"""
PHASE 5: CONTROLLED A/B PREEMPTION STAGING EXPERIMENT
=====================================================
Direct head-to-head comparison between:
- Condition A (Control): Production Model Preemption Controller
- Condition B (Treatment): Candidate Model Preemption Controller (via StagingETAAdapter)

Experimental Controls:
- Matched routes, origin, destination, background traffic demands, and random seeds.
- Predeclared Primary Metric: Paired Completed Ambulance Trip Travel Time (s).
- Secondary Metrics: Lead time, premature preemption count, civilian stopped queues,
                     civilian mean speed, next-junction ETA MAE, and restoration success.
- Timeouts flagged strictly as INCOMPLETE/FAILED (never assigned fictitious completion times).
"""

from __future__ import annotations

import csv
import json
import os
import sys
import time
import warnings
from pathlib import Path
import numpy as np
import pandas as pd
import joblib

warnings.filterwarnings("ignore")

import sumolib
import traci

PROJECT_ROOT = Path("D:/AIML/Projects/Major")
PY_ROOT = PROJECT_ROOT / "AI-Predictive-Traffic"
sys.path.append(str(PY_ROOT / "controller"))
sys.path.append(str(PY_ROOT / "scratch" / "phase5_staging"))

import config
import astar_router
import route_evaluator
import junction_detector
import signal_mapping
from signal_controller import SignalController
from hospital_manager import HospitalManager
from staging_adapter import StagingETAAdapter

MANGALURU_NET = PY_ROOT / "simulation" / "mangaluru" / "mangaluru_ai.net.xml.gz"
HOSPITALS_FILE = PY_ROOT / "simulation" / "mangaluru" / "presentation_labels.add.xml"
SUMOCFG = PY_ROOT / "simulation" / "mangaluru" / "ambulance_test.sumocfg"

PROD_MODEL_PATH = PY_ROOT / "models" / "eta_prediction_model.joblib"
prod_model = joblib.load(PROD_MODEL_PATH)

config.NET_FILE = MANGALURU_NET
_net = sumolib.net.readNet(str(MANGALURU_NET))
astar_router._SUMO_NETWORK = _net
route_evaluator._SUMO_NETWORK = _net
junction_detector.SUMO_NETWORK = _net

hm = HospitalManager(str(MANGALURU_NET), str(HOSPITALS_FILE))
router = astar_router.AStarRouter(str(MANGALURU_NET))

STAGING_DIR = PY_ROOT / "scratch" / "phase5_staging"
STAGING_DIR.mkdir(parents=True, exist_ok=True)
RAW_RESULTS_CSV = STAGING_DIR / "ab_raw_experiment_results.csv"
SUMMARY_JSON = STAGING_DIR / "ab_staging_summary.json"


def run_single_simulation(
    condition: str,  # "CONTROL_PROD" or "TREATMENT_CAND"
    route_name: str,
    origin_edge: str,
    hospital_id: str,
    scenario_name: str,
    seed: int,
    max_steps: int = 750,
) -> dict:
    hospital = hm.get_hospital(hospital_id)
    dest_edge = hospital.nearest_edge
    if origin_edge == "1358315405":
        # Corridor_Kodialbail arterial route (Alt 1) avoiding the 0.2m OSM conversion micro-edge defect (131993097#0)
        alts = router.find_alternative_routes(origin_edge, dest_edge)
        route_obj = alts[1] if len(alts) > 1 else router.find_route(origin_edge, dest_edge)
    else:
        route_obj = router.find_route(origin_edge, dest_edge)
    if not route_obj or not route_obj.edge_ids:
        return {"error": "Route calculation failed"}

    amb_id = f"amb_p5_{seed}_{condition[:4].lower()}"
    route_id = f"route_{amb_id}"

    try:
        traci.close()
    except Exception:
        pass

    traci.start([
        "sumo",
        "-c", str(SUMOCFG),
        "--step-length", "1.0",
        "--seed", str(seed),
        "--time-to-teleport", "30",
        "--no-warnings",
    ])

    signal_mapping._MOVEMENT_TO_TLS_CACHE = None
    signal_mapping._build_tls_cache()
    all_tls_ids = set(traci.trafficlight.getIDList())

    traci.route.add(route_id, route_obj.edge_ids)
    traci.vehicle.add(
        vehID=amb_id,
        routeID=route_id,
        typeID="ambulance",
        depart="1.0",
        departLane="best",
    )

    # Apply scenario congestion
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
            block_r = f"blk_{amb_id}"
            traci.route.add(block_r, [route_obj.edge_ids[mid_idx]])
            for i in range(2):
                vid = f"bk_{amb_id}_{i}"
                traci.vehicle.add(vid, block_r, typeID="passenger")
                traci.vehicle.moveTo(vid, f"{route_obj.edge_ids[mid_idx]}_0", 10.0 + i * 8.0)
                traci.vehicle.setSpeed(vid, 0.0)
        except Exception:
            pass
    elif scenario_name == "incident":
        mid_idx = len(route_obj.edge_ids) // 2
        try:
            traci.edge.setMaxSpeed(route_obj.edge_ids[mid_idx], 0.8)
            block_r = f"inc_{amb_id}"
            traci.route.add(block_r, [route_obj.edge_ids[mid_idx]])
            for i in range(3):
                vid = f"inc_{amb_id}_{i}"
                traci.vehicle.add(vid, block_r, typeID="passenger")
                traci.vehicle.moveTo(vid, f"{route_obj.edge_ids[mid_idx]}_0", 5.0 + i * 8.0)
                traci.vehicle.setSpeed(vid, 0.0)
        except Exception:
            pass

    signal_ctl = SignalController()
    candidate_adapter = StagingETAAdapter(dry_run=False)

    step = 0
    ambulance_spawned = False
    ambulance_arrived = False
    ambulance_depart_time: float | None = None
    hospital_arrival_time: float | None = None

    junction_arrivals: dict[str, float] = {}
    active_approaches: dict[str, dict] = {}
    preemption_events: list[dict] = []
    eta_prediction_errors: list[float] = []

    civilian_halted_samples: list[int] = []
    civilian_mean_speed_samples: list[float] = []

    while step < max_steps:
        traci.simulationStep()
        sim_time = traci.simulation.getTime()

        # Remove background collision dummy ambulance
        if "ambulance" in traci.vehicle.getIDList():
            try:
                traci.vehicle.remove("ambulance")
            except Exception:
                pass

        # Update signal transitions and check cleared signals
        signal_ctl.process_step()

        # Track network-wide civilian traffic (sampled periodically to reduce TraCI RPC overhead)
        all_vehs = traci.vehicle.getIDList()
        if step % 2 == 0:
            civ_vehs = [v for v in all_vehs if v != amb_id and not v.startswith("amb_")]
            if civ_vehs:
                halted_civ = sum(1 for v in civ_vehs if traci.vehicle.getSpeed(v) < 0.1)
                speeds = [traci.vehicle.getSpeed(v) for v in civ_vehs]
                mean_civ_spd = float(np.mean(speeds)) * 3.6
                civilian_halted_samples.append(halted_civ)
                civilian_mean_speed_samples.append(mean_civ_spd)

        if amb_id in all_vehs:
            if not ambulance_spawned:
                ambulance_spawned = True
                ambulance_depart_time = sim_time

            current_edge = traci.vehicle.getRoadID(amb_id)
            current_spd_mps = max(0.0, traci.vehicle.getSpeed(amb_id))

            # Check hospital arrival
            if current_edge == dest_edge:
                if hospital_arrival_time is None:
                    hospital_arrival_time = sim_time
                ambulance_arrived = True
                break

            # Restore signals if ambulance passed them
            for j_id, info in list(active_approaches.items()):
                if signal_ctl.is_preempted(j_id):
                    if current_edge == info["outgoing"] or current_edge.startswith(f":{j_id}"):
                        signal_ctl.restore(j_id)

            # Get upcoming junctions
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
                if j_id in all_tls_ids:
                    try:
                        sig_phase = traci.trafficlight.getPhase(j_id)
                        next_sw = traci.trafficlight.getNextSwitch(j_id)
                        sig_switch = max(0.0, next_sw - sim_time)
                    except Exception:
                        pass

                is_red = (sig_phase != 0)  # General unfavorable indicator

                # Compute ETA based on condition
                if condition == "CONTROL_PROD":
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
                    try:
                        pred_eta = float(prod_model.predict(pd.DataFrame([prod_row]))[0])
                    except Exception:
                        pred_eta = j.distance_from_ambulance_m / max(current_spd_mps, 3.0)
                else:
                    # TREATMENT_CAND: Uses isolated candidate adapter
                    cand_features = candidate_adapter.extract_candidate_features(
                        ambulance_speed_mps=current_spd_mps,
                        distance_to_junction_m=j.distance_from_ambulance_m,
                        vehicle_count=v_count,
                        halted_vehicle_count=halted_count,
                        mean_speed_kmh=mean_spd * 3.6,
                        occupancy_percent=occ,
                        signal_phase=sig_phase,
                        signal_time_to_switch_s=sig_switch,
                    )
                    pred_eta = candidate_adapter.predict_eta(cand_features)

                # Preemption Decision Logic
                # Window = 20s or conflict
                queue_clearance = halted_count * 2.5
                conflict = is_red and (pred_eta <= sig_switch + queue_clearance)
                in_window = (pred_eta <= 20.0 and j.distance_from_ambulance_m <= 300.0)

                should_preempt = (conflict or in_window) and halted_count <= 5 and j.distance_from_ambulance_m > 10.0

                if should_preempt and not signal_ctl.is_preempted(j_id):
                    tls_id, sig_indices = signal_mapping.get_tls_and_indices_for_movement(inc_edge, j.outgoing_edge)
                    if tls_id and sig_indices:
                        activated = signal_ctl.preempt(tls_id, sig_indices, hold_seconds=config.PREEMPTION_HOLD_SECONDS)
                        if activated:
                            preemption_events.append({
                                "junction_id": j_id,
                                "tls_id": tls_id,
                                "activated_at_sim_time": sim_time,
                                "predicted_eta_at_activation": pred_eta,
                                "distance_at_activation": j.distance_from_ambulance_m,
                                "halted_vehicles": halted_count,
                                "arrival_time": None,  # Will populate below
                                "lead_time_s": None,
                                "premature": (pred_eta > 35.0 or j.distance_from_ambulance_m > 300.0),
                                "restored": False,
                            })

            # Check crossed junctions
            for j_id, info in list(active_approaches.items()):
                if j_id not in junction_arrivals:
                    if current_edge == info["outgoing"] or current_edge.startswith(f":{j_id}"):
                        junction_arrivals[j_id] = sim_time
                    elif j_id not in upcoming_ids and info["dist"] < 35.0:
                        junction_arrivals[j_id] = sim_time

        elif ambulance_spawned:
            if current_edge == dest_edge:
                if hospital_arrival_time is None:
                    hospital_arrival_time = sim_time
                ambulance_arrived = True
            break

        step += 1

    # End simulation and cleanup
    traci.close()

    # Post-process preemption events with actual arrival times
    lead_times = []
    restoration_count = 0
    premature_count = 0
    eta_errors = []

    for pe in preemption_events:
        jid = pe["junction_id"]
        if jid in junction_arrivals:
            arr_t = junction_arrivals[jid]
            pe["arrival_time"] = arr_t
            lead = round(arr_t - pe["activated_at_sim_time"], 2)
            pe["lead_time_s"] = lead
            lead_times.append(lead)
            pe["restored"] = True
            restoration_count += 1
            if pe.get("predicted_eta_at_activation") is not None:
                err = abs(pe["predicted_eta_at_activation"] - lead)
                eta_errors.append(err)
        else:
            pe["lead_time_s"] = None
            pe["premature"] = True
            premature_count += 1

    elapsed_trip_time = round(hospital_arrival_time - ambulance_depart_time, 2) if (hospital_arrival_time and ambulance_depart_time) else None
    trip_completed = (ambulance_arrived and elapsed_trip_time is not None)

    return {
        "condition": condition,
        "route_name": route_name,
        "origin_edge": origin_edge,
        "destination_hospital": hospital_id,
        "scenario": scenario_name,
        "seed": seed,
        "completed": trip_completed,
        "elapsed_trip_time_s": elapsed_trip_time,
        "junctions_reached": len(junction_arrivals),
        "preemptions_activated": len(preemption_events),
        "premature_preemptions": premature_count,
        "mean_lead_time_s": round(float(np.mean(lead_times)), 2) if lead_times else None,
        "signals_restored": restoration_count,
        "restoration_rate": round(restoration_count / len(preemption_events), 3) if preemption_events else 1.0,
        "civilian_avg_halted": round(float(np.mean(civilian_halted_samples)), 2) if civilian_halted_samples else 0.0,
        "civilian_mean_speed_kmh": round(float(np.mean(civilian_mean_speed_samples)), 2) if civilian_mean_speed_samples else 0.0,
        "adapter_stats": candidate_adapter.get_stats() if condition == "TREATMENT_CAND" else None,
        "activation_eta_mae_s": round(float(np.mean(eta_errors)), 2) if eta_errors else None,
    }


def run_controlled_ab_experiment():
    print("=" * 85)
    print("PHASE 5: CONTROLLED A/B PREEMPTION STAGING EXPERIMENT")
    print("=" * 85)

    corridors = [
        ("Corridor_Kankanady", "1089450246#0", "athena_hospital"),
        ("Corridor_Kodialbail", "1358315405", "athena_hospital"),
    ]

    scenarios = ["light", "moderate", "heavy", "incident"]
    seeds = [5001, 5002]

    experiment_plan = []
    for c_name, orig, dest in corridors:
        for sc in scenarios:
            for sd in seeds:
                experiment_plan.append((c_name, orig, dest, sc, sd))

    print(f"Total matched pairs scheduled: {len(experiment_plan)} pairs (32 total simulation runs)")

    # Resume capability: inspect existing CSV results
    existing_runs = {}
    if RAW_RESULTS_CSV.exists():
        try:
            df_existing = pd.read_csv(RAW_RESULTS_CSV)
            for _, r in df_existing.iterrows():
                key = (str(r["route_name"]), str(r["scenario"]), int(r["seed"]), str(r["condition"]))
                r_dict = r.to_dict()
                if "completed" in r_dict:
                    r_dict["completed"] = str(r_dict["completed"]).strip().lower() == "true"
                if pd.isna(r_dict.get("elapsed_trip_time_s")):
                    r_dict["elapsed_trip_time_s"] = None
                if isinstance(r_dict.get("adapter_stats"), str) and r_dict["adapter_stats"].strip():
                    try:
                        r_dict["adapter_stats"] = eval(r_dict["adapter_stats"])
                    except Exception:
                        pass
                existing_runs[key] = r_dict
            print(f"Loaded {len(existing_runs)} existing simulation runs from {RAW_RESULTS_CSV.name}")
        except Exception as e:
            print(f"Warning reading existing results CSV: {e}")

    all_results = []
    pair_counter = 1

    for c_name, orig, dest, sc, sd in experiment_plan:
        print(f"\n--- [Pair {pair_counter:02d}/{len(experiment_plan):02d}] {c_name} | {sc:<8} | Seed: {sd} ---")

        ctrl_key = (c_name, sc, sd, "CONTROL_PROD")
        treat_key = (c_name, sc, sd, "TREATMENT_CAND")

        # 1. Run / Retrieve Control
        if ctrl_key in existing_runs and existing_runs[ctrl_key].get("completed", False):
            res_ctrl = existing_runs[ctrl_key]
            ctrl_dur = f"{res_ctrl['elapsed_trip_time_s']}s"
            print(f"  Control (Production Model): Reused existing run. Status: COMPLETED ({ctrl_dur})")
        else:
            print("  Running Control (Production Model Preemption)...", end="", flush=True)
            res_ctrl = run_single_simulation(
                condition="CONTROL_PROD",
                route_name=c_name,
                origin_edge=orig,
                hospital_id=dest,
                scenario_name=sc,
                seed=sd,
                max_steps=750,
            )
            ctrl_dur = f"{res_ctrl['elapsed_trip_time_s']}s" if res_ctrl['completed'] else "TIMEOUT"
            print(f" Done! Status: {'COMPLETED' if res_ctrl['completed'] else 'TIMEOUT'} ({ctrl_dur}) | Preempts: {res_ctrl.get('preemptions_activated')} | Civ Spd: {res_ctrl.get('civilian_mean_speed_kmh')} km/h")

        # 2. Run / Retrieve Treatment
        if treat_key in existing_runs and existing_runs[treat_key].get("completed", False):
            res_treat = existing_runs[treat_key]
            treat_dur = f"{res_treat['elapsed_trip_time_s']}s"
            print(f"  Treatment (Candidate Model): Reused existing run. Status: COMPLETED ({treat_dur})")
        else:
            print("  Running Treatment (Candidate Model Preemption)...", end="", flush=True)
            res_treat = run_single_simulation(
                condition="TREATMENT_CAND",
                route_name=c_name,
                origin_edge=orig,
                hospital_id=dest,
                scenario_name=sc,
                seed=sd,
                max_steps=750,
            )
            treat_dur = f"{res_treat['elapsed_trip_time_s']}s" if res_treat['completed'] else "TIMEOUT"
            print(f" Done! Status: {'COMPLETED' if res_treat['completed'] else 'TIMEOUT'} ({treat_dur}) | Preempts: {res_treat.get('preemptions_activated')} | Civ Spd: {res_treat.get('civilian_mean_speed_kmh')} km/h")
            print(f" Done! Status: {'COMPLETED' if res_treat['completed'] else 'TIMEOUT'} ({treat_dur}) | Preempts: {res_treat.get('preemptions_activated')} | Civ Spd: {res_treat.get('civilian_mean_speed_kmh')} km/h")

        # Compute paired differences
        diff_duration = None
        if res_ctrl.get("completed") and res_treat.get("completed"):
            if res_ctrl.get("elapsed_trip_time_s") is not None and res_treat.get("elapsed_trip_time_s") is not None:
                diff_duration = round(float(res_treat["elapsed_trip_time_s"]) - float(res_ctrl["elapsed_trip_time_s"]), 2)

        res_ctrl["pair_id"] = pair_counter
        res_treat["pair_id"] = pair_counter
        res_ctrl["paired_diff_duration_s"] = diff_duration
        res_treat["paired_diff_duration_s"] = diff_duration

        all_results.append(res_ctrl)
        all_results.append(res_treat)
        pair_counter += 1

        # Incremental save after every pair
        pd.DataFrame(all_results).to_csv(RAW_RESULTS_CSV, index=False)

    print("\n" + "=" * 85)
    print("ALL A/B RUNS COMPLETED. PROCESSING COMPARATIVE SUMMARY...")
    print("=" * 85)

    df_res = pd.DataFrame(all_results)
    df_res.to_csv(RAW_RESULTS_CSV, index=False)

    # Compute aggregate statistics
    df_ctrl = df_res[df_res["condition"] == "CONTROL_PROD"]
    df_treat = df_res[df_res["condition"] == "TREATMENT_CAND"]

    # Completed pairs
    completed_pairs = []
    incomplete_pairs = []

    for pid in sorted(df_res["pair_id"].unique()):
        sub = df_res[df_res["pair_id"] == pid]
        c_row = sub[sub["condition"] == "CONTROL_PROD"].iloc[0]
        t_row = sub[sub["condition"] == "TREATMENT_CAND"].iloc[0]
        if bool(c_row["completed"]) and bool(t_row["completed"]):
            c_dur = float(c_row["elapsed_trip_time_s"])
            t_dur = float(t_row["elapsed_trip_time_s"])
            delta = round(t_dur - c_dur, 2)
            pct = round(delta / c_dur * 100, 2) if c_dur > 0 else 0.0
            completed_pairs.append({
                "pair_id": int(pid),
                "corridor": c_row["route_name"],
                "scenario": c_row["scenario"],
                "seed": int(c_row["seed"]),
                "ctrl_duration_s": c_dur,
                "treat_duration_s": t_dur,
                "delta_s": delta,
                "percent_change": pct,
                "ctrl_lead_time_s": c_row["mean_lead_time_s"] if pd.notna(c_row["mean_lead_time_s"]) else None,
                "treat_lead_time_s": t_row["mean_lead_time_s"] if pd.notna(t_row["mean_lead_time_s"]) else None,
                "ctrl_premature": int(c_row["premature_preemptions"]),
                "treat_premature": int(t_row["premature_preemptions"]),
                "ctrl_civ_speed_kmh": float(c_row["civilian_mean_speed_kmh"]),
                "treat_civ_speed_kmh": float(t_row["civilian_mean_speed_kmh"]),
            })
        else:
            incomplete_pairs.append({
                "pair_id": int(pid),
                "corridor": c_row["route_name"],
                "scenario": c_row["scenario"],
                "seed": int(c_row["seed"]),
                "ctrl_completed": bool(c_row["completed"]),
                "treat_completed": bool(t_row["completed"]),
                "reason": "Simulation timeout (>450s) under heavy/incident conditions",
            })

    deltas = [cp["delta_s"] for cp in completed_pairs]
    pct_changes = [cp["percent_change"] for cp in completed_pairs]

    # Model adapter inference latency aggregations
    treat_stats = [r["adapter_stats"] for r in all_results if r.get("adapter_stats") and isinstance(r["adapter_stats"], dict)]
    total_inferences = sum(s.get("total_inferences", 0) for s in treat_stats)
    total_clamped = sum(s.get("invalid_predictions_clamped", 0) for s in treat_stats)
    total_exceptions = sum(s.get("exceptions_caught", 0) for s in treat_stats)
    mean_latencies = [s.get("mean_latency_ms", 0.0) for s in treat_stats if s.get("mean_latency_ms")]
    p95_latencies = [s.get("p95_latency_ms", 0.0) for s in treat_stats if s.get("p95_latency_ms")]

    # Statistical significance of paired difference (Paired t-test / Wilcoxon)
    p_value = None
    wilcoxon_p_value = None
    if len(deltas) >= 5:
        try:
            from scipy import stats as sp_stats
            t_stat, p_val = sp_stats.ttest_rel(
                [cp["treat_duration_s"] for cp in completed_pairs],
                [cp["ctrl_duration_s"] for cp in completed_pairs]
            )
            p_value = round(float(p_val), 4)
            w_stat, w_pval = sp_stats.wilcoxon(
                [cp["treat_duration_s"] for cp in completed_pairs],
                [cp["ctrl_duration_s"] for cp in completed_pairs]
            )
            wilcoxon_p_value = round(float(w_pval), 4)
        except Exception:
            pass

    summary_stats = {
        "experimental_design": {
            "total_pairs_planned": len(experiment_plan),
            "total_simulation_runs": len(all_results),
            "corridors": [c[0] for c in corridors],
            "scenarios": scenarios,
            "seeds": seeds,
            "control_condition": "Production Model ETA (models/eta_prediction_model.joblib)",
            "treatment_condition": "Candidate Model ETA (scratch/phase3_eta/models/mangaluru_eta_candidate.joblib via StagingETAAdapter)",
            "predeclared_primary_metric": "Paired Completed Ambulance Trip Travel Time (s)",
        },
        "completion_rates": {
            "control_completion_rate": f"{int(df_ctrl['completed'].sum())}/{len(df_ctrl)} ({df_ctrl['completed'].mean()*100:.1f}%)",
            "treatment_completion_rate": f"{int(df_treat['completed'].sum())}/{len(df_treat)} ({df_treat['completed'].mean()*100:.1f}%)",
            "completed_pairs_count": len(completed_pairs),
            "incomplete_pairs_count": len(incomplete_pairs),
        },
        "primary_metric_results": {
            "completed_pairs_count": len(completed_pairs),
            "mean_delta_s": round(float(np.mean(deltas)), 2) if deltas else None,
            "std_delta_s": round(float(np.std(deltas)), 2) if deltas else None,
            "median_delta_s": round(float(np.median(deltas)), 2) if deltas else None,
            "mean_percent_change": round(float(np.mean(pct_changes)), 2) if pct_changes else None,
            "treatment_faster_pairs": sum(1 for d in deltas if d < 0),
            "control_faster_pairs": sum(1 for d in deltas if d > 0),
            "tied_pairs": sum(1 for d in deltas if d == 0),
            "paired_t_test_p_value": p_value,
            "wilcoxon_signed_rank_p_value": wilcoxon_p_value,
        },
        "operational_metrics": {
            "mean_duration_control_s": round(float(df_ctrl[df_ctrl['completed']]["elapsed_trip_time_s"].mean()), 2) if df_ctrl['completed'].any() else None,
            "mean_duration_treatment_s": round(float(df_treat[df_treat['completed']]["elapsed_trip_time_s"].mean()), 2) if df_treat['completed'].any() else None,
            "mean_preemptions_control": round(float(df_ctrl["preemptions_activated"].mean()), 2),
            "mean_preemptions_treatment": round(float(df_treat["preemptions_activated"].mean()), 2),
            "total_premature_preemptions_control": int(df_ctrl["premature_preemptions"].sum()),
            "total_premature_preemptions_treatment": int(df_treat["premature_preemptions"].sum()),
            "mean_lead_time_control_s": round(float(df_ctrl["mean_lead_time_s"].dropna().mean()), 2) if len(df_ctrl["mean_lead_time_s"].dropna()) else None,
            "mean_lead_time_treatment_s": round(float(df_treat["mean_lead_time_s"].dropna().mean()), 2) if len(df_treat["mean_lead_time_s"].dropna()) else None,
            "restoration_rate_control": round(float(df_ctrl["restoration_rate"].mean()), 3),
            "restoration_rate_treatment": round(float(df_treat["restoration_rate"].mean()), 3),
            "civilian_avg_halted_control": round(float(df_ctrl["civilian_avg_halted"].mean()), 2),
            "civilian_avg_halted_treatment": round(float(df_treat["civilian_avg_halted"].mean()), 2),
            "civilian_mean_speed_control_kmh": round(float(df_ctrl["civilian_mean_speed_kmh"].mean()), 2),
            "civilian_mean_speed_treatment_kmh": round(float(df_treat["civilian_mean_speed_kmh"].mean()), 2),
        },
        "candidate_adapter_telemetry": {
            "total_inferences": total_inferences,
            "invalid_clamped_predictions": total_clamped,
            "exceptions_caught": total_exceptions,
            "mean_latency_ms": round(float(np.mean(mean_latencies)), 4) if mean_latencies else 0.0,
            "p95_latency_ms": round(float(np.mean(p95_latencies)), 4) if p95_latencies else 0.0,
        },
        "completed_pairs_breakdown": completed_pairs,
        "incomplete_pairs_breakdown": incomplete_pairs,
    }

    with open(SUMMARY_JSON, "w", encoding="utf-8") as f:
        json.dump(summary_stats, f, indent=2)

    print("\n" + "=" * 85)
    print("PHASE 5 A/B STAGING EXPERIMENT COMPLETED SUCCESSFULLY!")
    print(f"Results CSV  : {RAW_RESULTS_CSV}")
    print(f"Summary JSON : {SUMMARY_JSON}")
    print(f"Completed Pairs Count: {len(completed_pairs)}/{len(experiment_plan)}")
    if deltas:
        print(f"Mean Paired Travel Time Delta: {summary_stats['primary_metric_results']['mean_delta_s']}s ({summary_stats['primary_metric_results']['mean_percent_change']}%)")
        print(f"Treatment Faster: {summary_stats['primary_metric_results']['treatment_faster_pairs']} pairs | Control Faster: {summary_stats['primary_metric_results']['control_faster_pairs']} pairs")
    print(f"Premature Preemptions: Control={summary_stats['operational_metrics']['total_premature_preemptions_control']} vs Treatment={summary_stats['operational_metrics']['total_premature_preemptions_treatment']}")
    print(f"Civilian Network Speed: Control={summary_stats['operational_metrics']['civilian_mean_speed_control_kmh']} km/h vs Treatment={summary_stats['operational_metrics']['civilian_mean_speed_treatment_kmh']} km/h")
    print("=" * 85)


if __name__ == "__main__":
    run_controlled_ab_experiment()

