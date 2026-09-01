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
    print("Generating spatially distributed dynamic traffic...")
    import xml.etree.ElementTree as ET
    import random
    import math
    import sumolib
    
    out_file = PROJECT_ROOT / "simulation" / "mangaluru" / "presentation_demo.rou.xml"
    
    # 1. Parse the network
    net = sumolib.net.readNet(str(MANGALURU_NET))
    edges = [e for e in net.getEdges() if e.getFunction() == '' and e.allows('passenger')]
    
    # 2. Setup distribution parameters
    bbox = net.getBBoxXY()
    min_x, min_y = bbox[0]
    max_x, max_y = bbox[1]
    dx = (max_x - min_x) / 4
    dy = (max_y - min_y) / 4
    
    # Ambulance spawn info
    amb_edge = net.getEdge('1096889856')
    amb_shape = amb_edge.getShape()
    amb_cx = sum(p[0] for p in amb_shape) / len(amb_shape)
    amb_cy = sum(p[1] for p in amb_shape) / len(amb_shape)
    
    # Jam route edges to strictly avoid
    jam_route_edges = {'1189020226#3', '-132363066#1', '-132363066#0', '903009071#1'}
    
    def get_edge_center(edge):
        shape = edge.getShape()
        if not shape: return 0, 0
        return sum(p[0] for p in shape) / len(shape), sum(p[1] for p in shape) / len(shape)
    
    valid_trips = []
    v_id = 0
    origins_used = set()
    dests_used = set()
    routes_used = set()
    vehicles_near_amb = 0
    regions_origins = set()
    regions_dests = set()
    
    target_vehicles = 80
    attempts = 0
    
    # 3. Generate distributed random traffic
    while len(valid_trips) < target_vehicles and attempts < 15000:
        attempts += 1
        orig_edge = random.choice(edges)
        dest_edge = random.choice(edges)
        
        if orig_edge == dest_edge:
            continue
            
        orig_cx, orig_cy = get_edge_center(orig_edge)
        dest_cx, dest_cy = get_edge_center(dest_edge)
        
        # Limit spawning near the ambulance (exclusion zone of 250m)
        dist_to_amb = math.hypot(orig_cx - amb_cx, orig_cy - amb_cy)
        if dist_to_amb < 250:
            if random.random() > 0.05: # 95% chance to reject
                continue
                
        # Must have a valid route
        path, cost = net.getShortestPath(orig_edge, dest_edge)
        if path is not None and len(path) > 2:
            path_ids = [e.getID() for e in path]
            
            # STRICTLY avoid jam route edges so we don't interfere with the 4-car scenario
            if any(e_id in jam_route_edges for e_id in path_ids):
                continue
                
            route_str = " ".join(path_ids)
            
            # Reduce duplicated routes to ensure network spread
            if route_str in routes_used and random.random() > 0.1:
                continue
                
            depart_time = round(random.uniform(0.0, 60.0), 1)
            
            veh = ET.Element('trip', id=f'rand_car_{v_id}', type='passenger', depart=str(depart_time), 
                             from_=orig_edge.getID(), to=dest_edge.getID())
            
            valid_trips.append((depart_time, veh))
            
            # Validation metrics
            origins_used.add(orig_edge.getID())
            dests_used.add(dest_edge.getID())
            routes_used.add(route_str)
            if dist_to_amb < 250:
                vehicles_near_amb += 1
                
            col = int((orig_cx - min_x) / dx)
            row = int((orig_cy - min_y) / dy)
            regions_origins.add((col, row))
            
            d_col = int((dest_cx - min_x) / dx)
            d_row = int((dest_cy - min_y) / dy)
            regions_dests.add((d_col, d_row))
            
            v_id += 1

    # Print Validation
    print("\nBACKGROUND TRAFFIC")
    print("-" * 18)
    print(f"Total background vehicles: {len(valid_trips)}")
    print(f"Unique origin edges: {len(origins_used)}")
    print(f"Unique destination edges: {len(dests_used)}")
    print(f"Unique routes: {len(routes_used)}")
    print(f"Spatial regions used: {len(regions_origins)}/16")
    print(f"Vehicles near ambulance spawn: {vehicles_near_amb}")
    depart_times = [v[0] for v in valid_trips]
    hist = [0, 0, 0, 0, 0, 0]
    for d in depart_times:
        idx = min(int(d / 10), 5)
        hist[idx] += 1
    print(f"Departure-time distribution: {hist}\n")
                    
    # 4. Generate deterministic queue vehicles on a shortened approach route (jam_route)
    jam_departs = [115.0, 117.0, 119.0, 121.0, 123.0]
    for i, d in enumerate(jam_departs):
        veh = ET.Element('vehicle', id=f'jam_car_{i}', type='passenger', depart=str(d), route='jam_route')
        valid_trips.append((d, veh))
        
    # 5. AMBULANCE OMITTED - Will be spawned dynamically via API
    
    # 6. Sort and serialize
    valid_trips.sort(key=lambda x: x[0])
    
    new_root = ET.Element('routes')
    ET.SubElement(new_root, 'vType', id='passenger', vClass='passenger', guiShape='passenger', maxSpeed='15.0', color='blue', length='5.0')
    ET.SubElement(new_root, 'vType', id='ambulance', vClass='emergency', guiShape='emergency', speedFactor='1.5', accel='2.5', decel='3.5', color='red', length='7.0', width='2.5')
    ET.SubElement(new_root, 'route', id='jam_route', edges='1189020226#3 -132363066#1 -132363066#0 903009071#1')
    
    for _, veh in valid_trips:
        if 'from_' in veh.attrib:
            veh.set('from', veh.attrib.pop('from_'))
        new_root.append(veh)
        
    tree = ET.ElementTree(new_root)
    tree.write(out_file, encoding='UTF-8', xml_declaration=True)
    print(f"Traffic generation complete. Guaranteed {v_id} spatially distributed background vehicles.")

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
    
    last_tls_states = {}
    last_tls_heartbeat_time = 0
    VEHICLE_VISUALIZATION_RADIUS_M = 500.0
    
    step = 0
    
    # Unity Diagnostics
    packets_sent = 0
    packets_received = 0
    last_packet_received = 0.0
    last_packet_sent = 0.0
    unity_status = "WAITING"
    last_unity_log = 0.0
    
    while traci.simulation.getMinExpectedNumber() > 0 and traci.simulation.getTime() < 3600:
        loop_start = time.time()
        
        traci.simulationStep()
        step += 1
            
        # Run AI signal preemption logic
        ai_decisions = []
        try:
            ai_decisions = ai_controller.process_step()
        except Exception as e:
            import traceback
            traceback.print_exc()
        
        current_vehicles = traci.vehicle.getIDList()
        
        if "ambulance" in current_vehicles and not ambulance_found:
            ambulance_found = True
            print("\n[SUCCESS] Ambulance found!")
            try:
                traci.vehicle.setColor("ambulance", (255, 0, 0, 255))
                traci.vehicle.setWidth("ambulance", 2.5)
                traci.vehicle.setLength("ambulance", 7.0)
            except Exception as e:
                pass
                
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
                
        if ambulance_found:
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
                            poly_id = "ambulance_route_poly"
                            try:
                                if poly_id in traci.polygon.getIDList(): traci.polygon.remove(poly_id)
                                traci.polygon.add(poly_id, sumo_points, (100, 200, 255, 255), fill=False, lineWidth=0.7, layer=200)
                            except: pass
                                
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
            x, y = traci.vehicle.getPosition("ambulance")
            angle = traci.vehicle.getAngle("ambulance")
            speed = traci.vehicle.getSpeed("ambulance")
            payload = {"id": "ambulance", "x": x, "y": 0.0, "z": y, "angle": angle, "speed": speed, "sim_time": traci.simulation.getTime()}
            sock.sendto(json.dumps(payload).encode('utf-8'), (UDP_IP, UDP_PORT))
            packets_sent += 1
            last_packet_sent = time.time()

        # --- TRIP CONTROL API POLLING ---
        if not trip_active:
            cmd = StateProvider.read_trip_command()
            if cmd and cmd.get("action") == "start":
                hospital_id = cmd.get("hospital_id", "highland_hospital")
                hosp = hm.get_hospital(hospital_id)
                
                print(f"\n[TRIP]")
                print(f"Selected hospital: {hosp.name if hosp else 'UNKNOWN'}")
                print(f"Hospital ID: {hospital_id}")
                
                if not hosp or not hosp.nearest_edge:
                    print(f"[ERROR] Destination lookup failed. Hospital {hospital_id} is not reachable on this road network.")
                    print(f"Trip aborted. No substitute hospital will be used.")
                    # Provide feedback to dashboard
                    StateProvider.write_trip_status({"status": "FAILED", "reason": "DESTINATION_UNREACHABLE"})
                    StateProvider.clear_trip_command()
                else:
                    trip_active = True
                    dest_edge = hosp.nearest_edge
                    print(f"Destination edge: {dest_edge}")
                    
                    is_emergency = cmd.get("emergency", True)
                    try:
                        start_edge = cmd.get("start_edge") or "1096889856"
                        print(f"\n[ROUTING]")
                        print(f"Ambulance: ambulance")
                        print(f"Spawn edge: {start_edge}")
                        
                        traci.route.add("dynamic_amb_route", [start_edge, dest_edge])
                        traci.vehicle.add(vehID="ambulance", routeID="dynamic_amb_route", typeID="ambulance", depart="now", departLane="best")
                        
                        if is_emergency:
                            traci.vehicle.setParameter("ambulance", "emergency", "true")
                        else:
                            traci.vehicle.setParameter("ambulance", "emergency", "false")
                            
                        print(f"[SUCCESS] Ambulance successfully spawned. Requesting AI routing sequence.")
                        
                        # Command the AI controller to lock the route via A* immediately
                        ai_controller.set_hospital_destination(hospital_id)
                        
                        # Log actual route
                        assigned_route = traci.vehicle.getRoute("ambulance")
                        print(f"Route length: {len(assigned_route)} edges")
                        print(f"Final edge: {assigned_route[-1]}")
                        
                        StateProvider.write_trip_status({"status": "ACTIVE", "hospital_id": hospital_id})
                    except Exception as e:
                        print(f"[ERROR] Failed to spawn ambulance: {e}")
                        StateProvider.write_trip_status({"status": "FAILED", "reason": str(e)})
                        trip_active = False
                        StateProvider.clear_trip_command()

        # --- Traffic Broadcasting ---
        traffic_vehicles = []
        amb_pos = traci.vehicle.getPosition("ambulance") if "ambulance" in current_vehicles else (0.0, 0.0)
            
        for v_id in current_vehicles:
            if v_id == "ambulance": continue
            x, y = traci.vehicle.getPosition(v_id)
            if "ambulance" in current_vehicles:
                if math.hypot(x - amb_pos[0], y - amb_pos[1]) > VEHICLE_VISUALIZATION_RADIUS_M: continue
            traffic_vehicles.append({"id": v_id, "x": x, "y": 0.0, "z": y, "angle": traci.vehicle.getAngle(v_id), "speed": traci.vehicle.getSpeed(v_id), "sim_time": traci.simulation.getTime()})
        sock.sendto(json.dumps({"vehicles": traffic_vehicles}).encode('utf-8'), (UDP_IP, TRAFFIC_UDP_PORT))
        packets_sent += 1
                
        # --- Traffic Signal Broadcasting ---
        tls_ids = traci.trafficlight.getIDList()
        signals = []
        if time.time() - last_tls_heartbeat_time > 1.5:
            last_tls_heartbeat_time = time.time()
            for tls in tls_ids:
                state = traci.trafficlight.getRedYellowGreenState(tls)
                if last_tls_states.get(tls) != state:
                    signals.append({"id": tls, "state": state})
                    last_tls_states[tls] = state
        if signals:
            sock.sendto(json.dumps({"signals": signals}).encode('utf-8'), (UDP_IP, TLS_UDP_PORT))
            packets_sent += 1
                    
        # --- Telemetry Broadcasting ---
        if ambulance_found:
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
                    "coordinates": route_coords
                },
                "traffic": [],
                "signals": signals,
                "decisions": [
                    {
                        "action": sig_state,
                        "timestamp": traci.simulation.getTime(),
                        "details": f"ETA: {next_junc_eta}s | Q: {queue_len} | Next: {next_junc}"
                    }
                ]
            }
            StateProvider.write_state(state_dict)
                    
        # Real-time synchronization
        elapsed = time.time() - loop_start
        sleep_time = REAL_TIME_STEP - elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)

    traci.close()
    print("Simulation ended.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nBridge stopped by user.")
        try:
            traci.close()
        except:
            pass
