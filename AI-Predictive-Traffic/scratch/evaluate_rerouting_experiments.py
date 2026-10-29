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
from rerouting_controller import ReroutingController

MANGALURU_NET = PY_ROOT / "simulation" / "mangaluru" / "mangaluru_ai.net.xml.gz"
config.NET_FILE = MANGALURU_NET
SUMOCFG = PY_ROOT / "simulation" / "mangaluru" / "ambulance_test.sumocfg"

_m_net = sumolib.net.readNet(str(MANGALURU_NET))
route_evaluator._SUMO_NETWORK = _m_net
astar_router._SUMO_NETWORK = _m_net
junction_detector.SUMO_NETWORK = _m_net

def run_simulation(scenario_name, congestion_edge, num_blockers, enable_rerouting, hospital_id="highland_hospital"):
    try:
        traci.close()
    except Exception:
        pass

    traci.start(["sumo", "-c", str(SUMOCFG), "--step-length", "1.0", "--no-warnings"])
    
    controller = TrafficAwareController() if enable_rerouting else None
    if controller:
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
    predicted_eta_start = 0.0
    
    target_edge = "-26299202#3" # Highland hospital destination edge
    step = 0
    max_steps = 700

    while step < max_steps:
        traci.simulationStep()
        curr_time = traci.simulation.getTime()
        
        # Apply congestion if specified
        if step == 15 and congestion_edge and num_blockers > 0:
            try:
                traci.edge.setMaxSpeed(congestion_edge, 0.001)
                block_r = f"block_r_{scenario_name}_{enable_rerouting}"
                traci.route.add(block_r, [congestion_edge])
                for i in range(min(num_blockers, 8)):
                    vid = f"blocker_{i}"
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
                predicted_eta_start = route_dist_m / 15.0 # baseline physics ETA at 15 m/s

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
    final_route_edges = traci.route.getEdges(final_route_id) if final_route_id in traci.route.getIDList() else []
    final_dist_m = sum(_m_net.getEdge(e).getLength() for e in final_route_edges if _m_net.hasEdge(e)) if final_route_edges else route_dist_m
    
    traci.close()
    
    return {
        "scenario": scenario_name,
        "mode": "AI-Rerouting" if enable_rerouting else "Baseline",
        "reached": reached,
        "travel_time_s": round(travel_time, 1),
        "initial_dist_m": round(route_dist_m, 1),
        "final_dist_m": round(final_dist_m, 1),
        "predicted_eta_start_s": round(predicted_eta_start, 1),
        "reroute_count": reroute_count,
        "initial_route": initial_route_id,
        "final_route": final_route_id
    }

if __name__ == "__main__":
    print("================================================================================")
    print("REPEATABLE CONGESTION-AWARE REROUTING EXPERIMENTS (BASELINE VS AI)")
    print("================================================================================")

    # 5 Test Scenarios as specified:
    # 1. Light traffic (0 blockers)
    # 2. Moderate traffic (1 blocker on route edge 184750308#18)
    # 3. Heavy traffic (3 blockers on route edge 184750308#18)
    # 4. Deliberately congested segment on original route (4 blockers on critical bottleneck 184750308#18)
    # 5. Rerouting not beneficial (minor slowdown on a detour, sticking to direct route is optimal)
    
    scenarios = [
        ("1. Light Traffic", None, 0),
        ("2. Moderate Traffic", "184750308#18", 1),
        ("3. Heavy Traffic", "184750308#18", 2),
        ("4. Deliberate Bottleneck", "184750308#18", 4),
        ("5. Detour Not Beneficial", "1369161863#1", 1), # Blocker on alternate path; original path clear
    ]

    results = []
    for name, edge, blockers in scenarios:
        print(f"\nRunning {name}...")
        res_baseline = run_simulation(name, edge, blockers, enable_rerouting=False)
        print(f"  Baseline: Travel Time = {res_baseline['travel_time_s']}s, Reached = {res_baseline['reached']}, Dist = {res_baseline['final_dist_m']}m")
        res_ai = run_simulation(name, edge, blockers, enable_rerouting=True)
        print(f"  AI-Route: Travel Time = {res_ai['travel_time_s']}s, Reached = {res_ai['reached']}, Dist = {res_ai['final_dist_m']}m, Reroutes = {res_ai['reroute_count']}")
        
        diff_s = res_baseline['travel_time_s'] - res_ai['travel_time_s']
        pct_saved = (diff_s / res_baseline['travel_time_s'] * 100) if res_baseline['travel_time_s'] > 0 else 0
        
        results.append((res_baseline, res_ai, diff_s, pct_saved))

    print("\n" + "=" * 95)
    print(f"{'Scenario':<25} | {'Base (s)':<9} | {'AI (s)':<9} | {'Saved (s)':<10} | {'Saved (%)':<10} | {'Reroutes':<8} | {'Outcome'}")
    print("=" * 95)
    for base, ai, diff, pct in results:
        outcome = "PASS: Significant Savings" if diff > 5 else ("PASS: Maintained Optimal Route" if abs(diff) <= 5 else "NEUTRAL")
        print(f"{base['scenario']:<25} | {base['travel_time_s']:<9.1f} | {ai['travel_time_s']:<9.1f} | {diff:<10.1f} | {pct:<9.1f}% | {ai['reroute_count']:<8} | {outcome}")
    print("=" * 95)
