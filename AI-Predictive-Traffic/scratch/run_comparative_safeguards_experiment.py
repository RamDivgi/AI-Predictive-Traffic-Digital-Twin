"""
FAIR COMPARATIVE EVALUATION EXPERIMENT
======================================
Compares 3 distinct architectural configurations across Low, Medium, and High traffic:
1. Baseline: Fixed-time signals, Static initial A* route, No preemption
2. Uncontrolled AI: Dynamic rerouting with no cooldown (0s), aggressive 2s threshold, standard preemption
3. Proposed Safeguarded AI: Reroute cooldown (30s), 10s threshold, oscillation suppression, movement-specific preemption, 8s min hold, 45s fail-safe timeout, clean restoration
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "controller"))
sys.path.insert(0, str(PROJECT_ROOT))

import sumolib
import traci

import config
import astar_router
import route_evaluator
import junction_detector
from traffic_aware_controller import TrafficAwareController
from rerouting_controller import ReroutingController

# Network setup
MANGALURU_NET = PROJECT_ROOT / "simulation" / "mangaluru" / "mangaluru_ai.net.xml.gz"
config.NET_FILE = MANGALURU_NET
astar_router.NETWORK_FILE = MANGALURU_NET
route_evaluator.NETWORK_FILE = MANGALURU_NET
junction_detector.NETWORK_FILE = MANGALURU_NET

_mangaluru_net_instance = sumolib.net.readNet(str(MANGALURU_NET))
route_evaluator._SUMO_NETWORK = _mangaluru_net_instance
astar_router._SUMO_NETWORK = _mangaluru_net_instance
junction_detector.SUMO_NETWORK = _mangaluru_net_instance

SUMOCFG = PROJECT_ROOT / "simulation" / "mangaluru" / "ambulance_test.sumocfg"


def run_single_trial(
    config_name: str,
    congestion_level: str,
    blocker_count: int,
    blocker_edge: str = "184750308#18",
    hospital_id: str = "highland_hospital",
    max_steps: int = 1000,
) -> dict:
    print(f"\n--- Running Trial: Config='{config_name}', Traffic='{congestion_level}' ---")
    
    try:
        traci.close()
    except Exception:
        pass
        
    traci.start(["sumo", "-c", str(SUMOCFG), "--step-length", "1.0", "--no-warnings", "true"])
    
    controller = TrafficAwareController()
    
    # Configure experimental condition
    if config_name == "Baseline":
        # Disable rerouting and preemption
        enable_rerouting = False
        enable_preemption = False
        emergency_param = "false"
    elif config_name == "Uncontrolled_AI":
        # Aggressive rerouting with no cooldown or oscillation safeguards
        enable_rerouting = True
        enable_preemption = True
        emergency_param = "true"
        controller.rerouting_controller.cooldown_s = 0.0
        controller.rerouting_controller.min_improvement_s = 2.0
        controller.rerouting_controller.min_improvement_percent = 1.0
        controller.rerouting_controller.oscillation_penalty_factor = 1.0
    elif config_name == "Safeguarded_AI":
        # Proposed controller with full safeguards
        enable_rerouting = True
        enable_preemption = True
        emergency_param = "true"
        controller.rerouting_controller.cooldown_s = 30.0
        controller.rerouting_controller.min_improvement_s = 10.0
        controller.rerouting_controller.min_improvement_percent = 5.0
        controller.rerouting_controller.oscillation_penalty_factor = 2.0
        controller.rerouting_controller.oscillation_window_s = 90.0
    else:
        raise ValueError(f"Unknown config: {config_name}")

    ambulance_spawned = False
    start_time = -1.0
    end_time = -1.0
    reached_dest = False
    time_stopped_s = 0.0
    preemptions_count = 0
    preempted_tls = set()
    initial_route = []
    final_route = []
    total_distance_m = 0.0
    target_edge = None
    
    step = 0
    while step < max_steps:
        traci.simulationStep()
        
        # Inject congestion scenario at step 15
        if step == 15 and blocker_count > 0:
            try:
                traci.edge.setMaxSpeed(blocker_edge, 0.05)
                route_id = f"block_route_{config_name}_{congestion_level}"
                traci.route.add(route_id, [blocker_edge])
                for i in range(min(blocker_count, 8)):
                    vid = f"blocker_{i}"
                    traci.vehicle.add(vid, route_id, typeID="passenger")
                    pos = 5.0 + i * 8.0
                    try:
                        traci.vehicle.moveTo(vid, f"{blocker_edge}_0", pos)
                        traci.vehicle.setSpeed(vid, 0.0)
                    except Exception:
                        pass
            except Exception:
                pass
                
        vehicles = traci.vehicle.getIDList()
        if "ambulance" in vehicles:
            if not ambulance_spawned:
                ambulance_spawned = True
                start_time = traci.simulation.getTime()
                traci.vehicle.setParameter("ambulance", "emergency", emergency_param)
                controller.set_hospital_destination(hospital_id)
                target_edge = controller.destination_hospital.nearest_edge if controller.destination_hospital else None
                try:
                    initial_route = list(traci.vehicle.getRoute("ambulance"))
                except Exception:
                    pass
                    
            curr_edge = traci.vehicle.getRoadID("ambulance")
            spd = traci.vehicle.getSpeed("ambulance")
            if spd < 0.1:
                time_stopped_s += 1.0
                
            try:
                total_distance_m = traci.vehicle.getDistance("ambulance")
            except Exception:
                pass
                
            if target_edge and curr_edge == target_edge:
                reached_dest = True
                end_time = traci.simulation.getTime()
                break
                
            # Process AI control logic if enabled
            if enable_preemption or enable_rerouting:
                decisions = controller.process_step()
                for feat, dec in decisions:
                    if dec.should_preempt and feat.junction_id not in preempted_tls:
                        preempted_tls.add(feat.junction_id)
            else:
                # Baseline: advance signals normally without AI interference
                pass
                
        elif ambulance_spawned:
            reached_dest = True
            end_time = traci.simulation.getTime()
            break
            
        step += 1

    if end_time < 0.0:
        end_time = traci.simulation.getTime()
        
    try:
        final_route = list(traci.vehicle.getRoute("ambulance"))
    except Exception:
        final_route = initial_route

    traci.close()
    
    travel_time_s = end_time - start_time if ambulance_spawned else 0.0
    reroute_count = controller.rerouting_controller.reroute_count if enable_rerouting else 0
    history = controller.rerouting_controller.get_history() if enable_rerouting else []
    
    res = {
        "config": config_name,
        "congestion_level": congestion_level,
        "blockers": blocker_count,
        "travel_time_s": round(travel_time_s, 1),
        "reached_destination": reached_dest,
        "time_stopped_s": round(time_stopped_s, 1),
        "reroute_count": reroute_count,
        "preemptions_fired": len(preempted_tls),
        "total_distance_m": round(total_distance_m, 1),
        "route_changes": len(history),
    }
    print(f"Result: {res}")
    return res


def main():
    print("=" * 80)
    print("STARTING CONTROLLED COMPARATIVE EXPERIMENT")
    print("=" * 80)
    
    scenarios = [
        ("Low", 0),       # Free-flowing arterial
        ("Medium", 2),    # Moderate bottleneck (2 stopped vehicles)
        ("High", 5),      # Severe bottleneck (5 stopped vehicles + reduced speed)
    ]
    
    configs = [
        "Baseline",
        "Uncontrolled_AI",
        "Safeguarded_AI",
    ]
    
    results = []
    
    for level, blockers in scenarios:
        for cfg in configs:
            res = run_single_trial(cfg, level, blockers)
            results.append(res)
            time.sleep(1.0)
            
    out_file = PROJECT_ROOT / "scratch" / "comparative_experiment_results.json"
    with open(out_file, "w") as f:
        json.dump(results, f, indent=2)
        
    print("\n" + "=" * 80)
    print("EXPERIMENT COMPLETE — SUMMARY TABLE")
    print("=" * 80)
    print(f"{'Congestion':<10} | {'Configuration':<17} | {'Travel Time':<11} | {'Stopped':<8} | {'Reroutes':<8} | {'Preempts':<8} | {'Arrival'}")
    print("-" * 80)
    for r in results:
        arr = "PASS" if r['reached_destination'] else "FAIL"
        print(f"{r['congestion_level']:<10} | {r['config']:<17} | {r['travel_time_s']:>9.1f}s | {r['time_stopped_s']:>6.1f}s | {r['reroute_count']:>8} | {r['preemptions_fired']:>8} | {arr}")


if __name__ == "__main__":
    main()

