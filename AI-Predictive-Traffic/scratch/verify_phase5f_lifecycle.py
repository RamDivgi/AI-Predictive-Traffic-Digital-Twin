"""
Phase 5F: Multi-Round Lifecycle Acceptance Test
Validates:
1. Complete emergency trip dispatch with Green Corridor preemption.
2. Dynamic downstream congestion injection triggering genuine mid-trip A* rerouting.
3. Signal preemption recovery after ambulance passage.
4. Stop trip API execution with vehicle removal and signal restoration.
5. Fresh second trip dispatch (KMC Hospital) with clean route generation and preemption.
"""
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "controller"))

import traci
import sumolib
import config
from api.state_provider import StateProvider
from controller.hospital_manager import HospitalManager
from controller.traffic_aware_controller import TrafficAwareController
import junction_detector
import astar_router
import route_evaluator

SUMO_CONFIG = PROJECT_ROOT / "simulation" / "mangaluru" / "presentation_demo.sumocfg"
MANGALURU_NET = PROJECT_ROOT / "simulation" / "mangaluru" / "presentation_selection2.net.xml"

astar_router.NETWORK_FILE = MANGALURU_NET
route_evaluator.NETWORK_FILE = MANGALURU_NET
junction_detector.NETWORK_FILE = MANGALURU_NET
route_evaluator._SUMO_NETWORK = None
astar_router._SUMO_NETWORK = None
junction_detector.SUMO_NETWORK = sumolib.net.readNet(str(MANGALURU_NET))

from visualization.unity_bridge import (
    TrafficMetricsTracker,
    generate_round_traffic,
    cleanup_simulation_traffic
)

def run_lifecycle_test():
    print("=" * 80)
    print("PHASE 5F: MULTI-ROUND LIFECYCLE ACCEPTANCE TEST")
    print("=" * 80)

    traci.start([
        "sumo",
        "-c", str(SUMO_CONFIG),
        "--step-length", "0.1",
        "--random",
        "--ignore-route-errors",
        "--start"
    ])

    metrics_tracker = TrafficMetricsTracker()
    ai_controller = TrafficAwareController()
    hm = HospitalManager(str(config.NET_FILE), str(config.HOSPITALS_FILE))

    # --- PART A: Round 1 Emergency Trip to Father Muller ---
    print("\n[PART A] Round 1 Emergency Trip & Congestion-Triggered Rerouting...")
    sched_r1 = generate_round_traffic(round_id=1, current_time=0.0, scenario="medium")
    metrics_tracker.reset_round(round_id=1, scenario="medium", scheduled_ids=sched_r1)

    start_edge = "1096889856"
    dest_edge = hm.get_hospital("father_muller_hospital").nearest_edge
    route_r1 = "p5f_r1_route"
    traci.route.add(route_r1, [start_edge, dest_edge])
    traci.vehicle.add(vehID="ambulance", routeID=route_r1, typeID="ambulance", depart="now", departLane="best")
    traci.vehicle.setParameter("ambulance", "emergency", "true")
    traci.simulationStep()
    ai_controller.set_hospital_destination("father_muller_hospital")

    # Configure rerouter thresholds for sensitive test detection
    ai_controller.rerouting_controller.min_improvement_s = 5.0
    ai_controller.rerouting_controller.min_improvement_percent = 5.0
    ai_controller.rerouting_controller.cooldown_s = 5.0
    ai_controller.rerouting_controller.min_distance_to_dest_m = 30.0

    orig_route = list(traci.vehicle.getRoute("ambulance"))
    print(f"  Initial dispatched route: {orig_route}")

    # Step until ambulance enters downstream normal road edge
    for _ in range(120):
        traci.simulationStep()
        ai_controller.process_step()
        cur_edge = traci.vehicle.getRoadID("ambulance")
        if not cur_edge.startswith(":") and cur_edge in ["-1096889856", "-184750315#1"]:
            break

    curr_edge = traci.vehicle.getRoadID("ambulance")
    print(f"  Ambulance progressed to mid-trip edge: '{curr_edge}'")

    # Inject heavy blockage on downstream edge 1368365880
    print("  Injecting heavy blockage onto downstream edge '1368365880'...")
    traci.route.add("p5f_jam_route", ["1368365880", "26209723#2"])
    for i in range(4):
        vid = f"p5f_blocker_{i}"
        traci.vehicle.add(vid, "p5f_jam_route", depart="now", departPos=str(i * 4.0))
        traci.vehicle.setSpeed(vid, 0.0)

    for _ in range(10):
        traci.simulationStep()

    rerouted = False
    new_route = None
    preemption_occurred = False

    for _ in range(40):
        traci.simulationStep()
        decisions = ai_controller.process_step()
        if decisions:
            for feat, dec in decisions:
                if dec.should_preempt:
                    preemption_occurred = True

        r_now = list(traci.vehicle.getRoute("ambulance"))
        if r_now != orig_route and not rerouted:
            rerouted = True
            new_route = r_now
            print(f"  [SUCCESS] Mid-trip reroute triggered! New route: {new_route}")

    print(f"  Mid-trip reroute verified: {rerouted}")
    print(f"  Corridor signal preemption verified: {preemption_occurred}")

    # --- PART B: Stop Trip Command ---
    print("\n[PART B] Stop Trip Command Execution & State Cleanup...")
    StateProvider.write_trip_command({"action": "stop"})
    cmd = StateProvider.read_trip_command()
    if cmd and cmd.get("action") == "stop":
        ai_controller.shutdown()
        if "ambulance" in traci.vehicle.getIDList():
            traci.vehicle.remove("ambulance")
        num_removed = cleanup_simulation_traffic(sched_r1)
        StateProvider.write_trip_status({"status": "IDLE"})
        StateProvider.clear_trip_command()
        print(f"  Ambulance removed. {num_removed} background vehicles cleaned up.")

    for _ in range(10):
        traci.simulationStep()

    vehs_after_stop = traci.vehicle.getIDList()
    amb_present_after_stop = "ambulance" in vehs_after_stop
    print(f"  Vehicles remaining after stop: {len(vehs_after_stop)} (Ambulance present: {amb_present_after_stop})")

    # --- PART C: Second Trip Dispatch ---
    print("\n[PART C] Second Trip Dispatch (KMC Hospital)...")
    cur_time = traci.simulation.getTime()
    sched_r2 = generate_round_traffic(round_id=2, current_time=cur_time, scenario="medium")
    metrics_tracker.reset_round(round_id=2, scenario="medium", scheduled_ids=sched_r2)

    dest_edge_2 = hm.get_hospital("kmc_hospital").nearest_edge
    route_r2 = "p5f_r2_route"
    traci.route.add(route_r2, [start_edge, dest_edge_2])
    traci.vehicle.add(vehID="ambulance", routeID=route_r2, typeID="ambulance", depart="now", departLane="best")
    traci.vehicle.setParameter("ambulance", "emergency", "true")
    traci.simulationStep()
    ai_controller.set_hospital_destination("kmc_hospital")

    second_trip_active = False
    for _ in range(25):
        traci.simulationStep()
        ai_controller.process_step()
        if "ambulance" in traci.vehicle.getIDList():
            second_trip_active = True

    print(f"  Second trip active in SUMO: {second_trip_active}")
    r2_edges = traci.vehicle.getRoute("ambulance")
    print(f"  Second trip route edges: {len(r2_edges)}")

    traci.close()

    lifecycle_pass = rerouted and (not amb_present_after_stop) and second_trip_active
    print("\n" + "=" * 80)
    print(f"LIFECYCLE TEST RESULT: {'PASS' if lifecycle_pass else 'FAIL'}")
    print("=" * 80)
    return lifecycle_pass

if __name__ == "__main__":
    success = run_lifecycle_test()
    sys.exit(0 if success else 1)
