import sys
import os
import json
import socket
import time
from pathlib import Path
import traci

# Setup pathing
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "controller"))

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
    
    target_vehicles = 68
    attempts = 0
    
    # 3. Generate distributed random traffic
    while len(valid_trips) < target_vehicles and attempts < 4000:
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
    jam_departs = [115.0, 117.0, 119.0, 121.0]
    for i, d in enumerate(jam_departs):
        veh = ET.Element('vehicle', id=f'jam_car_{i}', type='passenger', depart=str(d), route='jam_route')
        valid_trips.append((d, veh))
        
    # 5. Generate the ambulance
    amb_veh = ET.Element('vehicle', id='ambulance', type='ambulance', depart='45.0', route='amb_route', departLane='best')
    ET.SubElement(amb_veh, 'param', key='emergency', value='true')
    valid_trips.append((45.0, amb_veh))
    
    # 6. Sort and serialize
    valid_trips.sort(key=lambda x: x[0])
    
    new_root = ET.Element('routes')
    ET.SubElement(new_root, 'vType', id='passenger', vClass='passenger', guiShape='passenger', maxSpeed='15.0', color='blue', length='5.0')
    ET.SubElement(new_root, 'vType', id='ambulance', vClass='emergency', guiShape='emergency', speedFactor='1.5', accel='2.5', decel='3.5', color='red', length='7.0', width='2.5')
    ET.SubElement(new_root, 'route', id='amb_route', edges='1096889856 -1096889856 -184750315#1 -184750315#0 1055574152#1 1055574152#2 26182678#1 26182678#2 26182678#3 26299204#0 1189020226#1 1189020226#2 1189020226#3 -132363066#1 -132363066#0 903009071#1')
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
        # Task 1: Setup SUMO-GUI Viewport
        try:
            view_id = traci.gui.DEFAULT_VIEW
            # Bounding box of the Kankanady route + margin
            traci.gui.setBoundary(view_id, 1867.0, 1166.0, 2742.0, 1869.0)
            traci.gui.setSchema(view_id, "real world")
            print("SUMO-GUI Viewport focused on Kankanady corridor.")
        except Exception as e:
            print(f"Warning: Could not configure GUI viewport: {e}")

    print("Initializing AI Controller...")
    ai_controller = TrafficAwareController()
    
    print("Using native SUMO traffic definitions from kankanady_demo.rou.xml")

    # Force Kankanady to stay red for the approach to guarantee a traffic queue builds up
    # (Removed as per new requirements to allow natural traffic flow)
    kankanady_tls = "joinedS_11152279217_cluster_11151324665_3610155471"

    ambulance_found = False
    current_route_hash = None
    
    print("Waiting for ambulance to spawn...")
    
    last_tls_states = {}
    last_tls_heartbeat_time = 0
    VEHICLE_VISUALIZATION_RADIUS_M = 500.0
    
    step = 0
    while traci.simulation.getMinExpectedNumber() > 0 and traci.simulation.getTime() < 120:
        loop_start = time.time()
        
        traci.simulationStep()
        step += 1
        
        # No need to purge traffic manually, kankanady_demo.rou.xml is already lightweight
        
        # Run AI signal preemption logic
        ai_decisions = []
        try:
            ai_decisions = ai_controller.process_step()
        except Exception as e:
            import traceback
            traceback.print_exc()
            pass # Ignore AI errors to keep bridge running
            
        current_vehicles = traci.vehicle.getIDList()
        
        if "ambulance" in current_vehicles and not ambulance_found:
            ambulance_found = True
            print("\n[SUCCESS] Ambulance found!")
            try:
                # Task 2: Make the ambulance visually RED in SUMO-GUI
                traci.vehicle.setColor("ambulance", (255, 0, 0, 255))
                # Optional: Make it slightly larger so it's easier to see on a zoomed-out map
                traci.vehicle.setWidth("ambulance", 2.5)
                traci.vehicle.setLength("ambulance", 7.0)
            except Exception as e:
                pass

            try:
                # Default hospital until Unity sends one
                print("Setting default hospital destination to KMC Hospital...")
                ai_controller.set_hospital_destination("kmc_hospital")
            except Exception as e:
                print(f"Error setting hospital destination: {e}")
                
        # --- NEW: Process Incoming UDP Commands from Unity ---
        try:
            while True:
                data, addr = cmd_sock.recvfrom(1024)
                try:
                    cmd = json.loads(data.decode('utf-8'))
                    if cmd.get("type") == "set_hospital":
                        hospital_id = cmd.get("hospital_id")
                        print(f"\n[COMMAND] Received hospital selection from Unity: {hospital_id}")
                        if ambulance_found:
                            ai_controller.set_hospital_destination(hospital_id)
                            # Force route hash to trigger a redraw in Unity immediately
                            current_route_hash = None
                            print(f"[COMMAND] Ambulance rerouting to {hospital_id}...")
                except json.JSONDecodeError:
                    pass
        except BlockingIOError:
            pass # No commands pending
                
        if ambulance_found:
            # Route visualization tracking
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
                        except Exception:
                            pass
                            
                    if sumo_points:
                        # Draw in SUMO
                        if "--gui" in sys.argv:
                            poly_id = "ambulance_route_poly"
                            try:
                                if poly_id in traci.polygon.getIDList():
                                    traci.polygon.remove(poly_id)
                                # Light blue line overlay
                                traci.polygon.add(poly_id, sumo_points, (100, 200, 255, 255), fill=False, lineWidth=0.7, layer=200)
                            except Exception as e:
                                print(f"Warning: Could not draw route polygon: {e}")
                                
                        # Broadcast to Unity (Chunked if necessary)
                        CHUNK_SIZE = 500
                        import math
                        total_chunks = math.ceil(len(points) / CHUNK_SIZE)
                        
                        if total_chunks <= 1:
                            route_payload = {"type": "route", "points": points}
                            route_message = json.dumps(route_payload).encode('utf-8')
                            if len(route_message) < 60000:
                                sock.sendto(route_message, (UDP_IP, ROUTE_UDP_PORT))
                        else:
                            for i in range(total_chunks):
                                chunk_points = points[i*CHUNK_SIZE : (i+1)*CHUNK_SIZE]
                                chunk_payload = {
                                    "type": "route_chunk",
                                    "chunk_index": i,
                                    "total_chunks": total_chunks,
                                    "points": chunk_points
                                }
                                chunk_message = json.dumps(chunk_payload).encode('utf-8')
                                sock.sendto(chunk_message, (UDP_IP, ROUTE_UDP_PORT))
                                
                        print(f"[ROUTE VISUALIZATION] Updated. Sent {len(points)} points in {total_chunks} chunks.")
            except traci.TraCIException:
                pass

        if "ambulance" in current_vehicles:
            # Extract real SUMO coordinates (2D)
            x, y = traci.vehicle.getPosition("ambulance")
            angle = traci.vehicle.getAngle("ambulance")
            speed = traci.vehicle.getSpeed("ambulance")
            
            # Coordinate Conversion Logic:
            # SUMO is a 2D Cartesian plane (X, Y).
            # Unity is a 3D Left-Handed system (X, Y, Z) where Y is up.
            # 
            # 1. Unity.X = SUMO.X
            # 2. Unity.Y = 0 (Ground plane)
            # 3. Unity.Z = SUMO.Y
            # 
            # Rotation: SUMO 0 degrees = North. Unity Z = Forward (North).
            # So Unity.Rotation.Y = SUMO.Angle
            
            unity_x = x
            unity_y = 0.0
            unity_z = y
            unity_angle = angle
            
            # Create the payload
            payload = {
                "id": "ambulance",
                "x": unity_x,
                "y": unity_y,
                "z": unity_z,
                "angle": unity_angle,
                "speed": speed,
                "sim_time": traci.simulation.getTime()
            }
            
            # Send to Unity
            message = json.dumps(payload).encode('utf-8')
            sock.sendto(message, (UDP_IP, UDP_PORT))
            
            # Print for validation (throttle printing to avoid spam)
            if step % 10 == 0:
                print(f"Time {traci.simulation.getTime():6.1f} | SUMO(X:{x:8.2f}, Y:{y:8.2f}, Ang:{angle:6.1f}) -> Unity(X:{unity_x:8.2f}, Z:{unity_z:8.2f}, RotY:{unity_angle:6.1f})")

        # --- NEW: Traffic Broadcasting ---
        traffic_vehicles = []
        amb_x, amb_y = 0.0, 0.0
        if "ambulance" in current_vehicles:
            amb_x, amb_y = traci.vehicle.getPosition("ambulance")
            
        for v_id in current_vehicles:
            if v_id == "ambulance":
                continue
                
            x, y = traci.vehicle.getPosition(v_id)
            
            # Spatial filter: only send vehicles within radius
            if "ambulance" in current_vehicles:
                import math
                dist = math.hypot(x - amb_x, y - amb_y)
                if dist > VEHICLE_VISUALIZATION_RADIUS_M:
                    continue
            
            angle = traci.vehicle.getAngle(v_id)
            speed = traci.vehicle.getSpeed(v_id)
            
            # COORDINATE MAPPING VERIFICATION
            # SUMO 2D (X, Y) -> Unity 3D (X, 0, Z). SUMO Angle -> Unity RotY
            traffic_vehicles.append({
                "id": v_id,
                "x": x,
                "y": 0.0,
                "z": y,
                "angle": angle,
                "speed": speed,
                "sim_time": traci.simulation.getTime()
            })
            
        traffic_payload = {"vehicles": traffic_vehicles}
        traffic_message = json.dumps(traffic_payload).encode('utf-8')
            
        try:
            sock.sendto(traffic_message, (UDP_IP, TRAFFIC_UDP_PORT))
        except OSError as e:
            print(f"UDP send error (packet too large? size: {len(traffic_message)}): {e}")
                
        # --- NEW: Traffic Signal Broadcasting ---
        tls_ids = traci.trafficlight.getIDList()
        signals = []
        current_time = time.time()
        
        # We want a heartbeat every 1.5 seconds for UDP reliability
        heartbeat = False
        if current_time - last_tls_heartbeat_time > 1.5:
            heartbeat = True
            last_tls_heartbeat_time = current_time

        for tls in tls_ids:
            state = traci.trafficlight.getRedYellowGreenState(tls)
            # Delta sync: only send if state changed or heartbeat reached
            if heartbeat or last_tls_states.get(tls) != state:
                signals.append({"id": tls, "state": state})
                last_tls_states[tls] = state
            
        if len(signals) > 0:
            # Chunk the signals to avoid exceeding UDP packet size limits
            chunk_size = 50
            for i in range(0, len(signals), chunk_size):
                chunk = signals[i:i + chunk_size]
                tls_payload = {"signals": chunk}
                tls_message = json.dumps(tls_payload).encode('utf-8')
                try:
                    sock.sendto(tls_message, (UDP_IP, TLS_UDP_PORT))
                except OSError as e:
                    print(f"UDP send error TLS (size: {len(tls_message)}): {e}")
                    
        # --- NEW: Telemetry Broadcasting for Dashboard (Phase 5/6) ---
        if ambulance_found:
            rc = ai_controller.get_rerouting_controller("ambulance")
            status = rc.get_status()
            
            # Extract first decision if available
            next_junc = "None"
            next_junc_eta = 0.0
            traffic_cond = "LOW"
            queue_len = 0
            sig_state = "NORMAL"
            light_color = "UNKNOWN"
            
            if ai_decisions and len(ai_decisions) > 0:
                features, decision = ai_decisions[0]
                next_junc = features.junction_id
                next_junc_eta = features.ambulance_eta_s
                queue_len = features.halted_vehicle_count
                
                if queue_len > 10:
                    traffic_cond = "HIGH"
                elif queue_len > 3:
                    traffic_cond = "MODERATE"
                else:
                    traffic_cond = "LOW"
                    
                if decision.should_preempt:
                    sig_state = "PREEMPTING"
                    # Log the exact string required by the user
                    print(f"[PREEMPTION_EVALUATION] High queue + Ambulance approaching -> PREEMPTING")
                elif features.ambulance_distance_m < 800:
                    sig_state = "PREPARING"
                    
                # check actual light color
                try:
                    state_str = traci.trafficlight.getRedYellowGreenState(next_junc).lower() if next_junc in traci.trafficlight.getIDList() else 'unknown'
                    if 'g' in state_str: light_color = "GREEN"
                    elif 'y' in state_str: light_color = "YELLOW"
                    elif 'r' in state_str: light_color = "RED"
                except:
                    pass

            # Check if any restorations fired recently (approximated based on active preemptions)
            active_preempts = ai_controller.signal_controller.get_active_preemptions()
            if not active_preempts and sig_state == "NORMAL":
                pass # Normal

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
                tel_msg = json.dumps(telemetry).encode('utf-8')
                sock.sendto(tel_msg, (UDP_IP, TELEMETRY_PORT))
            except Exception as e:
                pass
                    
        # Real-time synchronization
        elapsed = time.time() - loop_start
        sleep_time = REAL_TIME_STEP - elapsed
        if sleep_time > 0:
            pass # time.sleep(sleep_time)

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
