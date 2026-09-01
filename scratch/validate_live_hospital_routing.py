import os
import sys
import time
import json
import traci

os.chdir(r'd:\AIML\Projects\Major\AI-Predictive-Traffic')
sys.path.append('controller')
sys.path.append('api')
sys.path.append('visualization')

import config
from hospital_manager import HospitalManager
from traffic_aware_controller import TrafficAwareController
from state_provider import StateProvider
SUMO_CONFIG = "simulation/mangaluru/presentation_demo.sumocfg"

def test_hospital_routing(hospital_id, expected_name, hm):
    print("=" * 80)
    print(f"TESTING LIVE ROUTING FOR: {expected_name} ({hospital_id})")
    print("=" * 80)
    
    # 1. Start simulation without GUI for fast testing
    traci.start([
        "sumo",
        "-c", str(SUMO_CONFIG),
        "--step-length", "0.1",
        "--random",
        "--ignore-route-errors",
        "--quit-on-end"
    ])
    
    try:
        # Simulate the dashboard writing the trip command
        trip_cmd = {
            "action": "start",
            "hospital_id": hospital_id,
            "emergency": True
        }
        
        # Instantiate controller like unity_bridge does
        ai_controller = TrafficAwareController()
        
        # 2. Emulate unity_bridge loop
        ambulance_spawned = False
        ambulance_route_locked = False
        step = 0
        
        expected_edge = hm.get_hospital(hospital_id).nearest_edge if hm.get_hospital(hospital_id) else "UNKNOWN"
        print(f"Expected final edge for {hospital_id} is: {expected_edge}")
        
        while step < 1000:  # Run for 100 simulation seconds max
            traci.simulationStep()
            step += 1
            
            # Simulate unity_bridge polling StateProvider
            if not ambulance_spawned and step == 10:
                print("[TRIP COMMAND]")
                print(f"hospital_id={hospital_id}")
                print(f"hospital_name={expected_name}")
                
                hosp = hm.get_hospital(hospital_id)
                print("\n[HOSPITAL RESOLUTION]")
                print(f"resolved hospital ID={hosp.id if hosp else 'None'}")
                print(f"resolved hospital name={hosp.name if hosp else 'None'}")
                dest_edge = hosp.nearest_edge if hosp else "1189020226#3"
                print(f"nearest SUMO edge={dest_edge}")
                
                start_edge = "1096889856"
                traci.route.add("dynamic_amb_route", [start_edge, dest_edge])
                traci.vehicle.add(vehID="ambulance", routeID="dynamic_amb_route", typeID="ambulance", depart="now", departLane="best")
                traci.vehicle.rerouteTraveltime("ambulance", True)
                ambulance_spawned = True
                print(f"\n[SPAWN] Ambulance spawned dynamically via unity_bridge logic.")
                
            if ambulance_spawned:
                current_vehicles = traci.vehicle.getIDList()
                if "ambulance" in current_vehicles:
                    if not ambulance_route_locked:
                        # Emulate receiving set_hospital from Dashboard via UDP
                        ai_controller.set_hospital_destination(hospital_id)
                        ambulance_route_locked = True
                        
                        actual_route = traci.vehicle.getRoute("ambulance")
                        actual_route_id = traci.vehicle.getRouteID("ambulance")
                        print("\n[TRACI ROUTE AFTER LOCK]")
                        print(f"route ID created={actual_route_id}")
                        print(f"route final edge={actual_route[-1]}")
                    
                    # Run AI step
                    ai_controller.process_step()
                    
                    # Check if reached destination
                    road_id = traci.vehicle.getRoadID("ambulance")
                    if road_id == expected_edge:
                        print("\n[SUCCESS] Ambulance physically reached destination edge!")
                        print(f"simulation time={traci.simulation.getTime()}")
                        print(f"ambulance road ID={road_id}")
                        print(f"ambulance lane={traci.vehicle.getLaneID('ambulance')}")
                        print(f"ambulance position={traci.vehicle.getLanePosition('ambulance')}")
                        print(f"destination edge={expected_edge}")
                        return "PASS", expected_edge, road_id
                else:
                    if ambulance_route_locked:
                        # Ambulance was removed (arrived)
                        print(f"Ambulance arrived at destination.")
                        return "PASS", expected_edge, "ARRIVED"

        print("TIMEOUT: Ambulance did not reach destination in 100 seconds.")
        if "ambulance" in traci.vehicle.getIDList():
            actual_route = traci.vehicle.getRoute("ambulance")
            print(f"Current road: {traci.vehicle.getRoadID('ambulance')}")
            print(f"Final route edge: {actual_route[-1]}")
            return "FAIL", expected_edge, actual_route[-1]
        else:
            return "FAIL", expected_edge, "DISAPPEARED"
            
    finally:
        traci.close()

if __name__ == '__main__':
    hm = HospitalManager(str(config.NET_FILE), str(config.HOSPITALS_FILE))
    
    hospitals_to_test = [
        ("highland_hospital", "Highland Hospital"),
        ("kmc_hospital", "KMC Hospital"),
        ("father_muller_hospital", "Father Muller Hospital"),
        ("unity_hospital", "Unity Hospital"),
        ("indira_hospital", "Indira Hospital"),
        ("athena_hospital", "Athena Hospital")
    ]
    
    results = []
    
    for hid, hname in hospitals_to_test:
        status, exp, act = test_hospital_routing(hid, hname, hm)
        results.append((hname, exp, act, status))
        
    print("\n" + "=" * 80)
    print("LIVE ROUTING VALIDATION SUMMARY")
    print("=" * 80)
    print(f"{'Hospital':<25} | {'Expected Final Edge':<20} | {'Actual TraCI Final Edge':<20} | {'Status'}")
    print("-" * 80)
    for hname, exp, act, status in results:
        print(f"{hname:<25} | {exp:<20} | {act:<20} | {status}")
