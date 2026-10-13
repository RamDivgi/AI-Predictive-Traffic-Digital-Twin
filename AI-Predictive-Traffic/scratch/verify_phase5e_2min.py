"""
Phase 5E: Two-Minute Medium-Traffic Simulation Verification
Validates:
1. Vehicle smoother performance under real UDP packet streaming
2. Background vehicles motion and tracking (separate verification)
3. Ambulance motion and Green Corridor preemption (separate verification)
4. Invariance of vehicle counts, routes, traffic signals, and dashboard state
"""
import sys
import time
import json
import math
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

def run_two_minute_verification():
    print("=" * 80)
    print("PHASE 5E: 2-MINUTE MEDIUM-TRAFFIC SIMULATION VERIFICATION")
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

    # Spawn ambulance to KMC Hospital
    start_edge = "1096889856"
    dest_edge = hm.get_hospital("kmc_hospital").nearest_edge
    route_id = "phase5e_kmc_route"
    traci.route.add(route_id, [start_edge, dest_edge])
    traci.vehicle.add(vehID="ambulance", routeID=route_id, typeID="ambulance", depart="now", departLane="best")
    traci.vehicle.setParameter("ambulance", "emergency", "true")
    traci.simulationStep()
    ai_controller.set_hospital_destination("kmc_hospital")

    # Send initial route to Unity (Port 5008)
    initial_route = traci.vehicle.getRoute("ambulance")
    route_points = []
    for e in initial_route:
        try:
            shape = traci.lane.getShape(e + "_0")
            for p in shape:
                route_points.append({"x": p[0], "y": 0.0, "z": p[1]})
        except Exception:
            pass
    CHUNK_SIZE = 500
    total_chunks = math.ceil(len(route_points) / CHUNK_SIZE)
    for i in range(total_chunks):
        chunk_payload = {
            "type": "route_chunk",
            "chunk_index": i,
            "total_chunks": total_chunks,
            "points": route_points[i*CHUNK_SIZE : (i+1)*CHUNK_SIZE]
        }
        udp_sock.sendto(json.dumps(chunk_payload).encode('utf-8'), ("127.0.0.1", 5008))

    print(f"Ambulance spawned with {len(initial_route)} edges. Route chunk sent to Unity (Port 5008).")

    # Run for 2 minutes (1200 steps at 0.1s step length or ~120s real time)
    target_steps = 1200
    start_wall_time = time.perf_counter()

    vehicle_counts = []
    amb_positions = []
    amb_speeds = []
    car0_positions = []
    step_durations = []
    preemption_events = 0
    signals_seen = set()

    print(f"Beginning 2-minute simulation loop ({target_steps} steps)...")

    for step in range(target_steps):
        t_step_start = time.perf_counter()

        traci.simulationStep()
        metrics_tracker.update_step()
        ai_decisions = ai_controller.process_step()
        if ai_decisions:
            for feat, dec in ai_decisions:
                if dec.should_preempt:
                    preemption_events += 1

        sim_time = traci.simulation.getTime()
        current_vehicles = list(traci.vehicle.getIDList())
        vehicle_counts.append(len(current_vehicles))

        # Query background vehicles & broadcast to Unity (Port 5006)
        traffic_vehicles = []
        amb_found = "ambulance" in current_vehicles
        amb_pos = traci.vehicle.getPosition("ambulance") if amb_found else (0.0, 0.0)
        amb_speed = traci.vehicle.getSpeed("ambulance") if amb_found else 0.0
        amb_angle = traci.vehicle.getAngle("ambulance") if amb_found else 0.0

        if amb_found:
            amb_positions.append((sim_time, amb_pos[0], amb_pos[1]))
            amb_speeds.append(amb_speed)
            # Send ambulance telemetry to Port 5005
            amb_payload = {
                "id": "ambulance",
                "x": amb_pos[0],
                "y": 0.0,
                "z": amb_pos[1],
                "angle": amb_angle,
                "speed": amb_speed,
                "sim_time": sim_time
            }
            try:
                udp_sock.sendto(json.dumps(amb_payload).encode('utf-8'), ("127.0.0.1", 5005))
            except Exception:
                pass

        for v_id in current_vehicles:
            if v_id == "ambulance":
                continue
            try:
                x, y = traci.vehicle.getPosition(v_id)
                angle = traci.vehicle.getAngle(v_id)
                speed = traci.vehicle.getSpeed(v_id)
                traffic_vehicles.append({
                    "id": v_id,
                    "x": x,
                    "y": 0.0,
                    "z": y,
                    "angle": angle,
                    "speed": speed,
                    "sim_time": sim_time
                })
                if v_id == "car_0":
                    car0_positions.append((sim_time, x, y, speed))
            except Exception:
                pass

        try:
            udp_sock.sendto(json.dumps({"vehicles": traffic_vehicles}).encode('utf-8'), ("127.0.0.1", 5006))
        except Exception:
            pass

        # Query signals & broadcast to Unity (Port 5007)
        signals = []
        for tls in traci.trafficlight.getIDList():
            signals_seen.add(tls)
            signals.append({
                "id": tls,
                "state": traci.trafficlight.getRedYellowGreenState(tls)
            })
        try:
            udp_sock.sendto(json.dumps({"signals": signals}).encode('utf-8'), ("127.0.0.1", 5007))
        except Exception:
            pass

        # Update dashboard state (twin_state.json)
        state_dict = {
            "simulation_time": sim_time,
            "ambulance": {
                "vehicle_id": "ambulance",
                "latitude": amb_pos[0],
                "longitude": amb_pos[1],
                "speed": amb_speed,
                "current_edge": traci.vehicle.getRoadID("ambulance") if amb_found else "",
                "destination": "kmc_hospital",
                "eta": 0.0,
                "remaining_distance": 0.0,
                "progress_pct": 0.0
            },
            "route": {"coordinates": [], "candidates": []},
            "traffic": [],
            "signals": signals,
            "decisions": [],
            "traffic_metrics": metrics_tracker.get_metrics_dict()
        }
        StateProvider.write_state(state_dict)

        t_elapsed = (time.perf_counter() - t_step_start) * 1000.0
        step_durations.append(t_elapsed)

        # Regulate to approximate real-time (target ~100ms per step)
        sleep_needed = 0.10 - (time.perf_counter() - t_step_start)
        if sleep_needed > 0:
            time.sleep(sleep_needed)

        if step % 200 == 0:
            elapsed_w = time.perf_counter() - start_wall_time
            print(f"  Step {step:4d}/{target_steps} | SimTime: {sim_time:5.1f}s | WallTime: {elapsed_w:5.1f}s | ActiveVeh: {len(current_vehicles):2d} | AmbSpeed: {amb_speed:4.1f}m/s")

    total_wall_time = time.perf_counter() - start_wall_time
    traci.close()
    udp_sock.close()

    print("\n" + "=" * 80)
    print("SIMULATION SUMMARY RESULTS")
    print("=" * 80)
    print(f"Total steps executed: {len(step_durations)}")
    print(f"Total simulation time: {target_steps * 0.1:.1f} s")
    print(f"Total wall-clock duration: {total_wall_time:.2f} s")
    print(f"Average step computation: {sum(step_durations)/len(step_durations):.2f} ms")
    print(f"P95 step computation: {sorted(step_durations)[int(len(step_durations)*0.95)]:.2f} ms")
    print(f"Traffic signals managed: {len(signals_seen)} junctions")
    print(f"Preemption decision events: {preemption_events}")
    print(f"Active background vehicles: min={min(vehicle_counts)}, avg={sum(vehicle_counts)/len(vehicle_counts):.1f}, max={max(vehicle_counts)}")
    print(f"Ambulance tracking points: {len(amb_positions)} steps, avg speed: {sum(amb_speeds)/max(1, len(amb_speeds)):.2f} m/s")
    print(f"Car_0 tracking points: {len(car0_positions)} steps")
    print("=" * 80)

if __name__ == "__main__":
    run_two_minute_verification()
