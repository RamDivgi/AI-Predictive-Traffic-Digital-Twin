"""
AI PREDICTIVE TRAFFIC - COMPREHENSIVE REROUTING EXPERIMENT MATRIX
================================================================
Evaluates baseline (static route) vs AI-assisted dynamic rerouting across
multiple scenarios and repetitions, with explicit tracking of trip completion,
actual travel times, timeouts, and route stability.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
import sumolib
import traci

PROJECT_ROOT = Path("D:/AIML/Projects/Major")
PY_ROOT = PROJECT_ROOT / "AI-Predictive-Traffic"
sys.path.append(str(PY_ROOT / "controller"))

import config
import astar_router
import route_evaluator
import junction_detector
from traffic_aware_controller import TrafficAwareController

MANGALURU_NET = PY_ROOT / "simulation" / "mangaluru" / "mangaluru_ai.net.xml.gz"
config.NET_FILE = MANGALURU_NET
SUMOCFG = PY_ROOT / "simulation" / "mangaluru" / "ambulance_test.sumocfg"

_m_net = sumolib.net.readNet(str(MANGALURU_NET))
route_evaluator._SUMO_NETWORK = _m_net
astar_router._SUMO_NETWORK = _m_net
junction_detector.SUMO_NETWORK = _m_net


def run_single_simulation(
    scenario_name: str,
    congestion_edge: str | None,
    congestion_speed_mps: float | None,
    num_blockers: int,
    enable_rerouting: bool,
    seed: int = 42,
    hospital_id: str = "highland_hospital",
    max_steps: int = 700,
) -> dict:
    try:
        traci.close()
    except Exception:
        pass

    traci.start([
        "sumo",
        "-c", str(SUMOCFG),
        "--step-length", "1.0",
        "--seed", str(seed),
        "--no-warnings"
    ])

    controller = None
    if enable_rerouting:
        controller = TrafficAwareController()
        controller.rerouting_controller.min_improvement_s = 5.0
        controller.rerouting_controller.min_improvement_percent = 2.0
        controller.rerouting_controller.cooldown_s = 15.0
        controller.set_hospital_destination(hospital_id)

    ambulance_spawned = False
    start_time = None
    end_time = None
    reached = False
    initial_route_id = None
    final_route_id = None
    reroute_count = 0
    route_dist_m = 0.0
    time_stopped_s = 0.0

    target_edge = "-26299202#3"
    step = 0

    while step < max_steps:
        traci.simulationStep()
        curr_time = traci.simulation.getTime()

        # Inject scenario condition at step 15
        if step == 15 and congestion_edge:
            try:
                if congestion_speed_mps is not None:
                    traci.edge.setMaxSpeed(congestion_edge, congestion_speed_mps)
                if num_blockers > 0:
                    block_r = f"block_r_{scenario_name}_{enable_rerouting}_{seed}"
                    traci.route.add(block_r, [congestion_edge])
                    for i in range(min(num_blockers, 8)):
                        vid = f"blocker_{i}_{seed}"
                        traci.vehicle.add(vid, block_r, typeID="passenger")
                        traci.vehicle.moveTo(vid, f"{congestion_edge}_0", 5.0 + i * 8.0)
                        traci.vehicle.setSpeed(vid, 0.0)
            except Exception:
                pass

        vehs = traci.vehicle.getIDList()
        if "ambulance" in vehs:
            if not ambulance_spawned:
                ambulance_spawned = True
                start_time = curr_time
                initial_route_id = traci.vehicle.getRouteID("ambulance")
                final_route_id = initial_route_id
                route_edges = traci.vehicle.getRoute("ambulance")
                route_dist_m = sum(_m_net.getEdge(e).getLength() for e in route_edges if _m_net.hasEdge(e))

            speed = traci.vehicle.getSpeed("ambulance")
            if speed < 0.1:
                time_stopped_s += 1.0

            curr_edge = traci.vehicle.getRoadID("ambulance")
            if curr_edge == target_edge:
                reached = True
                end_time = curr_time
                break

            if enable_rerouting and controller:
                controller.process_step()
                status = controller.rerouting_controller.get_status()
                reroute_count = status.reroute_count
                final_route_id = status.current_route_id

        elif ambulance_spawned:
            reached = True
            end_time = curr_time
            break

        step += 1

    if end_time is None:
        end_time = traci.simulation.getTime()

    travel_time = (end_time - start_time) if start_time else (max_steps * 1.0)
    final_route_edges = traci.route.getEdges(final_route_id) if (final_route_id and final_route_id in traci.route.getIDList()) else []
    final_dist_m = sum(_m_net.getEdge(e).getLength() for e in final_route_edges if _m_net.hasEdge(e)) if final_route_edges else route_dist_m

    traci.close()

    return {
        "scenario": scenario_name,
        "seed": seed,
        "mode": "AI-Rerouting" if enable_rerouting else "Baseline",
        "reached": reached,
        "travel_time_s": round(travel_time, 1),
        "stopped_time_s": round(time_stopped_s, 1),
        "initial_dist_m": round(route_dist_m, 1),
        "final_dist_m": round(final_dist_m, 1),
        "reroute_count": reroute_count,
    }


def run_experiment_matrix():
    print("=" * 105)
    print("RIGOROUS CONGESTION-AWARE ROUTING EXPERIMENT MATRIX (REPEATED TRIALS)")
    print("=" * 105)

    # Scenarios tested:
    # 1. Light traffic (baseline speed, clear)
    # 2. Moderate traffic (flow slowed to 2.5 m/s on critical corridor 184750308#18)
    # 3. Severe congestion (0.5 m/s bottleneck with 2 blockers on 184750308#18)
    # 4. Total road blockage (0.001 m/s complete roadblock on 184750308#18)
    # 5. Detour not beneficial (alternate edge 1369161863#1 congested, direct corridor optimal)
    test_configs = [
        ("1. Light Traffic", None, None, 0),
        ("2. Moderate Slowdown (2.5 m/s)", "184750308#18", 2.5, 0),
        ("3. Severe Congestion (0.5 m/s)", "184750308#18", 0.5, 2),
        ("4. Roadblock Bottleneck", "184750308#18", 0.001, 3),
        ("5. Detour Not Beneficial", "1369161863#1", 1.0, 1),
    ]

    seeds = [42, 101, 2024]
    aggregated_results = []

    for name, edge, speed_limit, blockers in test_configs:
        print(f"\n--- Testing Scenario: {name} ---")
        base_runs = []
        ai_runs = []

        for s in seeds:
            res_b = run_single_simulation(name, edge, speed_limit, blockers, enable_rerouting=False, seed=s)
            res_a = run_single_simulation(name, edge, speed_limit, blockers, enable_rerouting=True, seed=s)
            base_runs.append(res_b)
            ai_runs.append(res_a)
            print(f"  Seed {s:4}: Base time={res_b['travel_time_s']}s (Reached={res_b['reached']}) | AI time={res_a['travel_time_s']}s (Reached={res_a['reached']}, Reroutes={res_a['reroute_count']})")

        # Average across seeds
        b_times = [r["travel_time_s"] for r in base_runs]
        a_times = [r["travel_time_s"] for r in ai_runs]
        b_reached = sum(1 for r in base_runs if r["reached"])
        a_reached = sum(1 for r in ai_runs if r["reached"])
        b_stopped = [r["stopped_time_s"] for r in base_runs]
        a_stopped = [r["stopped_time_s"] for r in ai_runs]
        reroutes = [r["reroute_count"] for r in ai_runs]

        mean_b_time = sum(b_times) / len(b_times)
        mean_a_time = sum(a_times) / len(a_times)
        mean_b_stop = sum(b_stopped) / len(b_stopped)
        mean_a_stop = sum(a_stopped) / len(a_stopped)
        mean_reroutes = sum(reroutes) / len(reroutes)

        if b_reached == len(seeds):
            saved_s = mean_b_time - mean_a_time
            pct_saved = (saved_s / mean_b_time * 100.0) if mean_b_time > 0 else 0.0
            status = f"Completed ({pct_saved:+.1f}%)"
        elif b_reached == 0:
            saved_s = mean_b_time - mean_a_time
            pct_saved = (saved_s / mean_b_time * 100.0)
            status = "Base Stuck (Timeout)"
        else:
            saved_s = mean_b_time - mean_a_time
            pct_saved = (saved_s / mean_b_time * 100.0)
            status = f"Base Partial ({b_reached}/{len(seeds)})"

        aggregated_results.append({
            "scenario": name,
            "base_reached": f"{b_reached}/{len(seeds)}",
            "ai_reached": f"{a_reached}/{len(seeds)}",
            "mean_base_time": mean_b_time,
            "mean_ai_time": mean_a_time,
            "mean_base_stop": mean_b_stop,
            "mean_ai_stop": mean_a_stop,
            "saved_s": saved_s,
            "pct_saved": pct_saved,
            "mean_reroutes": mean_reroutes,
            "status": status,
        })

    print("\n" + "=" * 115)
    print(f"{'Scenario':<28} | {'Base Reached':<12} | {'AI Reached':<10} | {'Base Time':<10} | {'AI Time':<9} | {'Saved (s)':<10} | {'Savings %':<10} | {'Reroutes':<8} | {'Verdict'}")
    print("=" * 115)
    for r in aggregated_results:
        print(f"{r['scenario']:<28} | {r['base_reached']:<12} | {r['ai_reached']:<10} | {r['mean_base_time']:<10.1f} | {r['mean_ai_time']:<9.1f} | {r['saved_s']:<10.1f} | {r['pct_saved']:<9.1f}% | {r['mean_reroutes']:<8.1f} | {r['status']}")
    print("=" * 115)


if __name__ == "__main__":
    run_experiment_matrix()
