"""
Controlled Experiment: Baseline vs Proposed System Evaluation
Point 4 (edge 1096889856) to KMC Hospital (edge 1538932912#4)
Across Low, Medium, High, and Bottleneck Traffic Scenarios
"""
from __future__ import annotations

import csv
import json
import math
import os
import random
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import sumolib
import traci

# Paths setup
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "controller"))

import astar_router
import config
import junction_detector
import route_evaluator
from controller.hospital_manager import HospitalManager
from controller.traffic_aware_controller import TrafficAwareController
from visualization.unity_bridge import cleanup_simulation_traffic, generate_round_traffic

# Simulation configuration
SUMO_CONFIG = PROJECT_ROOT / "simulation" / "mangaluru" / "presentation_demo.sumocfg"
MANGALURU_NET = PROJECT_ROOT / "simulation" / "mangaluru" / "presentation_selection2.net.xml"
RESULTS_DIR = PROJECT_ROOT / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

CSV_OUTPUT_PATH = RESULTS_DIR / "baseline_vs_proposed_kmc_runs.csv"
JSON_OUTPUT_PATH = RESULTS_DIR / "baseline_vs_proposed_kmc_summary.json"
CHART_OUTPUT_PATH = RESULTS_DIR / "baseline_vs_proposed_kmc_chart.png"

# Align networks across modules
astar_router.NETWORK_FILE = MANGALURU_NET
route_evaluator.NETWORK_FILE = MANGALURU_NET
junction_detector.NETWORK_FILE = MANGALURU_NET
route_evaluator._SUMO_NETWORK = None
astar_router._SUMO_NETWORK = None
junction_detector.SUMO_NETWORK = sumolib.net.readNet(str(MANGALURU_NET))

# Configuration
ORIGIN_EDGE = "1096889856"
HOSPITAL_ID = "kmc_hospital"
SCENARIOS = ["low", "medium", "high", "bottleneck"]
SEEDS = [42, 101, 202, 303, 404]
MAX_SIMULATION_STEPS = 4000  # 400.0s hard ceiling at step-length 0.1s


def run_single_simulation(
    scenario: str,
    seed: int,
    mode: str,
    round_id: int,
    dest_edge: str,
) -> Dict[str, Any]:
    """
    Executes a single simulation run for either 'baseline' or 'proposed' mode.
    """
    is_proposed = mode == "proposed"

    sumo_cmd = [
        "sumo",
        "-c", str(SUMO_CONFIG),
        "--step-length", "0.1",
        "--seed", str(seed),
        "--ignore-route-errors",
        "--no-step-log",
        "--no-warnings",
        "--start"
    ]

    traci.start(sumo_cmd)
    
    ai_controller: Optional[TrafficAwareController] = None
    if is_proposed:
        ai_controller = TrafficAwareController()
        # Disable MQTT attempts to ensure zero network timeout overhead
        if hasattr(ai_controller, "control_egress") and hasattr(ai_controller.control_egress, "use_mqtt"):
            ai_controller.control_egress.use_mqtt = False

    dep_time: Optional[float] = None
    arr_time: Optional[float] = None
    travel_time: Optional[float] = None
    accum_waiting: float = 0.0
    preempt_count: int = 0
    preempted_tls: set = set()
    reroutes_count: int = 0
    completed: bool = False
    teleports_count: int = 0
    insertion_errors: int = 0
    
    try:
        # Generate traffic with deterministic seed
        active_scheduled = generate_round_traffic(
            round_id=round_id,
            current_time=0.0,
            scenario=scenario,
            seed=seed,
        )

        # Baseline & initial proposed route: candidate 0 shortest path from A*
        router = astar_router.AStarRouter()
        candidates = router.find_alternative_routes(ORIGIN_EDGE, dest_edge)
        initial_route_edges = candidates[0].edge_ids

        route_id = f"trip_{mode}_{scenario}_{seed}_{round_id}"
        traci.route.add(route_id, initial_route_edges)
        
        traci.vehicle.add(
            vehID="ambulance",
            routeID=route_id,
            typeID="ambulance",
            depart="now",
            departLane="best"
        )

        if is_proposed:
            traci.vehicle.setParameter("ambulance", "emergency", "true")
        else:
            traci.vehicle.setParameter("ambulance", "emergency", "false")

        ambulance_entered = False
        initial_assigned_route = list(initial_route_edges)

        step = 0
        while step < MAX_SIMULATION_STEPS:
            traci.simulationStep()
            step += 1
            sim_time = traci.simulation.getTime()
            active_vehs = traci.vehicle.getIDList()

            # Monitor teleports
            teleports_count += traci.simulation.getStartingTeleportNumber()

            if "ambulance" in active_vehs:
                if not ambulance_entered:
                    ambulance_entered = True
                    dep_time = sim_time
                    if is_proposed and ai_controller:
                        ai_controller.set_hospital_destination(HOSPITAL_ID)

                # Track ambulance accumulated waiting time
                try:
                    accum_waiting = traci.vehicle.getAccumulatedWaitingTime("ambulance")
                except Exception:
                    pass

                if is_proposed and ai_controller:
                    # Detect dynamic reroutes
                    try:
                        curr_route = list(traci.vehicle.getRoute("ambulance"))
                        if curr_route != initial_assigned_route:
                            reroutes_count += 1
                            initial_assigned_route = curr_route
                    except Exception:
                        pass

                    # Step controller (evaluates periodic rerouting and signal preemption)
                    decisions = ai_controller.process_step()
                    for feat, dec in decisions:
                        if dec.should_preempt:
                            if feat.junction_id not in preempted_tls:
                                preempted_tls.add(feat.junction_id)
                                preempt_count += 1
            else:
                # If ambulance entered and is now gone, it reached the destination edge
                if ambulance_entered and arr_time is None:
                    arr_time = sim_time
                    completed = True
                    break

        if completed and dep_time is not None and arr_time is not None:
            travel_time = round(arr_time - dep_time, 2)

    except Exception as e:
        print(f"Error during {mode} run ({scenario}, seed {seed}): {e}")
        insertion_errors += 1
    finally:
        if is_proposed and ai_controller:
            try:
                ai_controller.shutdown()
            except Exception:
                pass
        try:
            traci.close()
        except Exception:
            pass

    return {
        "scenario": scenario,
        "seed": seed,
        "mode": mode,
        "departure_time": dep_time,
        "arrival_time": arr_time,
        "travel_time": travel_time,
        "waiting_time": round(accum_waiting, 2),
        "reroutes": reroutes_count,
        "preemptions": preempt_count,
        "completed": completed,
        "teleports": teleports_count,
        "insertion_errors": insertion_errors,
        "status": "COMPLETED" if completed else "INCOMPLETE",
    }


def run_all_experiments() -> List[Dict[str, Any]]:
    hm = HospitalManager(str(config.NET_FILE), str(config.HOSPITALS_FILE))
    kmc = hm.get_hospital(HOSPITAL_ID)
    if not kmc or not kmc.nearest_edge:
        raise RuntimeError(f"KMC Hospital destination edge not found for {HOSPITAL_ID}")
    dest_edge = kmc.nearest_edge

    print("=" * 80)
    print("STARTING EXPERIMENT: BASELINE VS PROPOSED EVALUATION")
    print(f"Origin Edge: {ORIGIN_EDGE} (Point 4)")
    print(f"Destination Edge: {dest_edge} (KMC Hospital)")
    print(f"Scenarios: {SCENARIOS}")
    print(f"Seeds: {SEEDS}")
    print(f"Total Runs: {len(SCENARIOS) * len(SEEDS) * 2}")
    print("=" * 80)

    all_records: List[Dict[str, Any]] = []
    round_counter = 100
    start_real_time = time.time()

    for sc_idx, scenario in enumerate(SCENARIOS, 1):
        print(f"\n>>> Running Scenario [{sc_idx}/{len(SCENARIOS)}]: {scenario.upper()}")
        for s_idx, seed in enumerate(SEEDS, 1):
            pair_start = time.time()
            round_counter += 1
            print(f"  [Pair {s_idx}/{len(SEEDS)} | Seed {seed}] Running Baseline...", end=" ", flush=True)
            t0 = time.time()
            res_baseline = run_single_simulation(scenario, seed, "baseline", round_counter, dest_edge)
            t_base_elapsed = time.time() - t0
            print(f"Done ({t_base_elapsed:.1f}s real) -> TT: {res_baseline['travel_time']}s, Status: {res_baseline['status']}")

            round_counter += 1
            print(f"  [Pair {s_idx}/{len(SEEDS)} | Seed {seed}] Running Proposed...", end=" ", flush=True)
            t1 = time.time()
            res_proposed = run_single_simulation(scenario, seed, "proposed", round_counter, dest_edge)
            t_prop_elapsed = time.time() - t1
            print(f"Done ({t_prop_elapsed:.1f}s real) -> TT: {res_proposed['travel_time']}s, Status: {res_proposed['status']}")

            # Calculate paired delta if both completed
            if res_baseline["completed"] and res_proposed["completed"]:
                imp = ((res_baseline["travel_time"] - res_proposed["travel_time"]) / res_baseline["travel_time"]) * 100.0
                print(f"       -> Paired Improvement: {imp:+.2f}% (Saved {res_baseline['travel_time'] - res_proposed['travel_time']:.1f}s)")
            else:
                print("       -> Paired Comparison: Incomplete run present")

            all_records.append(res_baseline)
            all_records.append(res_proposed)

    total_time = time.time() - start_real_time
    print("\n" + "=" * 80)
    print(f"ALL SIMULATIONS COMPLETE in {total_time:.1f} seconds ({total_time / 60.0:.2f} minutes).")
    print("=" * 80)

    return all_records


def save_csv(records: List[Dict[str, Any]]) -> None:
    fieldnames = [
        "scenario",
        "seed",
        "mode",
        "departure_time",
        "arrival_time",
        "travel_time",
        "waiting_time",
        "reroutes",
        "preemptions",
        "completed",
        "teleports",
        "insertion_errors",
        "status",
    ]
    with open(CSV_OUTPUT_PATH, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)
    print(f"Saved raw CSV to {CSV_OUTPUT_PATH}")


def compute_statistics(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    summary: Dict[str, Any] = {}

    for scenario in SCENARIOS:
        sc_records = [r for r in records if r["scenario"] == scenario]
        base_runs = [r for r in sc_records if r["mode"] == "baseline"]
        prop_runs = [r for r in sc_records if r["mode"] == "proposed"]

        base_completed = [r for r in base_runs if r["completed"] and r["travel_time"] is not None]
        prop_completed = [r for r in prop_runs if r["completed"] and r["travel_time"] is not None]

        base_tt = [r["travel_time"] for r in base_completed]
        prop_tt = [r["travel_time"] for r in prop_completed]

        base_wait = [r["waiting_time"] for r in base_completed]
        prop_wait = [r["waiting_time"] for r in prop_completed]

        # Paired differences
        paired_diffs = []
        paired_pcts = []
        for s in SEEDS:
            b = next((r for r in base_completed if r["seed"] == s), None)
            p = next((r for r in prop_completed if r["seed"] == s), None)
            if b is not None and p is not None:
                diff = b["travel_time"] - p["travel_time"]
                pct = (diff / b["travel_time"]) * 100.0
                paired_diffs.append(diff)
                paired_pcts.append(pct)

        summary[scenario] = {
            "baseline": {
                "total_runs": len(base_runs),
                "completed_runs": len(base_completed),
                "completion_rate": len(base_completed) / max(1, len(base_runs)),
                "mean_travel_time": round(float(np.mean(base_tt)), 2) if base_tt else None,
                "median_travel_time": round(float(np.median(base_tt)), 2) if base_tt else None,
                "std_travel_time": round(float(np.std(base_tt, ddof=1)), 2) if len(base_tt) > 1 else 0.0,
                "mean_waiting_time": round(float(np.mean(base_wait)), 2) if base_wait else None,
            },
            "proposed": {
                "total_runs": len(prop_runs),
                "completed_runs": len(prop_completed),
                "completion_rate": len(prop_completed) / max(1, len(prop_runs)),
                "mean_travel_time": round(float(np.mean(prop_tt)), 2) if prop_tt else None,
                "median_travel_time": round(float(np.median(prop_tt)), 2) if prop_tt else None,
                "std_travel_time": round(float(np.std(prop_tt, ddof=1)), 2) if len(prop_tt) > 1 else 0.0,
                "mean_waiting_time": round(float(np.mean(prop_wait)), 2) if prop_wait else None,
                "mean_reroutes": round(float(np.mean([r["reroutes"] for r in prop_completed])), 2) if prop_completed else 0.0,
                "mean_preemptions": round(float(np.mean([r["preemptions"] for r in prop_completed])), 2) if prop_completed else 0.0,
            },
            "comparison": {
                "mean_paired_difference_s": round(float(np.mean(paired_diffs)), 2) if paired_diffs else None,
                "mean_improvement_percent": round(float(np.mean(paired_pcts)), 2) if paired_pcts else None,
                "paired_valid_count": len(paired_diffs),
            }
        }

    with open(JSON_OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"Saved summary JSON to {JSON_OUTPUT_PATH}")

    return summary


def plot_comparison_chart(summary: Dict[str, Any]) -> None:
    import matplotlib.pyplot as plt

    labels = [s.capitalize() for s in SCENARIOS]
    base_means = [summary[s]["baseline"]["mean_travel_time"] for s in SCENARIOS]
    base_stds = [summary[s]["baseline"]["std_travel_time"] for s in SCENARIOS]
    prop_means = [summary[s]["proposed"]["mean_travel_time"] for s in SCENARIOS]
    prop_stds = [summary[s]["proposed"]["std_travel_time"] for s in SCENARIOS]

    x = np.arange(len(labels))
    width = 0.35

    plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
    fig, ax = plt.subplots(figsize=(10, 6), dpi=300)

    rects1 = ax.bar(
        x - width / 2,
        base_means,
        width,
        yerr=base_stds,
        capsize=5,
        label="Mode A: Baseline System (Fixed Shortest Path, Normal Signals)",
        color="#e74c3c",
        edgecolor="#922b21",
        alpha=0.9,
    )
    rects2 = ax.bar(
        x + width / 2,
        prop_means,
        width,
        yerr=prop_stds,
        capsize=5,
        label="Mode B: Proposed AI System (Traffic-Aware Routing + Signal Preemption)",
        color="#2ecc71",
        edgecolor="#1e8449",
        alpha=0.9,
    )

    ax.set_ylabel("Completed-Trip Travel Time (Simulation Seconds)", fontsize=12, fontweight="bold")
    ax.set_xlabel("Traffic Scenarios (Point 4 to KMC Hospital)", fontsize=12, fontweight="bold")
    ax.set_title(
        "Ambulance Travel Time Evaluation: Baseline vs Proposed AI System\n"
        "(Origin: Edge 1096889856 → Destination: KMC Hospital 1538932912#4, N=5 paired repetitions/scenario)",
        fontsize=13,
        fontweight="bold",
        pad=15,
    )
    ax.set_xticks(x)
    ax.set_xticklabels([f"{l}\n(N=5 pairs)" for l in labels], fontsize=11)
    ax.legend(fontsize=10, loc="upper left", frameon=True)
    ax.grid(axis="y", linestyle="--", alpha=0.7)

    # Label bars with value and improvement percentage
    for i in range(len(labels)):
        b_val = base_means[i]
        p_val = prop_means[i]
        imp = summary[SCENARIOS[i]]["comparison"]["mean_improvement_percent"]
        if b_val is not None:
            ax.annotate(
                f"{b_val:.1f}s",
                xy=(x[i] - width / 2, b_val / 2),
                ha="center",
                va="center",
                color="white",
                fontweight="bold",
                fontsize=10,
            )
        if p_val is not None:
            ax.annotate(
                f"{p_val:.1f}s",
                xy=(x[i] + width / 2, p_val / 2),
                ha="center",
                va="center",
                color="white",
                fontweight="bold",
                fontsize=10,
            )
        if imp is not None:
            top_y = max(b_val, p_val) + 12
            ax.annotate(
                f"{imp:+.1f}%",
                xy=(x[i] + width / 2, top_y),
                ha="center",
                va="bottom",
                fontweight="bold",
                fontsize=10,
                color="#196f3d" if imp > 0 else "#922b21",
                bbox=dict(boxstyle="round,pad=0.2", facecolor="#eafaf1" if imp > 0 else "#fdedec", edgecolor="none")
            )

    plt.tight_layout()
    fig.savefig(CHART_OUTPUT_PATH)
    plt.close(fig)
    print(f"Saved comparison chart to {CHART_OUTPUT_PATH}")


if __name__ == "__main__":
    records = run_all_experiments()
    save_csv(records)
    stats = compute_statistics(records)
    plot_comparison_chart(stats)
