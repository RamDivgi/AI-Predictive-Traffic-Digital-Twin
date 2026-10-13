"""
Phase 5C: Comprehensive Baseline Profiling Script (Bounded 2-Minute Simulation)
Measures:
1. Trip-start route generation latency
2. Average, 95th-percentile, and maximum step durations over 600-800 steps
3. Fine-grained breakdowns:
   - ML ETA feature construction & predict()
   - Periodic rerouting evaluations
   - TraCI vehicle queries & traffic metrics
   - Signal state queries & preemption
   - Telemetry serialization, disk I/O, and UDP transmissions
4. Effective Unity/dashboard update frequency
"""
import sys
import time
import json
import socket
import numpy as np
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

# Network overrides
astar_router.NETWORK_FILE = MANGALURU_NET
route_evaluator.NETWORK_FILE = MANGALURU_NET
junction_detector.NETWORK_FILE = MANGALURU_NET
route_evaluator._SUMO_NETWORK = None
astar_router._SUMO_NETWORK = None
junction_detector.SUMO_NETWORK = sumolib.net.readNet(str(MANGALURU_NET))

from visualization.unity_bridge import (
    TrafficMetricsTracker,
    generate_round_traffic,
    generate_dynamic_traffic,
    _build_candidate_route_data
)

def run_baseline_profile(num_steps=600):
    print("=" * 80)
    print(f"PHASE 5C: BASELINE PROFILING ({num_steps} SIMULATION STEPS)")
    print("=" * 80)

    generate_dynamic_traffic()

    traci.start([
        "sumo",
        "-c", str(SUMO_CONFIG),
        "--step-length", "0.1",
        "--random",
        "--ignore-route-errors",
        "--start"
    ])

    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    metrics_tracker = TrafficMetricsTracker()
    ai_controller = TrafficAwareController()
    hm = HospitalManager(str(config.NET_FILE), str(config.HOSPITALS_FILE))

    # Initialize Medium background traffic
    scheduled_ids = generate_round_traffic(round_id=1, current_time=0.0, scenario="medium")
    metrics_tracker.reset_round(round_id=1, scenario="medium", scheduled_ids=scheduled_ids)

    # Measure trip-start route generation
    print("\n[PHASE 1] Measuring Trip-Start Route Generation Latency...")
    t_start_begin = time.perf_counter()
    start_edge = "1096889856"
    dest_edge = hm.get_hospital("kmc_hospital").nearest_edge
    traci.route.add("prof_kmc_route", [start_edge, dest_edge])
    traci.vehicle.add(vehID="ambulance", routeID="prof_kmc_route", typeID="ambulance", depart="now")
    traci.vehicle.setParameter("ambulance", "emergency", "true")
    traci.simulationStep()
    ai_controller.set_hospital_destination("kmc_hospital")
    t_trip_start_total_ms = (time.perf_counter() - t_start_begin) * 1000.0
    print(f"  Trip-Start Route Generation Total Time: {t_trip_start_total_ms:8.2f} ms")

    records = []
    ml_inference_times = []
    reroute_eval_times = []

    print(f"\n[PHASE 2] Executing {num_steps} profiled simulation steps...")

    for step in range(num_steps):
        t_step_start = time.perf_counter()
        step_metrics = {"step": step, "sim_time": traci.simulation.getTime()}

        # 1. TraCI simulationStep
        t0 = time.perf_counter()
        traci.simulationStep()
        step_metrics["t_sim_step"] = (time.perf_counter() - t0) * 1000.0

        # 2. TrafficMetricsTracker update
        t0 = time.perf_counter()
        metrics_tracker.update_step()
        step_metrics["t_metrics_update"] = (time.perf_counter() - t0) * 1000.0

        # 3. AI Controller process_step
        t0 = time.perf_counter()
        last_eval_time_before = ai_controller.last_reroute_evaluation_time
        ai_decisions = ai_controller.process_step()
        t_ai = (time.perf_counter() - t0) * 1000.0
        step_metrics["t_ai_controller"] = t_ai

        # Track if reroute evaluation occurred during this step
        if ai_controller.last_reroute_evaluation_time != last_eval_time_before:
            reroute_eval_times.append((step, t_ai))

        current_vehicles = list(traci.vehicle.getIDList())

        # 4. Traffic vehicles query
        t0 = time.perf_counter()
        traffic_vehicles = []
        amb_pos = traci.vehicle.getPosition("ambulance") if "ambulance" in current_vehicles else (0.0, 0.0)
        for v_id in current_vehicles:
            if v_id == "ambulance":
                continue
            try:
                x, y = traci.vehicle.getPosition(v_id)
                angle = traci.vehicle.getAngle(v_id)
                speed = traci.vehicle.getSpeed(v_id)
                traffic_vehicles.append({"id": v_id, "x": x, "y": 0.0, "z": y, "angle": angle, "speed": speed})
            except Exception:
                pass
        step_metrics["t_traffic_query"] = (time.perf_counter() - t0) * 1000.0

        # 5. Signals query
        t0 = time.perf_counter()
        signals = []
        for tls in traci.trafficlight.getIDList():
            signals.append({"id": tls, "state": traci.trafficlight.getRedYellowGreenState(tls)})
        step_metrics["t_signals_query"] = (time.perf_counter() - t0) * 1000.0

        # 6. Route reconstruction
        t0 = time.perf_counter()
        route_coords = []
        if "ambulance" in current_vehicles:
            try:
                route = traci.vehicle.getRoute("ambulance")
                for e in route:
                    shape = traci.lane.getShape(e + "_0")
                    for p in shape:
                        route_coords.append([p[0], p[1]])
            except Exception:
                pass
        cands_data = _build_candidate_route_data(
            getattr(ai_controller, 'candidate_routes', None),
            junction_detector.SUMO_NETWORK
        )
        step_metrics["t_route_reconstruction"] = (time.perf_counter() - t0) * 1000.0

        # 7. UDP telemetry broadcast
        t0 = time.perf_counter()
        try:
            udp_sock.sendto(json.dumps({"vehicles": traffic_vehicles}).encode('utf-8'), ("127.0.0.1", 5006))
            udp_sock.sendto(json.dumps({"signals": signals}).encode('utf-8'), ("127.0.0.1", 5007))
        except Exception:
            pass
        step_metrics["t_udp_send"] = (time.perf_counter() - t0) * 1000.0

        # 8. Disk I/O (StateProvider.write_state)
        t0 = time.perf_counter()
        state_dict = {
            "simulation_time": traci.simulation.getTime(),
            "ambulance": {
                "vehicle_id": "ambulance",
                "latitude": amb_pos[0],
                "longitude": amb_pos[1],
                "speed": traci.vehicle.getSpeed("ambulance") if "ambulance" in current_vehicles else 0.0,
                "current_edge": traci.vehicle.getRoadID("ambulance") if "ambulance" in current_vehicles else "",
                "current_route": "",
                "destination": "kmc_hospital",
                "eta": 0.0,
                "remaining_distance": 0.0,
                "progress_pct": 0.0
            },
            "route": {
                "coordinates": route_coords,
                "candidates": cands_data,
            },
            "traffic": [],
            "signals": signals,
            "decisions": [],
            "traffic_metrics": metrics_tracker.get_metrics_dict()
        }
        StateProvider.write_state(state_dict)
        step_metrics["t_disk_write"] = (time.perf_counter() - t0) * 1000.0

        t_total_ms = (time.perf_counter() - t_step_start) * 1000.0
        step_metrics["t_total_step"] = t_total_ms
        records.append(step_metrics)

        # Early exit if ambulance finished route
        if "ambulance" not in current_vehicles and step > 10:
            print(f"  Ambulance reached destination at step {step} (t={traci.simulation.getTime():.1f}s)")
            break

    traci.close()
    udp_sock.close()

    # Step durations analysis
    total_steps = len(records)
    total_times = np.array([r["t_total_step"] for r in records])
    ai_times = np.array([r["t_ai_controller"] for r in records])
    sim_times = np.array([r["t_sim_step"] for r in records])
    metrics_times = np.array([r["t_metrics_update"] for r in records])
    traffic_times = np.array([r["t_traffic_query"] for r in records])
    signals_times = np.array([r["t_signals_query"] for r in records])
    route_times = np.array([r["t_route_reconstruction"] for r in records])
    udp_times = np.array([r["t_udp_send"] for r in records])
    disk_times = np.array([r["t_disk_write"] for r in records])

    avg_step = np.mean(total_times)
    p95_step = np.percentile(total_times, 95)
    max_step = np.max(total_times)
    min_step = np.min(total_times)

    effective_hz = 1000.0 / avg_step if avg_step > 0 else 0.0

    print("\n" + "=" * 80)
    print("STEP 1 MEASUREMENT RESULTS: BASELINE PROFILING")
    print("=" * 80)
    print(f"Total Profiled Steps:           {total_steps}")
    print(f"Trip-Start Route Gen Latency:   {t_trip_start_total_ms:8.2f} ms")
    print(f"Average Step Duration:          {avg_step:8.2f} ms")
    print(f"95th-Percentile Step Duration:  {p95_step:8.2f} ms")
    print(f"Maximum Step Duration:          {max_step:8.2f} ms")
    print(f"Minimum Step Duration:          {min_step:8.2f} ms")
    print(f"Effective Unity/Dashboard Rate: {effective_hz:8.2f} Hz (Target: 10.0 Hz)")
    print("-" * 80)
    print(f"{'Sub-Operation':<26} | {'Avg (ms)':<9} | {'P95 (ms)':<9} | {'Max (ms)':<9} | {'% of Total':<10}")
    print("-" * 80)
    for name, arr in [
        ("t_sim_step", sim_times),
        ("t_metrics_update", metrics_times),
        ("t_ai_controller", ai_times),
        ("t_traffic_query", traffic_times),
        ("t_signals_query", signals_times),
        ("t_route_reconstruction", route_times),
        ("t_udp_send", udp_times),
        ("t_disk_write", disk_times),
    ]:
        m_avg = np.mean(arr)
        m_p95 = np.percentile(arr, 95)
        m_max = np.max(arr)
        pct = (m_avg / avg_step) * 100.0
        print(f"{name:<26} | {m_avg:8.2f}  | {m_p95:8.2f}  | {m_max:8.2f}  | {pct:8.1f}%")

    print("-" * 80)
    print(f"Periodic Reroute Evaluations:   {len(reroute_eval_times)} events")
    if reroute_eval_times:
        eval_durations = [d[1] for d in reroute_eval_times]
        print(f"  Avg Reroute Eval Duration:    {np.mean(eval_durations):8.2f} ms")
        print(f"  Max Reroute Eval Duration:    {np.max(eval_durations):8.2f} ms")

    # Step budget distribution
    under_50 = np.sum(total_times <= 50.0) / total_steps * 100.0
    b_50_100 = np.sum((total_times > 50.0) & (total_times <= 100.0)) / total_steps * 100.0
    over_100 = np.sum(total_times > 100.0) / total_steps * 100.0
    print(f"\nStep Duration Distribution:")
    print(f"  <= 50 ms:        {under_50:5.1f}%")
    print(f"  50 ms - 100 ms:  {b_50_100:5.1f}%")
    print(f"  > 100 ms:        {over_100:5.1f}%")

    return {
        "trip_start_ms": t_trip_start_total_ms,
        "avg_step": avg_step,
        "p95_step": p95_step,
        "max_step": max_step,
        "min_step": min_step,
        "effective_hz": effective_hz,
        "ai_avg": np.mean(ai_times),
        "ai_p95": np.percentile(ai_times, 95),
        "ai_max": np.max(ai_times),
    }

if __name__ == "__main__":
    run_baseline_profile(num_steps=600)
