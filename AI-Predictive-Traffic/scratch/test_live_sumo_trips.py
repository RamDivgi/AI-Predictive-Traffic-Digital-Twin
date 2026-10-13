import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "controller"))

import traci
import sumolib
import config
import astar_router
from hospital_manager import HospitalManager
from traffic_aware_controller import TrafficAwareController

SUMO_CONFIG = PROJECT_ROOT / "simulation" / "mangaluru" / "presentation_demo.sumocfg"

def run_trip_test(start_edge, dest_hospital_id, max_steps=1500):
    print(f"\n========================================================")
    print(f"RUNNING LIVE SUMO TRIP: Start={start_edge} -> Hospital={dest_hospital_id}")
    print(f"========================================================")
    
    # Start headless SUMO
    try:
        traci.close()
    except Exception:
        pass
        
    sumo_bin = sumolib.checkBinary("sumo")
    traci.start([
        sumo_bin,
        "-c", str(SUMO_CONFIG),
        "--step-length", "0.1",
        "--random",
        "--ignore-route-errors",
        "--start"
    ])
    
    hm = HospitalManager(str(config.NET_FILE), [str(config.SIMULATION_DIR / "hospitals.add.xml"), str(config.HOSPITALS_FILE)])
    hosp = hm.get_hospital(dest_hospital_id)
    dest_edge = hosp.nearest_edge
    
    print(f"Target Hospital: {hosp.name} (Dest Edge: {dest_edge})")
    
    # Initialize controller
    controller = TrafficAwareController()
    
    # 1. Spawn ambulance
    route_id = f"test_spawn_route_{int(time.time()*1000)%100000}"
    traci.route.add(route_id, [start_edge, dest_edge])
    traci.vehicle.add(vehID="ambulance", routeID=route_id, typeID="ambulance", depart="now", departLane="best")
    traci.vehicle.setParameter("ambulance", "emergency", "true")
    
    # Step 1: let ambulance materialize
    traci.simulationStep()
    
    # 2. Lock A* route
    ok = controller.set_hospital_destination(dest_hospital_id)
    if not ok:
        print("ERROR: set_hospital_destination failed!")
        traci.close()
        return False, "Failed to lock A* route"
        
    assigned_route = traci.vehicle.getRoute("ambulance")
    print(f"A* route locked: {len(assigned_route)} edges. Final edge: {assigned_route[-1]}")
    
    step = 0
    arrived = False
    preemptions_seen = set()
    restorations_seen = set()
    ml_etas_seen = []
    
    while step < max_steps:
        traci.simulationStep()
        step += 1
        
        vehs = traci.vehicle.getIDList()
        if "ambulance" in vehs:
            # Run controller step
            decisions = controller.process_step()
            for feat, dec in decisions:
                if feat.ambulance_eta_s is not None:
                    ml_etas_seen.append((feat.junction_id, round(feat.ambulance_eta_s, 2)))
                if dec.should_preempt:
                    preemptions_seen.add(feat.junction_id)
            
            # Check for restorations
            for tls_id in controller.active_movements:
                pass
        else:
            # Ambulance left network
            arrived = True
            break
            
    traci.close()
    
    print(f"Result: Arrived={arrived} in {step * 0.1:.1f}s simulation time")
    print(f"Preemptions triggered at junctions: {preemptions_seen}")
    print(f"ML ETAs computed: {len(ml_etas_seen)} instances")
    if ml_etas_seen:
        print(f"Sample ML ETAs: {ml_etas_seen[:5]}")
        
    return arrived, {
        "steps": step,
        "sim_time_s": step * 0.1,
        "arrived": arrived,
        "preemptions": list(preemptions_seen),
        "ml_etas_count": len(ml_etas_seen),
        "route_len": len(assigned_route)
    }

if __name__ == "__main__":
    results = {}
    
    # Test 1: Baseline Father Muller from default start (1096889856)
    ok, data = run_trip_test("1096889856", "father_muller_hospital")
    results["1096889856_father_muller"] = (ok, data)
    
    # Test 2: Start Point 1 (-26209727#1) to Father Muller
    ok, data = run_trip_test("-26209727#1", "father_muller_hospital")
    results["-26209727#1_father_muller"] = (ok, data)
    
    # Test 3: Start Point 2 (1213225868) to Father Muller
    ok, data = run_trip_test("1213225868", "father_muller_hospital")
    results["1213225868_father_muller"] = (ok, data)

    # Test 4: Start Point 3 (-1154699531) to Father Muller
    ok, data = run_trip_test("-1154699531", "father_muller_hospital")
    results["-1154699531_father_muller"] = (ok, data)

    # Test 5: Known 3-TLS route from -1047086882 to KMC Hospital
    ok, data = run_trip_test("-1047086882", "kmc_hospital")
    results["-1047086882_kmc_hospital"] = (ok, data)
    
    print("\n========================================================")
    print("ALL LIVE SIMULATION TESTS COMPLETED")
    print("========================================================")
    for k, v in results.items():
        status = "PASS" if v[0] else "FAIL"
        print(f"{k}: {status} => {v[1]}")
