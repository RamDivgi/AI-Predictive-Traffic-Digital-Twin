"""
Pilot test: Point 4 to KMC Hospital for Baseline and Proposed modes
"""
import sys
from pathlib import Path
import traci

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "controller"))

import config
import sumolib
import junction_detector
import astar_router
import route_evaluator
from controller.hospital_manager import HospitalManager
from controller.traffic_aware_controller import TrafficAwareController
from visualization.unity_bridge import generate_round_traffic, cleanup_simulation_traffic

SUMO_CONFIG = PROJECT_ROOT / "simulation" / "mangaluru" / "presentation_demo.sumocfg"
MANGALURU_NET = PROJECT_ROOT / "simulation" / "mangaluru" / "presentation_selection2.net.xml"

# Sync networks
astar_router.NETWORK_FILE = MANGALURU_NET
route_evaluator.NETWORK_FILE = MANGALURU_NET
junction_detector.NETWORK_FILE = MANGALURU_NET
route_evaluator._SUMO_NETWORK = None
astar_router._SUMO_NETWORK = None
junction_detector.SUMO_NETWORK = sumolib.net.readNet(str(MANGALURU_NET))

hm = HospitalManager(str(config.NET_FILE), str(config.HOSPITALS_FILE))
kmc = hm.get_hospital("kmc_hospital")
print(f"KMC Hospital destination edge: {kmc.nearest_edge if kmc else 'None'}")

def run_pilot(mode: str, scenario: str = "medium", seed: int = 42):
    print(f"\n==========================================")
    print(f"PILOT: Mode={mode}, Scenario={scenario}, Seed={seed}")
    print(f"==========================================")
    
    traci.start([
        "sumo",
        "-c", str(SUMO_CONFIG),
        "--step-length", "0.1",
        "--seed", str(seed),
        "--ignore-route-errors",
        "--start"
    ])
    
    ai_controller = TrafficAwareController() if mode == "proposed" else None
    
    # Generate background traffic
    scheduled_ids = generate_round_traffic(round_id=1, current_time=0.0, scenario=scenario, seed=seed)
    
    start_edge = "1096889856"
    dest_edge = kmc.nearest_edge
    
    # Initial route: find candidate 0 from A*
    router = astar_router.AStarRouter()
    candidates = router.find_alternative_routes(start_edge, dest_edge)
    initial_route_edges = candidates[0].edge_ids
    
    route_id = f"pilot_route_{mode}"
    traci.route.add(route_id, initial_route_edges)
    traci.vehicle.add(vehID="ambulance", routeID=route_id, typeID="ambulance", depart="now", departLane="best")
    
    if mode == "proposed":
        traci.vehicle.setParameter("ambulance", "emergency", "true")
    else:
        traci.vehicle.setParameter("ambulance", "emergency", "false")
        
    dep_time = None
    arr_time = None
    accum_waiting = 0.0
    preempt_count = 0
    preempted_tls = set()
    initial_assigned_route = list(initial_route_edges)
    reroutes = 0
    
    step = 0
    max_steps = 4000  # 400 seconds limit
    ambulance_entered = False
    
    while step < max_steps:
        traci.simulationStep()
        step += 1
        sim_time = traci.simulation.getTime()
        active_vehs = traci.vehicle.getIDList()
        
        if "ambulance" in active_vehs:
            if not ambulance_entered:
                ambulance_entered = True
                dep_time = sim_time
                print(f"[{mode}] Ambulance departed at {dep_time:.1f}s")
                if mode == "proposed":
                    ai_controller.set_hospital_destination("kmc_hospital")
                    
            accum_waiting = traci.vehicle.getAccumulatedWaitingTime("ambulance")
            
            if mode == "proposed":
                # Check for reroute
                curr_route = list(traci.vehicle.getRoute("ambulance"))
                if curr_route != initial_assigned_route:
                    print(f"[{mode}] Route changed at {sim_time:.1f}s!")
                    reroutes += 1
                    initial_assigned_route = curr_route
                    
                decisions = ai_controller.process_step()
                for feat, dec in decisions:
                    if dec.should_preempt:
                        if feat.junction_id not in preempted_tls:
                            preempted_tls.add(feat.junction_id)
                            preempt_count += 1
                            print(f"[{mode}] Preemption at {feat.junction_id} (count={preempt_count})")
        else:
            if ambulance_entered and arr_time is None:
                arr_time = sim_time
                print(f"[{mode}] Ambulance arrived at {arr_time:.1f}s")
                break
                
    if ai_controller:
        ai_controller.shutdown()
        
    traci.close()
    
    if dep_time is not None and arr_time is not None:
        tt = arr_time - dep_time
        completed = True
    else:
        tt = None
        completed = False
        
    print(f"Result: Completed={completed}, Travel Time={tt:.1f}s if completed else N/A, Waiting={accum_waiting:.1f}s, Preemptions={preempt_count}, Reroutes={reroutes}")
    return {
        "mode": mode,
        "completed": completed,
        "dep_time": dep_time,
        "arr_time": arr_time,
        "travel_time": tt,
        "accum_waiting": accum_waiting,
        "preempt_count": preempt_count,
        "reroutes": reroutes
    }

if __name__ == "__main__":
    r_base = run_pilot("baseline", scenario="medium", seed=42)
    r_prop = run_pilot("proposed", scenario="medium", seed=42)
    print("\nPILOT COMPARISON:")
    print(f"Baseline travel time: {r_base['travel_time']:.1f}s")
    print(f"Proposed travel time: {r_prop['travel_time']:.1f}s")
    imp = ((r_base['travel_time'] - r_prop['travel_time']) / r_base['travel_time']) * 100.0
    print(f"Improvement: {imp:.2f}%")
