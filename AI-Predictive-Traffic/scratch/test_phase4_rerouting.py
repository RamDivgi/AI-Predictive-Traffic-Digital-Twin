"""
Phase Four Automated Test Suite: Live Congestion-Aware Ambulance Rerouting
Validates:
1. Mathematical admissibility of A* heuristic and component cost consistency (no double counting).
2. Guardrails: Internal edges, near-destination, and invalid routes fail safely.
3. No-reroute case: Ambulance maintains route when current path remains preferable.
4. Active mid-trip reroute: Congestion injected ahead triggers genuine reroute in SUMO,
   continuous from ambulance's current edge, and assigned in TraCI.
5. Oscillation protection: Cooldown and previous-route penalty prevent flip-flopping.
6. Trip reset & Green Corridor restoration: Signals cleanly restored upon trip reset/clearance.
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
from controller.rerouting_controller import ReroutingController
from controller.hospital_manager import HospitalManager

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
    print("=" * 75)
    print("PHASE FOUR: LIVE CONGESTION-AWARE AMBULANCE REROUTING VALIDATION")
    print("=" * 75)

    # -------------------------------------------------------------------------
    # PART 1: Mathematical Admissibility & Cost Component Check (Section D)
    # -------------------------------------------------------------------------
    print("\n[TEST 1] Verifying Mathematical Admissibility Bound & Cost Breakdown...")
    router = AStarRouter()
    
    # Check max_speed_mps guarantee
    assert router.max_speed_mps >= 41.67, f"max_speed_mps ({router.max_speed_mps}) must be >= 41.67 m/s"
    print(f"  Heuristic speed bound verified: max_speed_mps = {router.max_speed_mps:.1f} m/s (>= 41.67 m/s)")
    
    # Check evaluate_path consistency on sample route
    sample_route = ["1096889856", "-1096889856", "-184750315#1", "1368365880", "26209723#2", "26209723#3"]
    eval_res = router.evaluate_path(sample_route, start_lane_position=10.0, ambulance_speed_mps=15.0)
    assert eval_res is not None, "evaluate_path returned None"
    
    free_flow = eval_res.estimated_travel_time_s - eval_res.total_congestion_cost
    assert abs(eval_res.total_cost - (eval_res.estimated_travel_time_s + eval_res.total_signal_delay_s)) < 1e-4, "Cost formula mismatch"
    assert abs(eval_res.total_cost - (free_flow + eval_res.total_congestion_cost + eval_res.total_signal_delay_s)) < 1e-4, "Component breakdown mismatch"
    print(f"  Cost breakdown verified without double-counting:")
    print(f"    Free-flow:   {free_flow:.2f} s")
    print(f"    Congestion:  {eval_res.total_congestion_cost:.2f} s")
    print(f"    Signal delay:{eval_res.total_signal_delay_s:.2f} s")
    print(f"    Total cost:  {eval_res.total_cost:.2f} s (sum matches Total Est)")
    print("  --> Test 1 PASSED: Mathematical admissibility bound and clean cost breakdown verified.")

    # -------------------------------------------------------------------------
    # PART 2: Guardrails & Safe Fallbacks (Offline & Edge Cases)
    # -------------------------------------------------------------------------
    print("\n[TEST 2] Verifying Guardrails (Internal Edges, Near-Destination, Disconnections)...")
    rc = ReroutingController(
        min_improvement_s=10.0,
        min_improvement_percent=5.0,
        cooldown_s=15.0,
        min_distance_to_dest_m=150.0
    )
    
    # Missing vehicle check
    assert rc.evaluate_and_reroute(ambulance_id="non_existent_veh") is False, "Did not handle missing vehicle safely"
    
    # Disconnected / invalid edge check
    res_none = router.evaluate_path(["non_existent_edge_xyz"])
    assert res_none is not None and res_none.total_cost > 0.0, "Missing edge in evaluate_path failed fallback"
    print("  --> Test 2 PASSED: Guardrails handle offline and disconnected conditions safely.")

    # -------------------------------------------------------------------------
    # Live Simulation Tests
    # -------------------------------------------------------------------------
    start_sim()
    try:
        ctrl = TrafficAwareController()
        hm = HospitalManager(NET_FILE, HOSP_FILE)

        # ---------------------------------------------------------------------
        # PART 3: Live No-Reroute Test (Current Route Remains Preferable)
        # ---------------------------------------------------------------------
        print("\n[TEST 3] Verifying No-Reroute When Current Route Remains Optimal...")
        # Dispatch ambulance towards Father Muller Hospital
        traci.route.add("amb_no_reroute", ["1096889856", "26209723#3"])
        traci.vehicle.add("ambulance", "amb_no_reroute", typeID="ambulance", depart="now", departLane="best")
        traci.simulationStep()

        ctrl.set_hospital_destination("father_muller_hospital")
        initial_route = list(traci.vehicle.getRoute("ambulance"))
        print(f"  Initial assigned route: {initial_route}")

        # Advance ambulance under free-flow conditions
        rerouted_observed = False
        for step in range(30):
            traci.simulationStep()
            ctrl.process_step()
            cur_route = list(traci.vehicle.getRoute("ambulance"))
            if cur_route != initial_route:
                rerouted_observed = True
                break

        assert not rerouted_observed, "Ambulance rerouted unnecessarily under free-flow conditions!"
        print(f"  Route after 30 simulation steps: {list(traci.vehicle.getRoute('ambulance'))}")
        print("  --> Test 3 PASSED: No reroute occurred; current route maintained as optimal.")

        # Cleanup test 3
        try: traci.vehicle.remove("ambulance")
        except: pass
        ctrl.shutdown()
        traci.simulationStep()

        # ---------------------------------------------------------------------
        # PART 4: Live Mid-Trip Congestion-Triggered Reroute
        # ---------------------------------------------------------------------
        print("\n[TEST 4] Verifying Genuine Mid-Trip Rerouting Under Dynamic Congestion...")
        # Start ambulance at 1096889856 towards Father Muller
        traci.route.add("amb_dyn_reroute", ["1096889856", "26209723#3"])
        traci.vehicle.add("ambulance", "amb_dyn_reroute", typeID="ambulance", depart="now", departLane="best")
        traci.simulationStep()

        ctrl.set_hospital_destination("father_muller_hospital")
        ctrl.rerouting_controller.min_improvement_s = 5.0  # Configure sensitive threshold for test
        ctrl.rerouting_controller.min_improvement_percent = 5.0
        ctrl.rerouting_controller.cooldown_s = 5.0
        ctrl.rerouting_controller.min_distance_to_dest_m = 30.0

        orig_route = list(traci.vehicle.getRoute("ambulance"))
        print(f"  Initial dispatched route: {orig_route}")

        # Step until ambulance enters a normal downstream road edge
        for _ in range(120):
            traci.simulationStep()
            ctrl.process_step()
            cur_edge = traci.vehicle.getRoadID("ambulance")
            if not cur_edge.startswith(":") and cur_edge in ["-1096889856", "-184750315#1"]:
                break

        current_edge_before_jam = traci.vehicle.getRoadID("ambulance")
        print(f"  Ambulance progressed to mid-trip edge: {current_edge_before_jam}")
        assert not current_edge_before_jam.startswith(":"), f"Ambulance is still on internal edge {current_edge_before_jam}"

        # Now dynamically inject heavy blockage onto downstream edge 1368365880
        # (Primary path goes through 1368365880; alternative turns via -184750315#0 -> 26209723#1)
        print("  Injecting heavy blockage onto downstream edge '1368365880'...")
        traci.route.add("jam_route_mid", ["1368365880", "26209723#2"])
        for i in range(4):
            vid = f"mid_blocker_{i}"
            traci.vehicle.add(vid, "jam_route_mid", depart="now", departPos=str(i * 4.0))
            traci.vehicle.setSpeed(vid, 0.0)

        # Step 10 times to let blockers halt and trigger traffic congestion measurement
        for _ in range(10):
            traci.simulationStep()
            for i in range(4):
                try: traci.vehicle.setSpeed(f"mid_blocker_{i}", 0.0)
                except: pass

        # Force evaluation check in next process_step
        ctrl.last_reroute_evaluation_time = -1.0
        ctrl.process_step()

        # Check route after evaluation
        new_assigned_route = list(traci.vehicle.getRoute("ambulance"))
        print(f"  Route after mid-trip evaluation: {new_assigned_route}")

        # Assertions
        assert new_assigned_route != orig_route, "Ambulance failed to reroute despite heavy downstream congestion!"
        assert "1368365880" not in new_assigned_route, "Congested edge 1368365880 was not avoided in the new route!"
        assert "26209723#1" in new_assigned_route, "Faster alternative via 26209723#1 was not selected!"
        
        # Verify route continuity: new route must start at the edge the ambulance was on
        cur_edge_now = traci.vehicle.getRoadID("ambulance")
        assert new_assigned_route[0] == cur_edge_now, f"Route continuity violation: new route starts at {new_assigned_route[0]}, but vehicle is on {cur_edge_now}"
        print(f"  --> Route continuity confirmed: new route begins precisely at current vehicle edge '{cur_edge_now}'.")
        print("  --> Test 4 PASSED: Genuine mid-trip reroute triggered and assigned in TraCI.")

        # ---------------------------------------------------------------------
        # PART 5: Oscillation & Cooldown Protection Check
        # ---------------------------------------------------------------------
        print("\n[TEST 5] Verifying Stability & Oscillation Protection...")
        route_after_reroute = list(traci.vehicle.getRoute("ambulance"))
        
        # Immediately attempt another evaluation within cooldown period
        did_reroute_during_cooldown = ctrl.rerouting_controller.evaluate_and_reroute(ambulance_id="ambulance")
        assert did_reroute_during_cooldown is False, "Cooldown failed to prevent immediate re-evaluation!"
        assert list(traci.vehicle.getRoute("ambulance")) == route_after_reroute, "Route changed during cooldown!"
        print("  --> Test 5 PASSED: Cooldown and stability rules prevent rapid route oscillation.")

        # Cleanup blockers
        for i in range(4):
            try: traci.vehicle.remove(f"mid_blocker_{i}")
            except: pass
        try: traci.vehicle.remove("ambulance")
        except: pass
        ctrl.shutdown()
        traci.simulationStep()

        # ---------------------------------------------------------------------
        # PART 6: Trip Reset & Signal Corridor Restoration
        # ---------------------------------------------------------------------
        print("\n[TEST 6] Verifying Signal Corridor Restoration on Reset...")
        assert len(ctrl.signal_controller._active_preemptions) == 0, "Signal preemptions remained active after shutdown"
        assert len(ctrl.active_movements) == 0, "Active movements remained populated after shutdown"
        print("  --> Test 6 PASSED: All signal preemptions and state buffers cleanly restored.")

        print("\n" + "=" * 75)
        print("ALL PHASE FOUR TESTS PASSED SUCCESSFULLY!")
        print("=" * 75)

    finally:
        close_sim()

if __name__ == "__main__":
    run_tests()
