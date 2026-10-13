import sys
import os
import json
import socket
import time
import subprocess
import webbrowser
from datetime import datetime
from pathlib import Path

# Setup pathing
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))
twin_path = str(PROJECT_ROOT / "twin")
sys.path.insert(0, str(PROJECT_ROOT / "controller"))

import traci
from api.state_provider import StateProvider
from controller.hospital_manager import HospitalManager
from traffic_aware_controller import TrafficAwareController
import sumolib

SUMO_CONFIG = PROJECT_ROOT / "simulation" / "mangaluru" / "presentation_demo.sumocfg"
MANGALURU_NET = PROJECT_ROOT / "simulation" / "mangaluru" / "presentation_selection2.net.xml"

# Overrides for AI scripts to use Mangaluru net
import astar_router
import route_evaluator
import junction_detector
astar_router.NETWORK_FILE = MANGALURU_NET
route_evaluator.NETWORK_FILE = MANGALURU_NET
junction_detector.NETWORK_FILE = MANGALURU_NET
route_evaluator._SUMO_NETWORK = None
astar_router._SUMO_NETWORK = None
junction_detector.SUMO_NETWORK = sumolib.net.readNet(str(MANGALURU_NET))

# UDP setup
UDP_IP = "127.0.0.1"
UDP_PORT = 5005
TRAFFIC_UDP_PORT = 5006
TLS_UDP_PORT = 5007
ROUTE_UDP_PORT = 5008

REAL_TIME_STEP = 0.1  # SUMO step length and real-time loop delay (in seconds)

print(f"Starting UDP server, targeting Unity at {UDP_IP}:{UDP_PORT}")
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# Command receiver socket
COMMAND_PORT = 5009
cmd_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
cmd_sock.bind(("0.0.0.0", COMMAND_PORT))
cmd_sock.setblocking(False)
print(f"Listening for commands from Unity on port {COMMAND_PORT}")

# Telemetry broadcast port
TELEMETRY_PORT = 5010

def generate_dynamic_traffic():
    """
    Generate minimal presentation route XML containing vTypes and the jam_route definition.
    Actual background traffic is generated dynamically per round via TraCI.
    """
    import xml.etree.ElementTree as ET
    out_file = PROJECT_ROOT / "simulation" / "mangaluru" / "presentation_demo.rou.xml"
    
    new_root = ET.Element('routes')
    ET.SubElement(new_root, 'vType', id='passenger', vClass='passenger', guiShape='passenger', maxSpeed='15.0', color='blue', length='5.0')
    ET.SubElement(new_root, 'vType', id='ambulance', vClass='emergency', guiShape='emergency', speedFactor='1.5', accel='2.5', decel='3.5', color='red', length='7.0', width='2.5')
    ET.SubElement(new_root, 'route', id='jam_route', edges='1189020226#3 -132363066#1 -132363066#0 903009071#1')
    
    tree = ET.ElementTree(new_root)
    tree.write(out_file, encoding='UTF-8', xml_declaration=True)
    print("Base presentation route definition initialized.")


class TrafficMetricsTracker:
    def __init__(self):
        self.round_id = 0
        self.scenario = "medium"
        self.scheduled_ids = set()
        self.inserted_ids = set()
        self.arrived_ids = set()
        self.removed_count = 0
        self.active_count = 0
        self.waiting_count = 0
        self.mean_speed_kmh = 0.0
        self.edge_speeds = {}
        self.edge_queues = {}
        self.monitored_edges = [
            "1189020226#3", "-132363066#1", "-132363066#0", "903009071#1",
            "26182678#1", "26182678#2", "26182678#3", "26299195#1", "26299195#2"
        ]

    def reset_round(self, round_id: int, scenario: str, scheduled_ids: list[str]):
        self.round_id = round_id
        self.scenario = scenario
        self.scheduled_ids = set(scheduled_ids)
        self.inserted_ids = set()
        self.arrived_ids = set()
        self.removed_count = 0
        self.active_count = 0
        self.waiting_count = 0
        self.mean_speed_kmh = 0.0
        self.edge_speeds = {}
        self.edge_queues = {}

    def record_cleanup(self, count: int):
        self.removed_count += count

    def update_step(self):
        prefix = f"rnd_{self.round_id}_"
        # Check newly departed vehicles
        try:
            departed = traci.simulation.getDepartedIDList()
            for v in departed:
                if v.startswith(prefix):
                    self.inserted_ids.add(v)
        except Exception:
            pass

        # Check newly arrived vehicles
        try:
            arrived = traci.simulation.getArrivedIDList()
            for v in arrived:
                if v.startswith(prefix):
                    self.arrived_ids.add(v)
        except Exception:
            pass

        # Query active vehicles
        try:
            active_vehs = [v for v in traci.vehicle.getIDList() if v.startswith(prefix)]
            self.active_count = len(active_vehs)
            halted = 0
            speeds = []
            for v in active_vehs:
                try:
                    s = traci.vehicle.getSpeed(v)
                    speeds.append(s)
                    if s < 0.1:
                        halted += 1
                except Exception:
                    pass
            self.waiting_count = halted
            self.mean_speed_kmh = round((sum(speeds) / len(speeds)) * 3.6, 1) if speeds else 0.0
        except Exception:
            pass

        # Query monitored edges
        for e in self.monitored_edges:
            try:
                mean_s = traci.edge.getLastStepMeanSpeed(e)
                halt_n = traci.edge.getLastStepHaltingNumber(e)
                self.edge_speeds[e] = round(max(0.0, mean_s * 3.6), 1)
                self.edge_queues[e] = int(halt_n)
            except Exception:
                pass

    def get_metrics_dict(self) -> dict:
        return {
            "round_id": self.round_id,
            "scenario": self.scenario,
            "scheduled": len(self.scheduled_ids),
            "inserted": len(self.inserted_ids),
            "active": self.active_count,
            "arrived": len(self.arrived_ids),
            "removed": self.removed_count,
            "waiting": self.waiting_count,
            "mean_speed_kmh": self.mean_speed_kmh,
            "edge_speeds": self.edge_speeds,
            "edge_queues": self.edge_queues
        }


def generate_round_traffic(round_id: int, current_time: float, scenario: str = "medium", seed: int | None = None) -> list[str]:
    """
    Generate a fresh randomized background traffic scenario for the round via TraCI.
    Supports scenarios: 'low' (~25 veh), 'medium' (~68 veh baseline), 'high' (~110 veh), 'bottleneck' (~74 veh).
    Preserves 4 deterministic queue vehicles on jam_route across all scenarios.
    """
    import random
    import math

    if seed is not None:
        random.seed(seed)

    scenario = (scenario or "medium").lower()
    if scenario not in ["low", "medium", "high", "bottleneck"]:
        scenario = "medium"

    net = junction_detector.SUMO_NETWORK
    edges = [e for e in net.getEdges() if e.getFunction() == '' and e.allows('passenger')]

    amb_edge = net.getEdge('1096889856')
    amb_shape = amb_edge.getShape()
    amb_cx = sum(p[0] for p in amb_shape) / len(amb_shape)
    amb_cy = sum(p[1] for p in amb_shape) / len(amb_shape)

    jam_route_edges = {'1189020226#3', '-132363066#1', '-132363066#0', '903009071#1'}

    def get_edge_center(edge):
        shape = edge.getShape()
        if not shape:
            return 0, 0
        return sum(p[0] for p in shape) / len(shape), sum(p[1] for p in shape) / len(shape)

    scenario_configs = {
        "low": {"random_target": 21, "window": 70.0, "bottleneck_target": 0},
        "medium": {"random_target": 64, "window": 75.0, "bottleneck_target": 0},
        "high": {"random_target": 106, "window": 90.0, "bottleneck_target": 0},
        "bottleneck": {"random_target": 50, "window": 75.0, "bottleneck_target": 20}
    }
    cfg = scenario_configs[scenario]
    target_random = cfg["random_target"]
    window_s = cfg["window"]
    bottleneck_target = cfg["bottleneck_target"]

    scheduled_ids = []
    routes_used = set()
    attempts = 0

    # 1. Spatially distributed background traffic
    while len(scheduled_ids) < target_random and attempts < 6000:
        attempts += 1
        orig_edge = random.choice(edges)
        dest_edge = random.choice(edges)
        if orig_edge == dest_edge:
            continue

        orig_cx, orig_cy = get_edge_center(orig_edge)
        dest_cx, dest_cy = get_edge_center(dest_edge)

        dist_to_amb = math.hypot(orig_cx - amb_cx, orig_cy - amb_cy)
        if dist_to_amb < 250:
            if random.random() > 0.05:
                continue

        path, cost = net.getShortestPath(orig_edge, dest_edge)
        if path is not None and len(path) > 2:
            path_ids = [e.getID() for e in path]
            if any(e_id in jam_route_edges for e_id in path_ids):
                continue

            route_str = " ".join(path_ids)
            if route_str in routes_used and random.random() > 0.1:
                continue

            v_num = len(scheduled_ids)
            route_id = f"rnd_{round_id}_route_{attempts}"
            veh_id = f"rnd_{round_id}_car_{v_num}"
            base_dep = (v_num / max(1, target_random)) * window_s
            jitter = random.uniform(-1.5, 1.5)
            dep_offset = max(0.5, round(base_dep + jitter, 1))
            dep_time = round(current_time + dep_offset, 1)

            try:
                traci.route.add(route_id, path_ids)
                traci.vehicle.add(veh_id, route_id, typeID="passenger", depart=str(dep_time))
                scheduled_ids.append(veh_id)
                routes_used.add(route_str)
            except Exception:
                pass

    # 2. Targeted corridor feeder vehicles for Bottleneck scenario
    if bottleneck_target > 0:
        corridor_edge_ids = [
            '26182678#1', '26182678#2', '26182678#3',
            '26299195#1', '26299195#2', '26299195#3',
            '1055574152#2', '1189020226#1'
        ]
        feeder_edges = [net.getEdge(eid) for eid in corridor_edge_ids if net.hasEdge(eid)]
        b_attempts = 0
        b_added = 0
        while b_added < bottleneck_target and b_attempts < 2000 and feeder_edges:
            b_attempts += 1
            orig_edge = random.choice(feeder_edges)
            dest_edge = random.choice(edges)
            if orig_edge == dest_edge:
                continue
            path, cost = net.getShortestPath(orig_edge, dest_edge)
            if path is not None and len(path) > 1:
                path_ids = [e.getID() for e in path]
                v_num = len(scheduled_ids)
                route_id = f"rnd_{round_id}_broute_{b_attempts}"
                veh_id = f"rnd_{round_id}_car_{v_num}"
                dep_offset = round(5.0 + (b_added / bottleneck_target) * 35.0 + random.uniform(-1.0, 1.0), 1)
                dep_time = round(current_time + max(1.0, dep_offset), 1)
                try:
                    traci.route.add(route_id, path_ids)
                    traci.vehicle.add(veh_id, route_id, typeID="passenger", depart=str(dep_time))
                    scheduled_ids.append(veh_id)
                    b_added += 1
                except Exception:
                    pass

    # 3. 4 Deterministic queue vehicles on jam_route
    jam_departs = [15.0, 17.0, 19.0, 21.0]
    for i, d in enumerate(jam_departs):
        jam_id = f"rnd_{round_id}_jam_{i}"
        jam_time = round(current_time + d, 1)
        try:
            traci.vehicle.add(jam_id, "jam_route", typeID="passenger", depart=str(jam_time))
            scheduled_ids.append(jam_id)
        except Exception:
            pass

    print(f"\n[ROUND_TRAFFIC] Round {round_id} traffic generated ({scenario}): {len(scheduled_ids)} vehicles scheduled (incl. 4 queue).")
    return scheduled_ids


def cleanup_simulation_traffic(scheduled_ids: list[str]) -> int:
    """
    Remove all active and pending vehicles from SUMO and clear Unity representations.
    Returns the count of vehicles successfully removed.
    """
    removed_count = 0
    active_ids = set(traci.vehicle.getIDList())
    for v in active_ids:
        try:
            traci.vehicle.remove(v)
            removed_count += 1
        except Exception:
            pass
    for v in scheduled_ids:
        if v in active_ids:
            continue
        try:
            traci.vehicle.remove(v)
            removed_count += 1
        except Exception:
            pass
    try:
        traci.simulation.clearPending()
    except Exception:
        pass

    # Send empty vehicle list to Unity to clear stale GameObjects
    sock.sendto(json.dumps({"vehicles": []}).encode('utf-8'), (UDP_IP, TRAFFIC_UDP_PORT))
    # Move ambulance underground in Unity
    sock.sendto(
        json.dumps({
            "id": "ambulance",
            "x": 0.0,
            "y": -500.0,
            "z": 0.0,
            "angle": 0.0,
            "speed": 0.0,
            "sim_time": traci.simulation.getTime()
        }).encode('utf-8'),
        (UDP_IP, UDP_PORT)
    )
    return removed_count


def _build_candidate_route_data(candidate_routes, sumo_network):
    """
    Convert ai_controller.candidate_routes into serialisable geometry for the
    dashboard state pipeline.  Uses the already-loaded sumolib network object
    so no additional file I/O is performed.

    Returns a list of dicts, one per candidate route:
        {
            "route_index":  int,     # 0 = selected/primary, 1+ = alternatives
            "selected":     bool,    # True only for index 0
            "edge_ids":     [str],   # SUMO edge ID sequence
            "coordinates":  [[x,y]], # lane-0 shape points for every edge
        }

    Safe to call when candidate_routes is None/empty — returns [].
    """
    if not candidate_routes:
        return []
    result = []
    for idx, astar_route in enumerate(candidate_routes):
        try:
            edge_ids = list(astar_route.edge_ids)
        except Exception:
            continue
        coords = []
        for edge_id in edge_ids:
            try:
                edge = sumo_network.getEdge(edge_id)
                shape = edge.getLanes()[0].getShape()
                for p in shape:
                    coords.append([round(p[0], 1), round(p[1], 1)])
            except Exception:
                pass
        result.append({
            "route_index": idx,
            "selected": idx == 0,
            "edge_ids": edge_ids,
            "coordinates": coords,
        })
    return result

def main():
    print("=" * 60)
    print("STARTING SUMO -> UNITY BRIDGE")
    print("=" * 60)
    
    try:
        generate_dynamic_traffic()
    except Exception as e:
        print(f"Failed to generate dynamic traffic: {e}")

    sumo_cmd = "sumo-gui" if "--gui" in sys.argv else "sumo"
    traci.start([
        sumo_cmd,
        "-c", str(SUMO_CONFIG),
        "--step-length", str(REAL_TIME_STEP),
        "--random",
        "--ignore-route-errors",
        "--quit-on-end",
        "--start"
    ])
    
    if "--gui" in sys.argv:
        try:
            view_id = traci.gui.DEFAULT_VIEW
            traci.gui.setBoundary(view_id, 1867.0, 1166.0, 2742.0, 1869.0)
            traci.gui.setSchema(view_id, "real world")
            print("SUMO-GUI Viewport focused on Kankanady corridor.")
        except Exception as e:
            print(f"Warning: Could not configure GUI viewport: {e}")

    StateProvider.clear_trip_command()
    print("Initializing AI Controller...")
    ai_controller = TrafficAwareController()
    import config
    hm = HospitalManager(
        str(config.NET_FILE), 
        str(config.HOSPITALS_FILE)
    )
    
    # Start the FastAPI Dashboard
    print("[SYSTEM] Starting Web Dashboard API on port 8000...")
    api_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "api.main:app", "--port", "8000"],
        cwd=str(PROJECT_ROOT)
    )
    import atexit
    atexit.register(lambda: api_proc.poll() is None and api_proc.terminate())
    time.sleep(2) # Give it a second to start
    
    print("[SYSTEM] Opening Web Dashboard in Browser...")
    try:
        webbrowser.open("http://localhost:8000/dashboard")
    except Exception as e:
        print(f"[SYSTEM] Could not open browser: {e}")
        
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Entering simulation loop...")
    trip_active = False

    ambulance_found = False
    current_route_hash = None

    # Pending hospital init: set_hospital_destination() cannot be called in the
    # same simulation step as traci.vehicle.add() because SUMO only materialises
    # the vehicle on the NEXT step (depart="now" means "next step", not instant).
    # Store the hospital ID here and consume it one step later.
    pending_hospital_id = None

    last_tls_states = {}
    last_tls_heartbeat_time = 0
    VEHICLE_VISUALIZATION_RADIUS_M = 500.0

    step = 0

    # Hash of last drawn SUMO candidate polygons — only redraw when routes change.
    last_candidate_hash = None
    
    # Unity Diagnostics
    packets_sent = 0
    packets_received = 0
    last_packet_received = 0.0
    last_packet_sent = 0.0
    unity_status = "WAITING"
    last_unity_log = 0.0
    
    # Initialize background traffic for round 0
    traffic_metrics_tracker = TrafficMetricsTracker()
    active_scheduled_ids = generate_round_traffic(round_id=0, current_time=0.0)
    traffic_metrics_tracker.reset_round(round_id=0, scenario="medium", scheduled_ids=active_scheduled_ids)
    round_counter = 0

    while traci.simulation.getMinExpectedNumber() > 0 and traci.simulation.getTime() < 3600:
        loop_start = time.time()
        
        traci.simulationStep()
        step += 1
        traffic_metrics_tracker.update_step()
            
        # Run AI signal preemption logic
        ai_decisions = []
        try:
            ai_decisions = ai_controller.process_step()
        except Exception as e:
            import traceback
            traceback.print_exc()
        
        current_vehicles = traci.vehicle.getIDList()

        # --- DEFERRED HOSPITAL INIT (one step after vehicle.add) ---
        # Now that simulationStep() has run, the ambulance is physically present.
        # Call set_hospital_destination() here so getRoadID/getSpeed/getLanePosition
        # work correctly and A* receives a valid start edge.
        if pending_hospital_id is not None and "ambulance" in current_vehicles:
            print(f"[ROUTING] Ambulance confirmed in simulation. Initialising A* route to {pending_hospital_id}.")
            init_ok = ai_controller.set_hospital_destination(pending_hospital_id)
            if init_ok:
                try:
                    assigned_route = traci.vehicle.getRoute("ambulance")
                    print(f"[ROUTING] Route length: {len(assigned_route)} edges | Final edge: {assigned_route[-1]}")
                    candidate_count = len(ai_controller.candidate_routes)
                    print(f"[ROUTING] Candidate routes stored: {candidate_count}")
                except Exception:
                    pass
            else:
                print(f"[ROUTING] set_hospital_destination returned False for {pending_hospital_id}. Ambulance will follow temporary spawn route.")
            StateProvider.write_trip_status({"status": "ACTIVE", "hospital_id": pending_hospital_id})
            pending_hospital_id = None

        if "ambulance" in current_vehicles and not ambulance_found:
            ambulance_found = True
            print("\n[SUCCESS] Ambulance found!")
            try:
                traci.vehicle.setColor("ambulance", (255, 0, 0, 255))
                traci.vehicle.setWidth("ambulance", 2.5)
                traci.vehicle.setLength("ambulance", 7.0)
            except Exception:
                pass
        elif ambulance_found and "ambulance" not in current_vehicles and pending_hospital_id is None:
            print("\n[INFO] Ambulance reached destination and exited simulation. Trip completed.")
            ambulance_found = False
            trip_active = False
            current_route_hash = None
            ai_controller.shutdown()
            sock.sendto(json.dumps({"id": "ambulance", "x": 0.0, "y": -500.0, "z": 0.0, "angle": 0.0, "speed": 0.0, "sim_time": traci.simulation.getTime()}).encode('utf-8'), (UDP_IP, UDP_PORT))
            try:
                if "ambulance_route_poly" in traci.polygon.getIDList():
                    traci.polygon.remove("ambulance_route_poly")
                for pid in traci.polygon.getIDList():
                    if pid.startswith("candidate_route_poly_"):
                        traci.polygon.remove(pid)
            except Exception:
                pass
            StateProvider.write_trip_status({"status": "COMPLETED"})
                
        # --- NEW: Process Incoming UDP Commands from Unity ---
        try:
            while True:
                data, addr = cmd_sock.recvfrom(1024)
                packets_received += 1
                last_packet_received = time.time()
                try:
                    cmd = json.loads(data.decode('utf-8'))
                    # set_hospital removed: it is now handled by the dashboard via StateProvider
                except json.JSONDecodeError:
                    pass
        except BlockingIOError:
            pass 
        except Exception as e:
            if type(e).__name__ != 'BlockingIOError':
                # Windows might throw other non-blocking errors
                pass
                
        # Update Unity Status
        current_time = time.time()
        if current_time - last_packet_received < 5.0 and packets_received > 0:
            unity_status = "CONNECTED"
        else:
            unity_status = "DISCONNECTED"
            
        if current_time - last_unity_log > 10.0:
            print(f"\n[UNITY] Status: {unity_status} | Packets Sent: {packets_sent} | Packets Received: {packets_received}")
            last_unity_log = current_time
                
        if ambulance_found and "ambulance" in current_vehicles:
            try:
                current_route = traci.vehicle.getRoute("ambulance")
                route_hash = hash(tuple(current_route))
                if route_hash != current_route_hash:
                    current_route_hash = route_hash
                    points = []
                    sumo_points = []
                    for edge_id in current_route:
                        try:
                            edge = junction_detector.SUMO_NETWORK.getEdge(edge_id)
                            shape = edge.getLanes()[0].getShape()
                            for p in shape:
                                points.append({"x": round(p[0], 1), "z": round(p[1], 1)})
                                sumo_points.append(p)
                        except Exception: pass
                            
                    if sumo_points:
                        if "--gui" in sys.argv:
                            # --- BLUE: selected/primary route ---
                            poly_id = "ambulance_route_poly"
                            try:
                                if poly_id in traci.polygon.getIDList(): traci.polygon.remove(poly_id)
                                traci.polygon.add(poly_id, sumo_points, (100, 200, 255, 255), fill=False, lineWidth=0.7, layer=200)
                            except: pass

                            # --- RED: alternative candidate routes ---
                            # Only redraw when the candidate set itself changes.
                            cand_routes = getattr(ai_controller, 'candidate_routes', None) or []
                            cand_hash = hash(tuple(
                                tuple(r.edge_ids) for r in cand_routes
                            ))
                            if cand_hash != last_candidate_hash:
                                last_candidate_hash = cand_hash
                                # Remove old red polygons
                                existing_polys = traci.polygon.getIDList()
                                for old_id in existing_polys:
                                    if old_id.startswith("candidate_route_poly_"):
                                        try: traci.polygon.remove(old_id)
                                        except: pass
                                # Draw new red polygons for alternatives (indices 1+)
                                for alt_idx, alt_route in enumerate(cand_routes[1:], start=1):
                                    alt_points = []
                                    try:
                                        for eid in alt_route.edge_ids:
                                            try:
                                                edge = junction_detector.SUMO_NETWORK.getEdge(eid)
                                                alt_points.extend(edge.getLanes()[0].getShape())
                                            except: pass
                                        if alt_points:
                                            alt_poly_id = f"candidate_route_poly_{alt_idx}"
                                            traci.polygon.add(
                                                alt_poly_id, alt_points,
                                                (255, 60, 60, 200),  # RED, semi-transparent
                                                fill=False, lineWidth=0.5, layer=199
                                            )
                                    except: pass

                        # Unity route_chunk UDP: send ONLY the primary (selected) route.
                        # Candidate alternative routes must NOT be sent to Unity.
                        CHUNK_SIZE = 500
                        import math
                        total_chunks = math.ceil(len(points) / CHUNK_SIZE)
                        for i in range(total_chunks):
                            chunk_payload = {"type": "route_chunk", "chunk_index": i, "total_chunks": total_chunks, "points": points[i*CHUNK_SIZE : (i+1)*CHUNK_SIZE]}
                            sock.sendto(json.dumps(chunk_payload).encode('utf-8'), (UDP_IP, ROUTE_UDP_PORT))
                            packets_sent += 1
                            last_packet_sent = time.time()
            except traci.TraCIException: pass

        if "ambulance" in current_vehicles:
            try:
                x, y = traci.vehicle.getPosition("ambulance")
                angle = traci.vehicle.getAngle("ambulance")
                speed = traci.vehicle.getSpeed("ambulance")
                payload = {"id": "ambulance", "x": x, "y": 0.0, "z": y, "angle": angle, "speed": speed, "sim_time": traci.simulation.getTime()}
                sock.sendto(json.dumps(payload).encode('utf-8'), (UDP_IP, UDP_PORT))
                packets_sent += 1
                last_packet_sent = time.time()
            except traci.TraCIException:
                pass

        # --- TRIP CONTROL API POLLING ---
        cmd = StateProvider.read_trip_command()
        if trip_active and cmd and cmd.get("action") == "stop":
            print("\n[INFO] Stop trip command received. Removing ambulance and restoring signals.")
            trip_active = False
            ambulance_found = False
            pending_hospital_id = None
            if "ambulance" in current_vehicles:
                try:
                    traci.vehicle.remove("ambulance")
                except:
                    pass
            ai_controller.shutdown()
            sock.sendto(json.dumps({"id": "ambulance", "x": 0.0, "y": -500.0, "z": 0.0, "angle": 0.0, "speed": 0.0, "sim_time": traci.simulation.getTime()}).encode('utf-8'), (UDP_IP, UDP_PORT))
            try:
                if "ambulance_route_poly" in traci.polygon.getIDList():
                    traci.polygon.remove("ambulance_route_poly")
                for pid in traci.polygon.getIDList():
                    if pid.startswith("candidate_route_poly_"):
                        traci.polygon.remove(pid)
            except Exception:
                pass
            StateProvider.write_trip_status({"status": "STOPPED"})
            StateProvider.clear_trip_command()
        elif cmd and cmd.get("action") == "set_mode":
            is_emergency = bool(cmd.get("emergency", False))
            print(f"\n[INFO] Mode switch command received. Setting Emergency Mode to {is_emergency}.")
            if "ambulance" in current_vehicles:
                try:
                    traci.vehicle.setParameter("ambulance", "emergency", "true" if is_emergency else "false")
                except Exception as e:
                    print(f"Warning: could not set ambulance emergency parameter: {e}")
            if not is_emergency:
                ai_controller.signal_controller.restore_all()
                ai_controller.active_movements.clear()
            StateProvider.clear_trip_command()
        elif not trip_active and cmd and cmd.get("action") == "start":
            hospital_id = cmd.get("hospital_id", "highland_hospital")
            hosp = hm.get_hospital(hospital_id)
            
            print(f"\n[TRIP]")
            print(f"Selected hospital: {hosp.name if hosp else 'UNKNOWN'}")
            print(f"Hospital ID: {hospital_id}")
            
            if not hosp or not hosp.nearest_edge:
                print(f"[ERROR] Destination lookup failed. Hospital {hospital_id} is not reachable on this road network.")
                print(f"Trip aborted. No substitute hospital will be used.")
                StateProvider.write_trip_status({"status": "FAILED", "reason": "DESTINATION_UNREACHABLE"})
                StateProvider.clear_trip_command()
            else:
                dest_edge = hosp.nearest_edge
                print(f"Destination edge: {dest_edge}")
                
                is_emergency = bool(cmd.get("emergency", False))
                try:
                    req_start_edge = cmd.get("start_edge")
                    if not req_start_edge:
                        start_edge = "1096889856"
                    else:
                        start_edge = str(req_start_edge)
                        
                    valid_start_edges = ["-26209727#1", "1213225868", "-1154699531", "1096889856"]
                    if start_edge not in valid_start_edges:
                        raise ValueError(f"Invalid start_edge: {start_edge}")
                        
                    traffic_scenario = cmd.get("traffic_scenario", "medium")
                    # 1. Clear previous round background traffic & state
                    removed = cleanup_simulation_traffic(active_scheduled_ids)
                    traffic_metrics_tracker.record_cleanup(removed)
                    ai_controller.shutdown()
                    try:
                        if "ambulance_route_poly" in traci.polygon.getIDList():
                            traci.polygon.remove("ambulance_route_poly")
                        for pid in traci.polygon.getIDList():
                            if pid.startswith("candidate_route_poly_"):
                                traci.polygon.remove(pid)
                    except Exception:
                        pass

                    # 2. Increment round counter and generate fresh randomized traffic
                    round_counter += 1
                    cur_sim_time = traci.simulation.getTime()
                    active_scheduled_ids = generate_round_traffic(round_counter, cur_sim_time, scenario=traffic_scenario)
                    traffic_metrics_tracker.reset_round(round_counter, traffic_scenario, active_scheduled_ids)

                    # 3. Spawn the new ambulance
                    trip_active = True
                    print(f"\n[ROUTING]")
                    print(f"Ambulance: ambulance")
                    print(f"Spawn edge: {start_edge}")
                    print(f"Emergency Priority: {is_emergency}")
                    
                    spawn_route_id = f"dynamic_amb_route_{round_counter}_{step}"
                    traci.route.add(spawn_route_id, [start_edge, dest_edge])
                    traci.vehicle.add(vehID="ambulance", routeID=spawn_route_id, typeID="ambulance", depart="now", departLane="best")
                    
                    if is_emergency:
                        traci.vehicle.setParameter("ambulance", "emergency", "true")
                    else:
                        traci.vehicle.setParameter("ambulance", "emergency", "false")
                        
                    print(f"[SUCCESS] Ambulance queued for next simulation step. A* init deferred.")

                    pending_hospital_id = hospital_id

                    StateProvider.write_trip_status({"status": "ACTIVE", "hospital_id": hospital_id, "emergency": is_emergency})
                    StateProvider.clear_trip_command()
                except Exception as e:
                    print(f"[ERROR] Failed to spawn ambulance: {e}")
                    StateProvider.write_trip_status({"status": "FAILED", "reason": str(e)})
                    trip_active = False
                    pending_hospital_id = None
                    StateProvider.clear_trip_command()

        # --- Traffic Broadcasting ---
        traffic_vehicles = []
        current_vehicles = list(traci.vehicle.getIDList())
        amb_pos = (0.0, 0.0)
        if "ambulance" in current_vehicles:
            try:
                amb_pos = traci.vehicle.getPosition("ambulance")
            except traci.TraCIException:
                pass
            
        for v_id in current_vehicles:
            if v_id == "ambulance":
                continue
            try:
                x, y = traci.vehicle.getPosition(v_id)
                if "ambulance" in current_vehicles:
                    if math.hypot(x - amb_pos[0], y - amb_pos[1]) > VEHICLE_VISUALIZATION_RADIUS_M:
                        continue
                angle = traci.vehicle.getAngle(v_id)
                speed = traci.vehicle.getSpeed(v_id)
                traffic_vehicles.append({"id": v_id, "x": x, "y": 0.0, "z": y, "angle": angle, "speed": speed, "sim_time": traci.simulation.getTime()})
            except traci.TraCIException:
                continue
        sock.sendto(json.dumps({"vehicles": traffic_vehicles}).encode('utf-8'), (UDP_IP, TRAFFIC_UDP_PORT))
        packets_sent += 1
                
        # --- Traffic Signal Broadcasting ---
        tls_ids = traci.trafficlight.getIDList()
        signals = []
        is_tls_heartbeat = (time.time() - last_tls_heartbeat_time > 2.0)
        if is_tls_heartbeat:
            last_tls_heartbeat_time = time.time()

        for tls in tls_ids:
            state = traci.trafficlight.getRedYellowGreenState(tls)
            if is_tls_heartbeat or last_tls_states.get(tls) != state:
                signals.append({"id": tls, "state": state})
                last_tls_states[tls] = state

        if signals:
            sock.sendto(json.dumps({"signals": signals}).encode('utf-8'), (UDP_IP, TLS_UDP_PORT))
            packets_sent += 1
                    
        # --- Telemetry Broadcasting ---
        if ambulance_found and "ambulance" in current_vehicles:
            next_junc, next_junc_eta, traffic_cond, queue_len, sig_state, light_color = "None", 0.0, "LOW", 0, "NORMAL", "UNKNOWN"
            if ai_decisions:
                features, decision = ai_decisions[0]
                next_junc = features.junction_id
                next_junc_eta = features.ambulance_eta_s
                queue_len = features.halted_vehicle_count
                
                if decision.should_preempt:
                    sig_state = "PREEMPTING"
                
                try:
                    if next_junc in traci.trafficlight.getIDList():
                        state_str = traci.trafficlight.getRedYellowGreenState(next_junc).lower()
                        if 'g' in state_str: light_color = "GREEN"
                        elif 'y' in state_str: light_color = "YELLOW"
                        elif 'r' in state_str: light_color = "RED"
                except: pass

            telemetry = {
                "hospital": ai_controller.destination_hospital.id if ai_controller.destination_hospital else "None",
                "overall_eta": next_junc_eta,
                "next_junction": next_junc,
                "next_eta": next_junc_eta,
                "traffic_condition": traffic_cond,
                "queue_length": queue_len,
                "emergency_control": sig_state,
                "signal_color": light_color,
                "route_type": "FIXED_A_STAR"
            }
            try:
                sock.sendto(json.dumps(telemetry).encode('utf-8'), (UDP_IP, TELEMETRY_UDP_PORT))
                packets_sent += 1
            except: pass
            
            # --- Write State to IPC for Dashboard ---
            remaining_distance = 0.0
            total_eta = 0.0
            progress_pct = 0.0
            route_coords = []
            amb_lat, amb_lon = 0.0, 0.0
            if "ambulance" in current_vehicles:
                try:
                    route = traci.vehicle.getRoute("ambulance")
                    idx = traci.vehicle.getRouteIndex("ambulance")
                    for e in route[idx:]:
                        try:
                            remaining_distance += traci.lane.getLength(e + "_0")
                        except: pass
                    remaining_distance -= traci.vehicle.getLanePosition("ambulance")
                    remaining_distance = max(0.0, remaining_distance)
                    
                    if not hasattr(StateProvider, 'initial_route_length') or StateProvider.initial_route_length == 0:
                        total_len = 0.0
                        for e in route:
                            try:
                                total_len += traci.lane.getLength(e + "_0")
                            except: pass
                        StateProvider.initial_route_length = total_len
                        
                    if hasattr(StateProvider, 'initial_route_length') and StateProvider.initial_route_length > 0:
                        progress_pct = max(0.0, min(100.0, 100.0 * (1.0 - (remaining_distance / StateProvider.initial_route_length))))
                    
                    current_speed = traci.vehicle.getSpeed("ambulance")
                    avg_speed = max(current_speed, 10.0)
                    total_eta = remaining_distance / avg_speed
                    
                    # Keep Route in SUMO coords
                    for e in route:
                        try:
                            shape = traci.lane.getShape(e + "_0")
                            for point in shape:
                                route_coords.append([point[0], point[1]])
                        except: pass
                        
                    # Keep Ambulance pos in SUMO coords
                    amb_lat, amb_lon = amb_pos[0], amb_pos[1]
                except Exception as e:
                    pass

            state_dict = {
                "simulation_time": traci.simulation.getTime(),
                "ambulance": {
                    "vehicle_id": "ambulance",
                    "latitude": amb_lat,
                    "longitude": amb_lon,
                    "speed": speed if "ambulance" in current_vehicles else 0.0,
                    "current_edge": traci.vehicle.getRoadID("ambulance") if "ambulance" in current_vehicles else "",
                    "current_route": "",
                    "destination": telemetry["hospital"],
                    "eta": total_eta,
                    "remaining_distance": remaining_distance,
                    "progress_pct": progress_pct
                },
                "route": {
                    # Primary selected route geometry (ambulance actively follows this).
                    "coordinates": route_coords,
                    # Candidate routes: index 0 = selected (same as coordinates above),
                    # index 1+ = alternatives for dashboard visualisation only.
                    # Empty list when no trip is active or routes are not yet generated.
                    "candidates": _build_candidate_route_data(
                        getattr(ai_controller, 'candidate_routes', None),
                        junction_detector.SUMO_NETWORK
                    ),
                },
                "traffic": [],
                "signals": signals,
                "decisions": [
                    {
                        "action": sig_state,
                        "timestamp": traci.simulation.getTime(),
                        "details": f"ETA: {next_junc_eta}s | Q: {queue_len} | Next: {next_junc}"
                    }
                ],
                "traffic_metrics": traffic_metrics_tracker.get_metrics_dict()
            }
            StateProvider.write_state(state_dict)
        elif step % 10 == 0:
            # Periodic state broadcast when ambulance is not yet active
            idle_state = {
                "simulation_time": traci.simulation.getTime(),
                "ambulance": None,
                "route": {"coordinates": [], "candidates": []},
                "traffic": [],
                "signals": signals if 'signals' in locals() else [],
                "decisions": [],
                "traffic_metrics": traffic_metrics_tracker.get_metrics_dict()
            }
            StateProvider.write_state(idle_state)
                    
        # Real-time synchronization
        elapsed = time.time() - loop_start
        sleep_time = REAL_TIME_STEP - elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)

    try:
        traci.close()
    except Exception:
        pass
    if api_proc and api_proc.poll() is None:
        try:
            api_proc.terminate()
        except Exception:
            pass
    print("Simulation ended.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nBridge stopped by user.")
        try:
            traci.close()
        except Exception:
            pass
