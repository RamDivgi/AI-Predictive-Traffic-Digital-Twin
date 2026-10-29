"""
FINAL SYSTEM BASELINE VERIFICATION SUITE
========================================
Validates all critical components of the Mangaluru AI Digital Twin:
1. Python dependencies and configuration validation
2. Network and route loading (Mangaluru AI SUMO network)
3. Hospital destination resolution (HospitalManager)
4. Production & Candidate ETA model loading and inference
5. Staging adapter dry-run and safety tests
6. Bounded SUMO simulation smoke test (15 steps)
7. Routing (A*) and signal preemption initialization
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
import numpy as np
import pandas as pd
import joblib

PROJECT_ROOT = Path("D:/AIML/Projects/Major/AI-Predictive-Traffic")
sys.path.append(str(PROJECT_ROOT / "controller"))
sys.path.append(str(PROJECT_ROOT / "scratch" / "phase5_staging"))

def run_tests():
    print("=" * 80)
    print("MANGALURU AI DIGITAL TWIN — COMPONENT VALIDATION SUITE")
    print("=" * 80)
    results = {}

    # Test 1: Imports and configuration
    print("\n[Test 1/7] Validating imports and configuration...")
    try:
        import config
        import sumolib
        import traci
        from signal_controller import SignalController
        from hospital_manager import HospitalManager
        import astar_router
        print("  -> All core modules imported successfully.")
        results["test_1_imports"] = "PASSED"
    except Exception as e:
        print(f"  FAILED: {e}")
        results["test_1_imports"] = f"FAILED: {e}"
        return results

    # Test 2: Network loading
    print("\n[Test 2/7] Validating SUMO network loading...")
    net_path = PROJECT_ROOT / "simulation" / "mangaluru" / "mangaluru_ai.net.xml.gz"
    try:
        assert net_path.exists(), f"Network file missing: {net_path}"
        net = sumolib.net.readNet(str(net_path))
        num_edges = len(net.getEdges())
        num_nodes = len(net.getNodes())
        print(f"  -> Network loaded: {num_edges} edges, {num_nodes} nodes.")
        assert num_edges > 1000
        results["test_2_network"] = "PASSED"
    except Exception as e:
        print(f"  FAILED: {e}")
        results["test_2_network"] = f"FAILED: {e}"

    # Test 3: Hospital resolution
    print("\n[Test 3/7] Validating hospital destination resolution...")
    labels_path = PROJECT_ROOT / "simulation" / "mangaluru" / "presentation_labels.add.xml"
    try:
        hm = HospitalManager(str(net_path), str(labels_path))
        known_hospitals = ["athena_hospital", "highland_hospital", "kmc_hospital", "father_muller_hospital"]
        resolved = {}
        for hid in known_hospitals:
            h = hm.get_hospital(hid)
            assert h is not None, f"Hospital {hid} not resolved"
            assert h.nearest_edge, f"Hospital {hid} has no nearest edge"
            resolved[hid] = h.nearest_edge
            print(f"  -> Resolved {hid:<24} -> Edge: {h.nearest_edge}")
        results["test_3_hospitals"] = "PASSED"
    except Exception as e:
        print(f"  FAILED: {e}")
        results["test_3_hospitals"] = f"FAILED: {e}"

    # Test 4: ETA model loading and inference
    print("\n[Test 4/7] Validating ETA models (Production & Candidate)...")
    prod_path = PROJECT_ROOT / "models" / "eta_prediction_model.joblib"
    cand_path = PROJECT_ROOT / "scratch" / "phase3_eta" / "models" / "mangaluru_eta_candidate.joblib"
    try:
        assert prod_path.exists(), f"Production model missing: {prod_path}"
        prod_model = joblib.load(prod_path)
        
        # Test sample inference on production model
        prod_sample = pd.DataFrame([{
            "ambulance_speed_mps": 12.0,
            "ambulance_speed_kmh": 43.2,
            "distance_to_junction_m": 80.0,
            "vehicle_count": 3,
            "halted_vehicle_count": 0,
            "mean_speed_kmh": 35.0,
            "occupancy_percent": 15.0,
            "signal_phase": 0,
            "signal_time_to_switch_s": 10.0,
            "junction_id": "9979735204",
            "incoming_edge": "1089450246#0",
            "outgoing_edge": "27191039#0",
        }])
        prod_pred = float(prod_model.predict(prod_sample)[0])
        print(f"  -> Production model inference OK: ETA = {prod_pred:.2f}s")

        assert cand_path.exists(), f"Candidate model missing: {cand_path}"
        cand_model = joblib.load(cand_path)
        cand_sample = pd.DataFrame([{
            "ambulance_speed_mps": 12.0,
            "distance_to_junction_m": 80.0,
            "vehicle_count": 3,
            "halted_vehicle_count": 0,
            "mean_speed_kmh": 35.0,
            "occupancy_percent": 15.0,
            "signal_phase": 0,
            "signal_time_to_switch_s": 10.0,
        }])
        cand_pred = float(cand_model.predict(cand_sample)[0])
        print(f"  -> Candidate model inference OK: ETA = {cand_pred:.2f}s")
        results["test_4_eta_models"] = "PASSED"
    except Exception as e:
        print(f"  FAILED: {e}")
        results["test_4_eta_models"] = f"FAILED: {e}"

    # Test 5: Staging adapter dry run
    print("\n[Test 5/7] Validating staging adapter safety tests...")
    try:
        from staging_adapter import StagingETAAdapter
        adapter = StagingETAAdapter(dry_run=True)
        f_dict = adapter.extract_candidate_features(10.0, 50.0, 1, 0, 30.0, 10.0, 0, 10.0)
        eta_val = adapter.predict_eta(f_dict)
        dec, reason = adapter.evaluate_preemption_decision(eta_val, 50.0, True, 10.0, 0)
        assert dec is False, "Dry run must never return True for execution"
        print(f"  -> Staging adapter safety verified (dry-run decision={dec}).")
        results["test_5_staging_adapter"] = "PASSED"
    except Exception as e:
        print(f"  FAILED: {e}")
        results["test_5_staging_adapter"] = f"FAILED: {e}"

    # Test 6: Bounded SUMO smoke test
    print("\n[Test 6/7] Running bounded SUMO smoke test (15 steps)...")
    sumocfg_path = PROJECT_ROOT / "simulation" / "mangaluru" / "ambulance_test.sumocfg"
    try:
        assert sumocfg_path.exists(), f"Sumocfg missing: {sumocfg_path}"
        try:
            traci.close()
        except Exception:
            pass
        traci.start(["sumo", "-c", str(sumocfg_path), "--step-length", "1.0", "--no-warnings"])
        for s in range(15):
            traci.simulationStep()
        t = traci.simulation.getTime()
        veh_count = traci.vehicle.getIDCount()
        traci.close()
        print(f"  -> SUMO smoke test complete: simulated {t}s, vehicles tracked: {veh_count}.")
        results["test_6_sumo_smoke"] = "PASSED"
    except Exception as e:
        print(f"  FAILED: {e}")
        results["test_6_sumo_smoke"] = f"FAILED: {e}"
        try:
            traci.close()
        except Exception:
            pass

    # Test 7: Routing and Signal Controller Initialization
    print("\n[Test 7/7] Validating A* routing & signal controller...")
    try:
        import config
        config.NET_FILE = net_path
        astar_router._SUMO_NETWORK = net
        router = astar_router.AStarRouter(str(net_path))
        dest_edge = hm.get_hospital("athena_hospital").nearest_edge
        route = router.find_route("1089450246#0", dest_edge)
        assert route is not None, "Failed to compute A* route"
        assert len(route.edge_ids) > 0, "Route edge list is empty"
        print(f"  -> A* Route found: {len(route.edge_ids)} edges, distance: {route.total_distance_m:.1f}m, est. time: {route.estimated_travel_time_s:.1f}s.")
        
        # Test Signal Controller initialization
        s_ctl = SignalController()
        print(f"  -> SignalController initialized successfully.")
        results["test_7_routing_signals"] = "PASSED"
    except Exception as e:
        print(f"  FAILED: {e}")
        results["test_7_routing_signals"] = f"FAILED: {e}"

    print("\n" + "=" * 80)
    all_passed = all(v == "PASSED" for v in results.values())
    print(f"TEST SUMMARY: {'ALL TESTS PASSED (7/7)' if all_passed else 'SOME TESTS FAILED'}")
    for k, v in results.items():
        print(f"  {k:<28}: {v}")
    print("=" * 80)
    return results

if __name__ == "__main__":
    res = run_tests()
    if not all(v == "PASSED" for v in res.values()):
        sys.exit(1)
