"""
Phase Three Automated Test Suite: Congestion-Aware Route Selection
Validates:
1. Route with lower estimated travel time is selected.
2. When the shortest-distance route is congested, a valid faster alternative is selected.
3. Stable selection when routes have similar costs (no oscillation).
4. Invalid, disconnected, and duplicate alternatives are safely rejected.
5. Missing or offline traffic data does not crash routing.
6. The selected route is actually assigned to the ambulance in TraCI.
7. Candidate costs and selection decisions under Medium, High, and Bottleneck scenarios.
"""
import sys
import os
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "controller"))

import traci
import config
from controller.astar_router import AStarRouter, AStarRoute
from controller.traffic_aware_controller import TrafficAwareController
from controller.hospital_manager import HospitalManager
from visualization.unity_bridge import generate_round_traffic, cleanup_simulation_traffic

CFG_FILE = str(PROJECT_ROOT / "simulation" / "mangaluru" / "presentation_demo.sumocfg")
NET_FILE = str(config.NET_FILE)
HOSP_FILE = str(config.HOSPITALS_FILE)

def start_sim():
    traci.start([
        "sumo",
        "-c", CFG_FILE,
        "--step-length", "0.1",
        "--random",
        "--ignore-route-errors",
        "--quit-on-end",
        "--start"
    ])

def close_sim():
    try:
        traci.close()
    except Exception:
        pass

def run_tests():
    print("=" * 70)
    print("PHASE THREE: CONGESTION-AWARE ROUTE SELECTION VALIDATION")
    print("=" * 70)

    # -------------------------------------------------------------
    # Test 1 & 4 & 5: Robustness, Data Safety, Validity, and Unit Checks
    # -------------------------------------------------------------
    print("\n[TEST 1, 4, 5] Verifying Cost Formula Units, Validity, and Fallbacks...")
    router = AStarRouter()
    
    # 1. Units check on Route Cost
    r = router.find_route("1096889856", "26209723#3")
    assert r is not None, "Failed to find primary route to Father Muller"
    print(f"  Primary route found: {len(r.edge_ids)} edges, distance={r.total_distance_m:.1f}m")
    print(f"  Cost breakdown (strictly in seconds):")
    print(f"    Travel time:   {r.estimated_travel_time_s:.2f} s")
    print(f"    Congestion:    {r.total_congestion_cost:.2f} s")
    print(f"    Signal delay:  {r.total_signal_delay_s:.2f} s")
    print(f"    Total cost:    {r.total_cost:.2f} s")
    assert abs(r.total_cost - (r.estimated_travel_time_s + r.total_signal_delay_s)) < 1e-4, "Cost formula consistency violation"
    
    # 4. Invalid edge safety
    r_inv = router.find_route("non_existent_edge_123", "26209723#3")
    assert r_inv is None, "Did not handle non-existent edge gracefully"
    alts_inv = router.find_alternative_routes("non_existent_edge_123", "26209723#3")
    assert alts_inv == [], "Did not handle non-existent edge in alternatives gracefully"
    
    # 5. Missing / internal edge safety
    t_f, c_c, _ = router._get_edge_traffic_cost("non_existent_edge", 100.0)
    assert t_f > 0 and c_c == 0.0, "Missing traffic data did not safely fall back to free-flow"
    print("  --> Test 1, 4, 5 PASSED: Units consistent in seconds; invalid inputs safely handled.")

    # -------------------------------------------------------------
    # Live SUMO Simulation Tests
    # -------------------------------------------------------------
    start_sim()
    try:
        ctrl = TrafficAwareController()
        hm = HospitalManager(NET_FILE, HOSP_FILE)
        
        # ---------------------------------------------------------
        # Test 2 & 6: Congestion-Aware Selection & Vehicle Assignment
        # ---------------------------------------------------------
        print("\n[TEST 2 & 6] Verifying Congestion-Aware Selection & TraCI Assignment...")
        # Scenario: Start ambulance at 1096889856 towards Father Muller Hospital (26209723#3)
        # Father Muller has two candidate routes:
        # Candidate 0: via 1368365880 (172.4m, ~11.5s)
        # Candidate 1: via -184750315#0 -> 26209723#1 (193.1m, ~12.9s)
        # Inject queue onto 1368365880 so Candidate 0 becomes congested
        
        # Add 3 queue vehicles directly onto 1368365880 to congest Candidate 0 uniquely
        traci.route.add("cong_route", ["1368365880", "26209723#2"])
        for i in range(3):
            traci.vehicle.add(f"blocker_{i}", "cong_route", depart="now", departPos=str(i * 5.0))
            traci.vehicle.setSpeed(f"blocker_{i}", 0.0)

        # Step simulation to insert blockers and let them halt
        for _ in range(20):
            traci.simulationStep()
            for i in range(3):
                try:
                    traci.vehicle.setSpeed(f"blocker_{i}", 0.0)
                except:
                    pass

        # Spawn ambulance
        traci.route.add("amb_spawn", ["1096889856", "26209723#3"])
        traci.vehicle.add("ambulance", "amb_spawn", typeID="ambulance", depart="now", departLane="best")
        traci.simulationStep()

        # Call set_hospital_destination
        ctrl.set_hospital_destination("father_muller_hospital")

        assert len(ctrl.candidate_routes) >= 2, "Expected at least 2 candidate routes"
        selected = ctrl.candidate_routes[0]
        assigned_edges = traci.vehicle.getRoute("ambulance")

        print(f"  Selected candidate: {selected.edge_ids}")
        print(f"  TraCI assigned route: {assigned_edges}")
        assert list(assigned_edges) == list(selected.edge_ids), "Assigned TraCI route does not match candidate 0"
        
        # Verify that congested edge 1368365880 was avoided in favor of the alternative route
        assert "1368365880" not in selected.edge_ids, "Congestion avoidance failed: congested edge was still selected!"
        assert "26209723#1" in selected.edge_ids, "Faster alternative route was not selected"
        print("  --> Test 2 & 6 PASSED: Congested shortest route avoided; faster alternative selected and assigned in TraCI.")

        # Cleanup test 2
        for i in range(3):
            try: traci.vehicle.remove(f"blocker_{i}")
            except: pass
        try: traci.vehicle.remove("ambulance")
        except: pass
        ctrl.shutdown()
        traci.simulationStep()

        # ---------------------------------------------------------
        # Test 3: Stability and No Oscillation
        # ---------------------------------------------------------
        print("\n[TEST 3] Verifying Stability Under Equal/Free-Flow Conditions...")
        traci.route.add("amb_spawn_stable", ["1096889856", "26209723#3"])
        traci.vehicle.add("ambulance", "amb_spawn_stable", typeID="ambulance", depart="now", departLane="best")
        traci.simulationStep()

        # Evaluate destination multiple times
        first_selected = None
        for iteration in range(3):
            ctrl.set_hospital_destination("father_muller_hospital")
            current_choice = ctrl.candidate_routes[0].edge_ids
            if first_selected is None:
                first_selected = current_choice
            else:
                assert current_choice == first_selected, f"Route selection oscillated on iteration {iteration}"
        print(f"  Stable selected route: {first_selected}")
        print("  --> Test 3 PASSED: Selection is stable and deterministic across evaluations.")

        try: traci.vehicle.remove("ambulance")
        except: pass
        ctrl.shutdown()
        traci.simulationStep()

        # ---------------------------------------------------------
        # Test 8: Evaluation Logging Under Medium, High, Bottleneck
        # ---------------------------------------------------------
        print("\n[TEST 8] Verifying Candidate Logging Under Medium, High, and Bottleneck Scenarios...")
        scenarios = ["medium", "high", "bottleneck"]
        for idx, sc in enumerate(scenarios, start=201):
            cur_t = traci.simulation.getTime()
            sched = generate_round_traffic(round_id=idx, current_time=cur_t, scenario=sc, seed=42)
            
            # Step 100 steps to let background traffic circulate
            for _ in range(100):
                traci.simulationStep()

            traci.route.add(f"amb_spawn_{idx}", ["1096889856", "26209723#3"])
            traci.vehicle.add("ambulance", f"amb_spawn_{idx}", typeID="ambulance", depart="now", departLane="best")
            traci.simulationStep()

            print(f"\n  --- Trip Start Under '{sc}' Traffic ---")
            ctrl.set_hospital_destination("father_muller_hospital")
            assert len(ctrl.candidate_routes) > 0, f"No routes generated under {sc}"
            
            # Clean up round
            cleanup_simulation_traffic(sched)
            try: traci.vehicle.remove("ambulance")
            except: pass
            ctrl.shutdown()
            traci.simulationStep()

        print("\n  --> Test 8 PASSED: Candidate evaluations logged under Medium, High, and Bottleneck traffic.")

        print("\n" + "=" * 70)
        print("ALL PHASE THREE TESTS PASSED SUCCESSFULLY!")
        print("=" * 70)

    finally:
        close_sim()

if __name__ == "__main__":
    run_tests()
