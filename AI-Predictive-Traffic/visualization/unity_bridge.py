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

SUMO_CONFIG = PROJECT_ROOT / "simulation" / "mangaluru" / "ambulance_test.sumocfg"

# UDP setup
UDP_IP = "127.0.0.1"
UDP_PORT = 5005
TRAFFIC_UDP_PORT = 5006
TLS_UDP_PORT = 5007

REAL_TIME_STEP = 0.1  # SUMO step length and real-time loop delay (in seconds)

print(f"Starting UDP server, targeting Unity at {UDP_IP}:{UDP_PORT}")
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

def main():
    print("=" * 60)
    print("STARTING SUMO -> UNITY BRIDGE")
    print("=" * 60)

    traci.start([
        "sumo",
        "-c", str(SUMO_CONFIG),
        "--step-length", str(REAL_TIME_STEP),
        "--quit-on-end",
        "--start"
    ])

    ambulance_found = False
    
    print("Waiting for ambulance to spawn...")
    
    step = 0
    while traci.simulation.getMinExpectedNumber() > 0 and traci.simulation.getTime() < 3600:
        loop_start = time.time()
        
        traci.simulationStep()
        step += 1
        
        vehicles = traci.vehicle.getIDList()
        
        if "ambulance" in vehicles:
            if not ambulance_found:
                print("\n[SUCCESS] Ambulance found!")
                ambulance_found = True
                
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
        for v_id in vehicles:
            if v_id == "ambulance":
                continue
                
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
                "sim_time": traci.simulation.getTime()
            })
            
        if len(traffic_vehicles) > 0:
            traffic_payload = {"vehicles": traffic_vehicles}
            traffic_message = json.dumps(traffic_payload).encode('utf-8')
            try:
                sock.sendto(traffic_message, (UDP_IP, TRAFFIC_UDP_PORT))
            except OSError as e:
                print(f"UDP send error (packet too large? size: {len(traffic_message)}): {e}")
                
        # --- NEW: Traffic Signal Broadcasting ---
        # Throttle to avoid sending every step if states haven't changed much, but 10Hz is fine for UDP
        tls_ids = traci.trafficlight.getIDList()
        signals = []
        for tls in tls_ids:
            state = traci.trafficlight.getRedYellowGreenState(tls)
            signals.append({"id": tls, "state": state})
            
        if len(signals) > 0:
            tls_payload = {"signals": signals}
            tls_message = json.dumps(tls_payload).encode('utf-8')
            try:
                sock.sendto(tls_message, (UDP_IP, TLS_UDP_PORT))
            except OSError as e:
                print(f"UDP send error TLS: {e}")
                    
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
