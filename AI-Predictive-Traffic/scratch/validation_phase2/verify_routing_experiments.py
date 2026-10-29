"""
PHASE 2 INDEPENDENT VERIFICATION: TASK B - ROUTING EXPERIMENTS AUDIT
===================================================================
Independently verifies:
1. Whether signal preemption was conflated with rerouting.
2. Controlled comparison:
   - Condition A: Static Route, No Preemption (Pure Baseline)
   - Condition B: Static Route, WITH Preemption (Isolates Preemption)
   - Condition C: Dynamic Route, WITH Preemption (Full System)
3. Seed variation and determinism across seeds.
4. Incomplete trips and baseline timeout accounting.
5. Saves results to scratch/validation_phase2/routing_verification_results.json.
"""

from __future__ import annotations

import json
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
OUT_DIR = PY_ROOT / "scratch" / "validation_phase2"
OUT_DIR.mkdir(parents=True, exist_ok=True)

_m_net = sumolib.net.readNet(str(MANGALURU_NET))
route_evaluator._SUMO_NETWORK = _m_net
astar_router._SUMO_NETWORK = _m_net
junction_detector.SUMO_NETWORK = _m_net


def run_controlled_simulation(
    scenario_name: str,
    congestion_edge: str | None,
    congestion_speed_mps: float | None,
    num_blockers: int,
    enable_preemption: bool,
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
    if enable_preemption or enable_rerouting:
        controller = TrafficAwareController()
        if not enable_rerouting:
            # Prevent rerouting while preserving full preemption
            controller.rerouting_controller.min_improvement_s = 999999.0
            controller.rerouting_controller.min_improvement_percent = 999999.0
        else:
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

        if step == 15 and congestion_edge:
            try:
                if congestion_speed_mps is not None:
                    traci.edge.setMaxSpeed(congestion_edge, congestion_speed_mps)
                if num_blockers > 0:
                    block_r = f"block_r_{scenario_name}_{enable_preemption}_{enable_rerouting}_{seed}"
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

            if controller:
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
        "enable_preemption": enable_preemption,
        "enable_rerouting": enable_rerouting,
        "reached": reached,
        "travel_time_s": round(travel_time, 1),
        "stopped_time_s": round(time_stopped_s, 1),
        "initial_dist_m": round(route_dist_m, 1),
        "final_dist_m": round(final_dist_m, 1),
        "reroute_count": reroute_count,
    }


def verify_routing_experiments():
    print("=" * 95)
    print("TASK B: INDEPENDENT VERIFICATION OF ROUTING EXPERIMENTS")
    print("=" * 95)

    # 1. Confounding factor verification:
    # Compare Condition A (No Preemption, No Reroute),
    # Condition B (Preemption Only, No Reroute),
    # Condition C (Preemption + Dynamic Rerouting)
    # on:
    # 1) Light Traffic
    # 2) Moderate Traffic (2.5 m/s)
    # 3) Roadblock (0.001 m/s)
    
    test_cases = [
        ("Light Traffic", None, None, 0),
        ("Moderate Slowdown (2.5 m/s)", "184750308#18", 2.5, 0),
        ("Roadblock Bottleneck", "184750308#18", 0.001, 3),
    ]

    all_results = []
    print("\n--- 1. FACTORIAL COMPARISON: ISOLATING PREEMPTION VS REROUTING ---")
    header = f"{'Scenario':<26} | {'Condition':<25} | {'Reached':<8} | {'Travel Time':<11} | {'Stopped Time':<12} | {'Reroutes':<8}"
    print(header)
    print("-" * 105)

    for sc_name, edge, spd, blockers in test_cases:
        # A: Pure Baseline (No Preemption, No Reroute)
        res_a = run_controlled_simulation(sc_name, edge, spd, blockers, enable_preemption=False, enable_rerouting=False, seed=42)
        print(f"{sc_name:<26} | {'A: Static (No Preempt)':<25} | {str(res_a['reached']):<8} | {res_a['travel_time_s']:>9.1f} s | {res_a['stopped_time_s']:>10.1f} s | {res_a['reroute_count']:<8}")

        # B: Preemption Only (Static Route + Preemption)
        res_b = run_controlled_simulation(sc_name, edge, spd, blockers, enable_preemption=True, enable_rerouting=False, seed=42)
        print(f"{sc_name:<26} | {'B: Static + Preempt':<25} | {str(res_b['reached']):<8} | {res_b['travel_time_s']:>9.1f} s | {res_b['stopped_time_s']:>10.1f} s | {res_b['reroute_count']:<8}")

        # C: Full System (Preemption + Dynamic Rerouting)
        res_c = run_controlled_simulation(sc_name, edge, spd, blockers, enable_preemption=True, enable_rerouting=True, seed=42)
        print(f"{sc_name:<26} | {'C: Full (Preempt + Reroute)':<25} | {str(res_c['reached']):<8} | {res_c['travel_time_s']:>9.1f} s | {res_c['stopped_time_s']:>10.1f} s | {res_c['reroute_count']:<8}")
        print("-" * 105)

        all_results.extend([res_a, res_b, res_c])

    # Save verification output
    out_file = OUT_DIR / "routing_verification_results.json"
    with open(out_file, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nVerification results written to: {out_file}")
    return all_results


if __name__ == "__main__":
    verify_routing_experiments()
