import os
import sys
from pathlib import Path
import traci

# Ensure controller module path is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT / "controller"))

from rerouting_controller import ReroutingController

def run_test():
    sumo_cmd = [
        "sumo",
        "-c", str(PROJECT_ROOT / "simulation" / "config" / "test.sumocfg"),
        "--no-warnings"
    ]
    traci.start(sumo_cmd)

    # Use more aggressive thresholds to encourage rerouting in test
    controller = ReroutingController(
        min_improvement_s=2.0,
        min_improvement_percent=2.0,
        cooldown_s=10.0,
        min_distance_to_dest_m=20.0,
        ambulance_id="ambulance"
    )

    initial_route = None
    final_route = None
    ambulance_start_time = None
    ambulance_completion_time = None
    reroute_count = 0
    failed_reroute = False
    
    max_steps = 180
    step = 0
    
    try:
        while step < max_steps:
            traci.simulationStep()
            current_time = traci.simulation.getTime()
            
            vehicles = traci.vehicle.getIDList()
            if "ambulance" in vehicles:
                if ambulance_start_time is None:
                    ambulance_start_time = current_time
                    initial_route = traci.vehicle.getRouteID("ambulance")
                
                # Update final route dynamically
                final_route = traci.vehicle.getRouteID("ambulance")
                
                # Check at intervals (every 5 steps = 5 seconds if step length is 1s)
                if step % 5 == 0:
                    current_edge = traci.vehicle.getRoadID("ambulance")
                    if not current_edge.startswith(":"):
                        print("\n========================================")
                        print("DYNAMIC REROUTING TEST")
                        print("========================================")
                        print(f"Current edge: {current_edge}")
                        
                        route_before = traci.vehicle.getRouteID("ambulance")
                        
                        # Evaluate and potentially reroute
                        did_reroute = controller.evaluate_and_reroute(ml_etas={})
                        
                        route_after = traci.vehicle.getRouteID("ambulance")
                        
                        if did_reroute:
                            if route_before != route_after:
                                reroute_count += 1
                                print("--> TraCI route change verified.")
                            else:
                                print("--> ERROR: Controller returned True, but TraCI route did NOT change!")
                                failed_reroute = True
            else:
                if ambulance_start_time is not None and ambulance_completion_time is None:
                    ambulance_completion_time = current_time
                    break
                    
            step += 1
            
    finally:
        traci.close()
        
    print("\n========================================")
    print("REROUTING TEST RESULT")
    print("========================================")
    print(f"Initial route: {initial_route}")
    print(f"Final route: {final_route}")
    print(f"Reroute count: {reroute_count}")
    
    if ambulance_start_time is not None:
        if ambulance_completion_time is not None:
            travel_time = f"{ambulance_completion_time - ambulance_start_time:.1f} s"
        else:
            travel_time = f"> {max_steps - ambulance_start_time:.1f} s (did not finish)"
    else:
        travel_time = "N/A"
            
    print(f"Ambulance travel time: {travel_time}")
    
    if failed_reroute:
        print("\nFAIL")
        print("REROUTING_INTEGRATION_FAILED")
    elif reroute_count > 0:
        print("\nPASS")
        print("REROUTING_INTEGRATION_TEST_VALID")
    else:
        print("\nNO_REROUTE")
        print("REROUTING_LOGIC_VALID_BUT_SCENARIO_NOT_TRIGGERING")

if __name__ == "__main__":
    run_test()
