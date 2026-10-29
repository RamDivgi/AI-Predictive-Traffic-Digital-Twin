import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "controller"))

import traci
from controller.traffic_aware_controller import TrafficAwareController
from controller.hospital_manager import HospitalManager
from visualization.unity_bridge import generate_dynamic_traffic, generate_round_traffic, cleanup_simulation_traffic
import config

CFG_FILE = str(PROJECT_ROOT / "simulation" / "mangaluru" / "presentation_demo.sumocfg")

def test_normal_priority_ambulance_with_traffic():
    print("=" * 70)
    print("VALIDATION: NORMAL-PRIORITY AMBULANCE WITH HEAVY CORRIDOR TRAFFIC")
    print("=" * 70)
    
    generate_dynamic_traffic()
    
    traci.start([
        "sumo",
        "-c", CFG_FILE,
        "--step-length", "0.1",
        "--random",
        "--ignore-route-errors",
        "--quit-on-end",
        "--start"
    ])
    
    try:
        hm = HospitalManager(str(config.NET_FILE), str(config.HOSPITALS_FILE))
        ai_controller = TrafficAwareController()
        
        cur_t = traci.simulation.getTime()
        round_id = 1
        scheduled = generate_round_traffic(round_id=round_id, current_time=cur_t, scenario="medium")
        
        corridor_jam_ids = [vid for vid in scheduled if "_jam_" in vid]
        print(f"\n[STEP 1] Scheduled {len(corridor_jam_ids)} civilian corridor vehicles ahead of ambulance:")
        for vid in corridor_jam_ids:
            print(f"   -> {vid}")
        assert len(corridor_jam_ids) == 10, f"Expected 10 corridor vehicles, got {len(corridor_jam_ids)}"
        
        # Spawn ambulance with NORMAL priority (emergency=False)
        start_edge = "1096889856"
        dest_hosp = hm.get_hospital("kmc_hospital")
        dest_edge = dest_hosp.nearest_edge
        
        traci.route.add("test_amb_route", [start_edge, dest_edge])
        traci.vehicle.add(vehID="ambulance", routeID="test_amb_route", typeID="ambulance", depart="now", departLane="best")
        traci.vehicle.setParameter("ambulance", "emergency", "false")
        
        # Step once to materialize ambulance in SUMO
        traci.simulationStep()
        
        # Lock A* route
        init_ok = ai_controller.set_hospital_destination("kmc_hospital")
        assert init_ok, "A* route initialization failed!"
        assigned_route = traci.vehicle.getRoute("ambulance")
        print(f"\n[STEP 2] Ambulance spawned and route assigned: {len(assigned_route)} edges")
        print(f"   Destination: {dest_hosp.name} (edge {dest_edge})")
        print(f"   Emergency parameter: {traci.vehicle.getParameter('ambulance', 'emergency')} (NORMAL PRIORITY)")
        
        # Run simulation while tracking ambulance and civilian vehicles
        ambulance_active = True
        collisions = 0
        teleports = 0
        preemption_triggered = False
        corridor_vehicles_encountered = set()
        ambulance_wait_time = 0.0
        amb_speeds = []
        
        max_steps = 1200 # up to 120 simulation seconds
        for step_i in range(max_steps):
            traci.simulationStep()
            sim_time = traci.simulation.getTime()
            
            # Run AI controller step (which checks emergency status)
            decisions = ai_controller.process_step()
            for d in decisions:
                if "PREEMPT" in d.action:
                    preemption_triggered = True
            
            active_vehs = traci.vehicle.getIDList()
            if "ambulance" in active_vehs:
                amb_edge = traci.vehicle.getRoadID("ambulance")
                amb_spd = traci.vehicle.getSpeed("ambulance")
                amb_wait = traci.vehicle.getWaitingTime("ambulance")
                amb_speeds.append(amb_spd)
                if amb_wait > ambulance_wait_time:
                    ambulance_wait_time = amb_wait
                
                # Check civilian corridor vehicles ahead on the ambulance's route
                for jid in corridor_jam_ids:
                    if jid in active_vehs:
                        j_edge = traci.vehicle.getRoadID(jid)
                        if j_edge in assigned_route:
                            corridor_vehicles_encountered.add(jid)
            elif "ambulance" not in active_vehs and step_i > 10:
                print(f"\n[INFO] Ambulance reached destination at sim_time = {sim_time:.1f}s.")
                ambulance_active = False
                break
                
            coll = traci.simulation.getCollidingVehiclesNumber()
            if coll > 0:
                collisions += coll
            tel = traci.simulation.getStartingTeleportNumber()
            if tel > 0:
                teleports += tel
                
        print(f"\n[STEP 3] Traffic Interaction & Congestion Results:")
        print(f"   Corridor vehicles observed on ambulance route: {len(corridor_vehicles_encountered)} / 10")
        print(f"   Ambulance maximum waiting time in queue: {ambulance_wait_time:.1f}s")
        print(f"   Ambulance average speed: {sum(amb_speeds)/len(amb_speeds):.2f} m/s ({sum(amb_speeds)/len(amb_speeds)*3.6:.1f} km/h)")
        print(f"   Collisions detected: {collisions}")
        print(f"   Teleports detected: {teleports}")
        print(f"   Signal preemption triggered: {preemption_triggered}")
        
        assert collisions == 0, f"Collisions occurred: {collisions}"
        assert teleports == 0, f"Teleports occurred: {teleports}"
        assert not preemption_triggered, "Preemption was unexpectedly triggered in normal priority mode!"
        assert len(corridor_vehicles_encountered) >= 8, f"Too few corridor vehicles encountered: {len(corridor_vehicles_encountered)}"
        
        print("\n" + "=" * 70)
        print("ALL NORMAL-PRIORITY CORRIDOR DENSITY CHECKS PASSED SUCCESSFULLY!")
        print("=" * 70)
    finally:
        try:
            traci.close()
        except Exception:
            pass

if __name__ == "__main__":
    test_normal_priority_ambulance_with_traffic()
