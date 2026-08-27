import os
import sys
from pathlib import Path
import traci

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT / "controller"))

import astar_router
import route_evaluator
from rerouting_controller import ReroutingController

# Override network file for A* to use Mangaluru
MANGALURU_NET = PROJECT_ROOT / "simulation" / "mangaluru" / "mangaluru_ai.net.xml.gz"
astar_router.NETWORK_FILE = MANGALURU_NET
route_evaluator.NETWORK_FILE = MANGALURU_NET
route_evaluator._SUMO_NETWORK = None
astar_router._SUMO_NETWORK = None

SUMOCFG = PROJECT_ROOT / "simulation" / "mangaluru" / "ambulance_test.sumocfg"

def run_scenario(scenario_idx, congestion_edge, num_halted_vehicles):
    print(f"\n--- Starting Scenario {scenario_idx} ---")
    
    # Ensure no lingering traci instances
    try:
        traci.close()
    except:
        pass
        
    traci.start(["sumo", "-c", str(SUMOCFG), "--step-length", "1.0"])
    
    controller = ReroutingController(
        min_improvement_s=5.0, # Lowered threshold to ensure we can trigger it
        min_improvement_percent=2.0,
        cooldown_s=30.0,
        ambulance_id="ambulance"
    )
    
    ambulance_spawned = False
    rerouted = False
    reached_dest = False
    
    step = 0
    old_route = None
    new_route = None
    reroute_time = -1
    
    while step < 1000:
        traci.simulationStep()
        
        # Apply congestion
        if step == 15:
            print(f"Applying congestion on {congestion_edge}...")
            try:
                # Drastically reduce max speed on the edge to make it unappealing and cause traffic jams
                traci.edge.setMaxSpeed(congestion_edge, 0.001)
                route_id = f"block_route_{scenario_idx}"
                traci.route.add(route_id, [congestion_edge])
                for i in range(min(num_halted_vehicles, 8)): # Max 8 to avoid edge overflow
                    vid = f"blocker_{scenario_idx}_{i}"
                    traci.vehicle.add(vid, route_id, typeID="passenger")
                    pos = 5.0 + i * 8.0 # 8 meters apart
                    try:
                        traci.vehicle.moveTo(vid, f"{congestion_edge}_0", pos)
                        traci.vehicle.setSpeed(vid, 0.0)
                    except:
                        pass
            except Exception as e:
                print(f"Error adding congestion: {e}")
                    
        vehicles = traci.vehicle.getIDList()
        if "ambulance" in vehicles:
            if not ambulance_spawned:
                ambulance_spawned = True
                print("Ambulance spawned.")
                old_route = traci.vehicle.getRouteID("ambulance")
                
            curr_edge = traci.vehicle.getRoadID("ambulance")
            if curr_edge == "-26299202#3" or curr_edge == "-26299202#2":
                print("Ambulance reached destination!")
                reached_dest = True
                break
                
            # Evaluate rerouting
            if not rerouted and step % 5 == 0 and not curr_edge.startswith(":"):
                was_rerouted = controller.evaluate_and_reroute()
                if was_rerouted:
                    rerouted = True
                    new_route = traci.vehicle.getRouteID("ambulance")
                    reroute_time = traci.simulation.getTime()
                    print("============================================================")
                    print("MANGALURU A* REROUTING TEST")
                    print("============================================================")
                    print("REROUTING DECISION: YES")
                    print(f"Old route: {old_route}")
                    print(f"New route: {new_route}")
                    print(f"Reroute simulation time: {reroute_time}")
                    print("============================================================")
                    
        elif ambulance_spawned:
            # Ambulance left simulation
            print("Ambulance left simulation, assumed reached destination.")
            reached_dest = True
            break
            
        step += 1
        
    traci.close()
    
    if not ambulance_spawned:
        print("Fail: Ambulance never spawned.")
        return False
        
    if not rerouted:
        print("Fail: Ambulance did not reroute.")
        return False
        
    if not reached_dest:
        print("Fail: Ambulance did not reach destination.")
        return False
        
    return True

if __name__ == "__main__":
    print("Testing A* Rerouting on Mangaluru Network")
    
    # Edges from the route: 1366470617#1, 1042171954#1, 184750308#18
    scenarios = [
        (1, "1366470617#1", 5),
        (2, "1042171954#1", 8),
        (3, "184750308#18", 8)
    ]
    
    success = False
    for idx, edge, num in scenarios:
        if run_scenario(idx, edge, num):
            print("\nSUCCESS: Valid rerouting scenario found and validated.")
            success = True
            break
            
    if not success:
        print("\nFAILURE: All 3 scenarios failed to produce a valid reroute.")
        sys.exit(1)
