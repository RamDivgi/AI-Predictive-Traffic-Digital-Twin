"""
Phase Two Test Suite: Configurable Traffic Scenarios & Lifecycle Validation
Validates:
1. Scenario Generation profiles: Low (25), Medium (68), High (110), Bottleneck (74).
2. Four deterministic queue vehicles on jam_route across all profiles.
3. TrafficMetricsTracker measurable reporting: scheduled, inserted, active, arrived, removed, waiting, edge speeds, queue lengths.
4. 5 consecutive rounds lifecycle test for stale IDs, duplicate vehicles, leftover scheduled departures, and crashes.
5. Signal restoration verification across consecutive rounds.
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
from controller.traffic_aware_controller import TrafficAwareController
from controller.hospital_manager import HospitalManager
from visualization.unity_bridge import (
    generate_round_traffic,
    cleanup_simulation_traffic,
    TrafficMetricsTracker
)

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
    print("PHASE TWO: CONFIGURABLE TRAFFIC GENERATION VALIDATION")
    print("=" * 70)

    start_sim()
    try:
        # -------------------------------------------------------------
        # Part 1: Scenario Profile & Deterministic Queue Verification
        # -------------------------------------------------------------
        print("\n[PART 1] Verifying Scenario Profiles & Deterministic Queues...")
        scenarios = ["low", "medium", "high", "bottleneck"]
        expected_counts = {"low": 25, "medium": 68, "high": 110, "bottleneck": 74}
        
        tracker = TrafficMetricsTracker()

        for idx, sc in enumerate(scenarios, start=1):
            cur_t = traci.simulation.getTime()
            sched = generate_round_traffic(round_id=idx, current_time=cur_t, scenario=sc)
            exp = expected_counts[sc]
            print(f"  Scenario '{sc}': scheduled {len(sched)} (expected {exp})")
            assert len(sched) == exp, f"Scenario '{sc}' scheduled count mismatch: {len(sched)} != {exp}"
            
            # Verify 4 deterministic queue vehicles
            jam_ids = [f"rnd_{idx}_jam_{i}" for i in range(4)]
            for jid in jam_ids:
                assert jid in sched, f"Deterministic vehicle {jid} missing from scheduled IDs in {sc}"
            
            # Clean up before next scenario check
            cleanup_simulation_traffic(sched)
            traci.simulationStep()
            active_after = traci.vehicle.getIDList()
            assert len(active_after) == 0, f"Lingering vehicles after cleanup in {sc}: {active_after}"
        print("  --> Part 1 PASSED: All 4 scenario profiles generated expected counts and preserved deterministic queue.")

        # -------------------------------------------------------------
        # Part 2: TrafficMetricsTracker & Measurable Reporting
        # -------------------------------------------------------------
        print("\n[PART 2] Verifying TrafficMetricsTracker Measurable Reporting...")
        round_id = 10
        cur_t = traci.simulation.getTime()
        sched = generate_round_traffic(round_id=round_id, current_time=cur_t, scenario="medium")
        tracker.reset_round(round_id=round_id, scenario="medium", scheduled_ids=sched)

        # Run 250 steps (25 simulation seconds) to allow insertions and movement
        for _ in range(250):
            traci.simulationStep()
            tracker.update_step()

        metrics = tracker.get_metrics_dict()
        print(f"  Captured Metrics at Step 250 (sim_time={traci.simulation.getTime():.1f}s):")
        print(f"    Scenario:   {metrics['scenario']}")
        print(f"    Scheduled:  {metrics['scheduled']}")
        print(f"    Inserted:   {metrics['inserted']}")
        print(f"    Active:     {metrics['active']}")
        print(f"    Arrived:    {metrics['arrived']}")
        print(f"    Removed:    {metrics['removed']}")
        print(f"    Waiting:    {metrics['waiting']}")
        print(f"    Mean Speed: {metrics['mean_speed_kmh']} km/h")
        print(f"    Edge Speeds Count: {len(metrics['edge_speeds'])}")
        print(f"    Edge Queues Count: {len(metrics['edge_queues'])}")

        assert metrics["scheduled"] == 68, f"Scheduled metric mismatch: {metrics['scheduled']}"
        assert metrics["inserted"] > 0, "No vehicles were inserted during 25 seconds"
        assert metrics["active"] > 0, "No active vehicles in network"
        assert len(metrics["edge_speeds"]) > 0, "Edge speeds dictionary empty"
        assert len(metrics["edge_queues"]) > 0, "Edge queues dictionary empty"

        # Test cleanup recording
        rem_count = cleanup_simulation_traffic(sched)
        tracker.record_cleanup(rem_count)
        traci.simulationStep()
        tracker.update_step()
        assert tracker.active_count == 0, f"Active vehicles remained after cleanup: {tracker.active_count}"
        print("  --> Part 2 PASSED: Measurable reporting captures scheduled, inserted, active, arrived, removed, waiting, speeds, and queues.")

        # -------------------------------------------------------------
        # Part 3: 5 Consecutive Rounds Lifecycle Test
        # -------------------------------------------------------------
        print("\n[PART 3] Running 5 Consecutive Rounds Lifecycle Test...")
        round_scenarios = ["medium", "low", "bottleneck", "high", "medium"]
        all_seen_ids = set()
        ai_controller = TrafficAwareController()

        for r_num, sc in enumerate(round_scenarios, start=101):
            cur_t = traci.simulation.getTime()
            print(f"\n  --- Round {r_num} ({sc}) ---")
            
            # 1. Schedule traffic
            sched = generate_round_traffic(round_id=r_num, current_time=cur_t, scenario=sc)
            tracker.reset_round(round_id=r_num, scenario=sc, scheduled_ids=sched)
            
            # Check for stale IDs / duplicate IDs across rounds
            duplicates = all_seen_ids.intersection(set(sched))
            assert len(duplicates) == 0, f"Found duplicate IDs across rounds: {duplicates}"
            all_seen_ids.update(sched)

            # 2. Spawn ambulance
            start_edge = "1096889856"
            dest_edge = "26209723#3" # Father Muller
            amb_route_id = f"rnd_{r_num}_amb_route"
            traci.route.add(amb_route_id, [start_edge, dest_edge])
            traci.vehicle.add("ambulance", amb_route_id, typeID="ambulance", depart="now", departLane="best")
            traci.vehicle.setParameter("ambulance", "emergency", "true")

            traci.simulationStep()
            ai_controller.set_hospital_destination("father_muller_hospital")

            # 3. Step for 60 steps (6 seconds)
            for _ in range(60):
                traci.simulationStep()
                ai_controller.process_step()
                tracker.update_step()

            # Active checks
            active_now = traci.vehicle.getIDList()
            print(f"    Mid-round active vehicles: {len(active_now)} (ambulance + background)")
            assert "ambulance" in active_now, "Ambulance missing from simulation"
            assert any(v.startswith(f"rnd_{r_num}_") for v in active_now), f"No round {r_num} background vehicles active"

            # 4. Clean up round completely
            cleanup_simulation_traffic(sched)
            if "ambulance" in traci.vehicle.getIDList():
                try:
                    traci.vehicle.remove("ambulance")
                except:
                    pass
            ai_controller.shutdown()
            traci.simulationStep()

            # 5. Post-cleanup verification: zero vehicles, signals restored
            post_cleanup = traci.vehicle.getIDList()
            print(f"    Post-cleanup active vehicles: {len(post_cleanup)}")
            assert len(post_cleanup) == 0, f"Round {r_num} failed to clean up vehicles: {post_cleanup}"

            active_preemptions = ai_controller.signal_controller.get_active_preemptions()
            assert len(active_preemptions) == 0, f"Round {r_num} left active preemptions: {active_preemptions}"

        print("\n  --> Part 3 PASSED: 5 consecutive rounds completed with 0 duplicate IDs, 0 lingering vehicles, and clean signal restoration.")

        print("\n" + "=" * 70)
        print("ALL PHASE TWO TESTS PASSED SUCCESSFULLY!")
        print("=" * 70)

    finally:
        close_sim()

if __name__ == "__main__":
    run_tests()
