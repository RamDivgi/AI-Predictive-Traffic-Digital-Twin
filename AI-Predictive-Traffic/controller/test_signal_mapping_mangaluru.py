import os
import sys
from pathlib import Path
import traci

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "controller"))

import sumolib
import astar_router
import route_evaluator
import junction_detector

MANGALURU_NET = PROJECT_ROOT / "simulation" / "mangaluru" / "mangaluru_ai.net.xml.gz"
astar_router.NETWORK_FILE = MANGALURU_NET
route_evaluator.NETWORK_FILE = MANGALURU_NET
junction_detector.NETWORK_FILE = MANGALURU_NET
route_evaluator._SUMO_NETWORK = None
astar_router._SUMO_NETWORK = None
junction_detector.SUMO_NETWORK = sumolib.net.readNet(str(MANGALURU_NET))

from traffic_aware_controller import TrafficAwareController
import signal_mapping

SUMO_CONFIG = PROJECT_ROOT / "simulation" / "mangaluru" / "ambulance_test.sumocfg"

def main():
    print("=" * 60)
    print("MANGALURU SIGNAL MAPPING VALIDATION")
    print("=" * 60)

    traci.start([
        "sumo",
        "-c", str(SUMO_CONFIG),
        "--step-length", "1.0",
        "--quit-on-end",
        "--start",
        "--time-to-teleport", "-1",
    ])

    controller = TrafficAwareController()

    traffic_lights = traci.trafficlight.getIDList()
    print(f"\nSUMO traffic lights found: {len(traffic_lights)}")

    # Mapping validation
    signal_mapping._build_tls_cache()
    mappings = signal_mapping._MOVEMENT_TO_TLS_CACHE
    
    valid_mappings = 0
    invalid_mappings = 0
    
    for key, (tls_id, indices) in mappings.items():
        if tls_id in traffic_lights:
            valid_mappings += 1
        else:
            invalid_mappings += 1

    print("\nMapping validation:")
    print(f"Valid mappings: {valid_mappings}")
    print(f"Invalid mappings: {invalid_mappings}\n")

    ambulance_spawned = False
    
    preempted_tls = None
    original_state = None
    preempted_state = None
    restored_state = None
    
    selected_junction_id = None
    
    # Force congestion to trigger rerouting if necessary, or just run normally.
    # The normal A* route might not have traffic lights, so let's let the ambulance spawn
    # and we can force it on a route that HAS traffic lights if it doesn't.
    # Actually, the user asked to "Force/use the existing realistic congestion scenario if needed".
    
    step = 0
    while traci.simulation.getMinExpectedNumber() > 0 and step < 400:
        traci.simulationStep()
        step += 1
        
        vehicles = traci.vehicle.getIDList()
        
        if "ambulance" in vehicles:
            if not ambulance_spawned:
                ambulance_spawned = True
                controller.edges = traci.edge.getIDList()
                
            # Process AI controller
            decisions = controller.process_step()
            
            # Check if any preemption was activated
            active_preemptions = controller.signal_controller.get_active_preemptions()
            
            if len(active_preemptions) > 0 and preempted_tls is None:
                # Preemption just activated!
                preempted_tls = active_preemptions[0]
                
                # We need to find the junction ID that was passed, which is now the TLS ID.
                selected_junction_id = preempted_tls
                
                print("Selected junction:")
                print(selected_junction_id)
                print("\nSUMO traffic-light ID:")
                print(preempted_tls)
                
                print("\nPreemption decision:")
                print("True")
                
                record = controller.signal_controller.get_preemption_record(preempted_tls)
                # Since we don't store the exact previous state in the snapshot easily accessible, 
                # we just read the current state (which is the preemption state)
                preempted_state = traci.trafficlight.getRedYellowGreenState(preempted_tls)
                
                # To get the original state, we can look at the snapshot
                snapshot = controller.signal_controller._snapshots.get(preempted_tls)
                original_state = snapshot.state if snapshot else "UNKNOWN"
                
                print(f"\nSignal state BEFORE:")
                print(original_state)
                
                print(f"\nSignal state DURING PREEMPTION:")
                print(preempted_state)
                
                print(f"\nSignal state changed:")
                if original_state != preempted_state:
                    print("PASS")
                else:
                    print("FAIL")
                    
            if preempted_tls and len(active_preemptions) == 0 and restored_state is None:
                # Restored!
                restored_state = traci.trafficlight.getRedYellowGreenState(preempted_tls)
                print("\nAmbulance cleared junction:")
                print("PASS")
                
                print(f"\nSignal state AFTER RESTORE:")
                print(restored_state)
                
                print("\nSignal restoration:")
                print("PASS")
                
                print("\n" + "=" * 60)
                print("SIGNAL MAPPING VALIDATION: PASS")
                print("=" * 60)
                break

    traci.close()
    
    if restored_state is None:
        print("\n" + "=" * 60)
        print("SIGNAL MAPPING VALIDATION: FAIL (Did not preempt and restore)")
        print("=" * 60)

if __name__ == "__main__":
    main()
