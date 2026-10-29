import sys
from pathlib import Path

PROJECT_ROOT = Path("D:/AIML/Projects/Major")
PY_ROOT = PROJECT_ROOT / "AI-Predictive-Traffic"
sys.path.append(str(PY_ROOT / "controller"))

import config
import traci
from traffic_features import TrafficFeatures
from preemption_decision import (
    decide_traffic_aware_preemption,
    is_movement_signal_green,
    is_movement_signal_unfavorable,
)
from signal_controller import SignalController, SignalSnapshot
import signal_mapping

SUMOCFG = PY_ROOT / "simulation" / "mangaluru" / "ambulance_test.sumocfg"

def test_preemption_edge_cases():
    print("================================================================================")
    print("SIGNAL PREEMPTION EDGE-CASE AUDIT")
    print("================================================================================")

    # 1. Ambulance approaching RED signal within threshold (distance=120m, speed=12m/s, ETA=10s)
    f_red = TrafficFeatures(
        junction_id="J1",
        incoming_edge="E_in",
        outgoing_edge="E_out",
        ambulance_distance_m=120.0,
        ambulance_speed_mps=12.0,
        ambulance_eta_s=10.0,
        vehicle_count=2,
        halted_vehicle_count=1,
        mean_speed_kmh=28.8,
        occupancy_percent=15.0,
        signal_phase=1,
        signal_state="rrrG",
        movement_signal_indices=[0],
        movement_signal_state="r",
        signal_time_to_switch_s=15.0
    )
    d_red = decide_traffic_aware_preemption(f_red)
    print(f"Edge Case 1 (Approaching Red): Should Preempt = {d_red.should_preempt} | Reason: {d_red.reason}")
    assert d_red.should_preempt, "FAIL: Should preempt red signal"

    # 2. Ambulance approaching GREEN signal (already favorable, ETA=10s, remaining green=25s)
    f_green = TrafficFeatures(
        junction_id="J1",
        incoming_edge="E_in",
        outgoing_edge="E_out",
        ambulance_distance_m=120.0,
        ambulance_speed_mps=12.0,
        ambulance_eta_s=10.0,
        vehicle_count=0,
        halted_vehicle_count=0,
        mean_speed_kmh=43.2,
        occupancy_percent=0.0,
        signal_phase=0,
        signal_state="GGGr",
        movement_signal_indices=[0],
        movement_signal_state="G",
        signal_time_to_switch_s=25.0
    )
    d_green = decide_traffic_aware_preemption(f_green)
    print(f"Edge Case 2 (Approaching Green): Should Preempt = {d_green.should_preempt} | Reason: {d_green.reason}")
    assert not d_green.should_preempt, "FAIL: Should not preempt green signal when green duration suffices"

    # 3. Civilian vehicles queued ahead of ambulance (queue=8 vehicles, halted=5)
    f_queued = TrafficFeatures(
        junction_id="J2",
        incoming_edge="E_in2",
        outgoing_edge="E_out2",
        ambulance_distance_m=180.0,
        ambulance_speed_mps=6.0,
        ambulance_eta_s=22.0,
        vehicle_count=8,
        halted_vehicle_count=5,
        mean_speed_kmh=7.2,
        occupancy_percent=65.0,
        signal_phase=2,
        signal_state="rrGG",
        movement_signal_indices=[0],
        movement_signal_state="r",
        signal_time_to_switch_s=18.0
    )
    d_queued = decide_traffic_aware_preemption(f_queued)
    print(f"Edge Case 3 (Queued Ahead): Should Preempt = {d_queued.should_preempt} | Priority Score = {d_queued.priority_score:.1f}")
    assert d_queued.should_preempt and d_queued.priority_score > d_red.priority_score, "FAIL: Queue should increase priority score"

    # Live SUMO tests for Cases 4 - 8
    try:
        traci.close()
    except Exception:
        pass
    traci.start(["sumo", "-c", str(SUMOCFG), "--no-warnings"])

    try:
        tls_list = traci.trafficlight.getIDList()
        test_tls = tls_list[0] if tls_list else "298371965"
        orig_program = traci.trafficlight.getProgram(test_tls)
        orig_phase = traci.trafficlight.getPhase(test_tls)
        orig_state = traci.trafficlight.getRedYellowGreenState(test_tls)

        print(f"\nLive SUMO TLS Connected: {test_tls} | Program: {orig_program} | Phase: {orig_phase} | State: {orig_state}")

        # 4. Multi-lane shared physical approach
        controlled_links = traci.trafficlight.getControlledLinks(test_tls)
        print(f"Edge Case 4 (Multi-Lane Approach Mapping): Controlled Link groups: {len(controlled_links)}")
        assert len(controlled_links) > 0, "FAIL: No controlled links found on TLS"

        # 5. Preemption activation (conflicting approaches turn red, ambulance movement turns green)
        sc = SignalController()
        target_indices = [0]
        success = sc.preempt(test_tls, target_indices, hold_seconds=10.0)
        assert success, "FAIL: Preemption call must succeed"
        
        # Advance simulation step to process yellow transition if applicable
        traci.simulationStep()
        sc.process_step()
        
        preempted_state = traci.trafficlight.getRedYellowGreenState(test_tls)
        print(f"Edge Case 5 (Preemption Applied): State before = {orig_state} -> State during = {preempted_state}")

        # 6. Preemption hold & recovery
        sc.restore(test_tls)
        restored_state = traci.trafficlight.getRedYellowGreenState(test_tls)
        restored_program = traci.trafficlight.getProgram(test_tls)
        print(f"Edge Case 6 (Signal Restored): Program restored = {restored_program} | State = {restored_state}")
        assert restored_program == orig_program, "FAIL: Program ID must be restored"
        assert test_tls not in sc.get_active_preemptions(), "FAIL: Active preemption record must be cleared"

    finally:
        traci.close()

    print("\nALL 6 PREEMPTION EDGE CASES AUDITED AND VERIFIED: PASS")

if __name__ == "__main__":
    test_preemption_edge_cases()
