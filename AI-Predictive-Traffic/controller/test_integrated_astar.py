import os
import sys
from pathlib import Path
import traci

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT / "controller"))

from rerouting_controller import ReroutingController
from traffic_aware_controller import TrafficAwareController

def run_test():
    sumo_cmd = [
        "sumo",
        "-c", str(PROJECT_ROOT / "simulation" / "config" / "test.sumocfg"),
        "--no-warnings"
    ]
    traci.start(sumo_cmd)

    rerouting_controller = ReroutingController(
        min_improvement_s=2.0,
        min_improvement_percent=2.0,
        cooldown_s=10.0,
        min_distance_to_dest_m=20.0,
        ambulance_id="ambulance"
    )
    
    traffic_controller = TrafficAwareController()

    initial_route = None
    final_route = None
    ambulance_start_time = None
    ambulance_completion_time = None
    reroute_count = 0
    preemption_occurred = False
    
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
                
                final_route = traci.vehicle.getRouteID("ambulance")
                
                # Run Rerouting every 5 steps
                if step % 5 == 0:
                    current_edge = traci.vehicle.getRoadID("ambulance")
                    if not current_edge.startswith(":"):
                        route_before = traci.vehicle.getRouteID("ambulance")
                        
                        did_reroute = rerouting_controller.evaluate_and_reroute(ml_etas={})
                        
                        route_after = traci.vehicle.getRouteID("ambulance")
                        if did_reroute and route_before != route_after:
                            reroute_count += 1
                            print("--> TraCI route change verified.")
                
                # Run Preemption logic on every step
                traffic_controller.process_step()
                if traffic_controller.active_movements:
                    preemption_occurred = True
                    
            else:
                if ambulance_start_time is not None and ambulance_completion_time is None:
                    ambulance_completion_time = current_time
                    break
                    
            step += 1
            
    except traci.TraCIException as e:
        print(f"TraCI Exception occurred: {e}")
    finally:
        try:
            traci.close()
        except Exception:
            pass
        
    print("\n========================================")
    print("INTEGRATED A* + PREEMPTION TEST RESULT")
    print("========================================")
    print(f"Initial route: {initial_route}")
    print(f"Final route: {final_route}")
    print(f"Reroute count: {reroute_count}")
    print(f"Preemption occurred: {preemption_occurred}")
    
    travel_time = "N/A"
    if ambulance_start_time is not None and ambulance_completion_time is None:
        travel_time = f"> {max_steps - ambulance_start_time:.1f} s (did not finish)"
    elif ambulance_start_time is not None:
        travel_time = f"{ambulance_completion_time - ambulance_start_time:.1f} s"
        
    print(f"Ambulance travel time: {travel_time}")

if __name__ == "__main__":
    run_test()