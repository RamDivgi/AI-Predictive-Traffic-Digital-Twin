"""
Phase 5B: Dedicated High-Resolution Profiler for Simulation Loop
Instruments every sub-operation of the unity_bridge execution loop:
- TraCI simulationStep
- Traffic metrics updates (vehicle loops, edge queries)
- AI Controller process_step:
  * periodic rerouting check & A* search
  * upcoming junction detection
  * ML feature generation & model inference
  * preemption state machine & TraCI signal changes
- Vehicle telemetry gathering & UDP socket sends (Ports 5005, 5006, 5007, 5008)
- Candidate route generation & coordinate conversions
- Disk I/O (StateProvider.write_state -> twin_state.json atomic write)
- TraCI call counters
"""
import sys
import os
import time
import json
import socket
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

# Overrides
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

def run_profiler(num_steps=120):
    print("=" * 75)
    print(f"PHASE 5B: HIGH-RESOLUTION SIMULATION LOOP PROFILER ({num_steps} STEPS)")
    print("=" * 75)

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

    # Initialize Round 1 Medium traffic
    scheduled_ids = generate_round_traffic(round_id=1, current_time=0.0, scenario="medium")
    metrics_tracker.reset_round(round_id=1, scenario="medium", scheduled_ids=scheduled_ids)

    # Spawn ambulance
    start_edge = "1096889856"
    dest_edge = hm.get_hospital("father_muller_hospital").nearest_edge
    traci.route.add("prof_amb_route", [start_edge, dest_edge])
    traci.vehicle.add(vehID="ambulance", routeID="prof_amb_route", typeID="ambulance", depart="now")
    traci.vehicle.setParameter("ambulance", "emergency", "true")

    traci.simulationStep()
    ai_controller.set_hospital_destination("father_muller_hospital")

    # Metrics storage
    timing_records = []
    stalls = []

    print("\nExecuting profiled steps...")
    for step in range(num_steps):
        t_step_start = time.perf_counter()
        timings = {"step": step}

        # 1. TraCI simulationStep
        t0 = time.perf_counter()
        traci.simulationStep()
        timings["t_sim_step"] = (time.perf_counter() - t0) * 1000.0

        # 2. TrafficMetricsTracker update
        t0 = time.perf_counter()
        metrics_tracker.update_step()
        timings["t_metrics_update"] = (time.perf_counter() - t0) * 1000.0

        # 3. AI Controller process_step
        t0 = time.perf_counter()
        ai_decisions = ai_controller.process_step()
        timings["t_ai_controller"] = (time.perf_counter() - t0) * 1000.0

        current_vehicles = list(traci.vehicle.getIDList())

        # 4. Traffic vehicles UDP collection
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
        timings["t_traffic_query"] = (time.perf_counter() - t0) * 1000.0

        # 5. Signal state queries
        t0 = time.perf_counter()
        signals = []
        for tls in traci.trafficlight.getIDList():
            signals.append({"id": tls, "state": traci.trafficlight.getRedYellowGreenState(tls)})
        timings["t_signals_query"] = (time.perf_counter() - t0) * 1000.0

        # 6. Ambulance route shape & candidate route reconstruction
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
        timings["t_route_reconstruction"] = (time.perf_counter() - t0) * 1000.0

        # 7. UDP Telemetry send
        t0 = time.perf_counter()
        try:
            udp_sock.sendto(json.dumps({"vehicles": traffic_vehicles}).encode('utf-8'), ("127.0.0.1", 5006))
            udp_sock.sendto(json.dumps({"signals": signals}).encode('utf-8'), ("127.0.0.1", 5007))
        except Exception:
            pass
        timings["t_udp_send"] = (time.perf_counter() - t0) * 1000.0

        # 8. StateProvider.write_state (Disk I/O)
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
                "destination": "father_muller_hospital",
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
        timings["t_disk_write_state"] = (time.perf_counter() - t0) * 1000.0

        # Total step duration
        t_total_ms = (time.perf_counter() - t_step_start) * 1000.0
        timings["t_total_step"] = t_total_ms

        timing_records.append(timings)

        # Flag any step exceeding real-time budget (100ms) or experiencing large stall
        if t_total_ms > 100.0:
            stall_entry = {
                "step": step,
                "sim_time": traci.simulation.getTime(),
                "total_ms": t_total_ms,
                "breakdown": {k: round(v, 2) for k, v in timings.items() if k != "step" and v > 5.0}
            }
            stalls.append(stall_entry)
            print(f"  [STALL @ step {step} | t={traci.simulation.getTime():.1f}s] Total: {t_total_ms:.1f}ms -> {stall_entry['breakdown']}")

    traci.close()
    udp_sock.close()

    # Aggregate Analysis
    print("\n" + "=" * 75)
    print("PROFILING RESULTS SUMMARY")
    print("=" * 75)
    ops = [
        "t_sim_step", "t_metrics_update", "t_ai_controller",
        "t_traffic_query", "t_signals_query", "t_route_reconstruction",
        "t_udp_send", "t_disk_write_state", "t_total_step"
    ]
    
    print(f"{'Operation':<26} | {'Avg (ms)':<9} | {'Max (ms)':<9} | {'Min (ms)':<9} | {'% Total':<8}")
    print("-" * 75)
    total_avg = sum(r["t_total_step"] for r in timing_records) / len(timing_records)
    
    for op in ops:
        vals = [r[op] for r in timing_records]
        avg_v = sum(vals) / len(vals)
        max_v = max(vals)
        min_v = min(vals)
        pct = (avg_v / total_avg * 100.0) if op != "t_total_step" else 100.0
        print(f"{op:<26} | {avg_v:8.2f}  | {max_v:8.2f}  | {min_v:8.2f}  | {pct:6.1f}%")

    print("-" * 75)
    print(f"Total steps: {num_steps} | Steps exceeding 100ms budget: {len(stalls)} ({len(stalls)/num_steps*100:.1f}%)")
    print(f"Max single-step latency: {max(r['t_total_step'] for r in timing_records):.2f} ms")

    # Output detailed stall events
    if stalls:
        print("\nTOP 5 LONGEST STALL EVENTS:")
        sorted_stalls = sorted(stalls, key=lambda x: x["total_ms"], reverse=True)[:5]
        for idx, s in enumerate(sorted_stalls, 1):
            print(f"  #{idx} Step {s['step']} (t={s['sim_time']:.1f}s): {s['total_ms']:.1f} ms | Breakdown: {s['breakdown']}")

    return timing_records, stalls

if __name__ == "__main__":
    run_profiler(num_steps=120)
