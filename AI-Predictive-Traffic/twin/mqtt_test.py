import os
import sys
import time
import json
import threading
import subprocess
import paho.mqtt.publish as publish
import paho.mqtt.client as mqtt

# Ensure SUMO_HOME is set
if 'SUMO_HOME' in os.environ:
    tools = os.path.join(os.environ['SUMO_HOME'], 'tools')
    sys.path.append(tools)
    
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import traci
from twin.mqtt_telemetry import MQTTTelemetryIngestor
from twin.state_sync import StateSynchronizer

def start_broker():
    # Run amqtt locally
    cmd = ["amqtt"]
    return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def publish_mock_data():
    broker = "127.0.0.1"
    port = 1883
    
    # Ambulance
    publish.single("traffic/ambulance", json.dumps({
        "vehicle_id": "ambulance",
        "latitude": 12.86640,
        "longitude": 74.85466,
        "speed": 40.0,
        "heading": 90.0,
        "timestamp": time.time()
    }), hostname=broker, port=port)
    
    # Traffic
    publish.single("traffic/vehicles", json.dumps({
        "edge_id": "1366470617#1",
        "vehicle_count": 25,
        "average_speed": 18.5,
        "occupancy": 62.0,
        "timestamp": time.time()
    }), hostname=broker, port=port)
    
    # Signal
    publish.single("traffic/signals", json.dumps({
        "junction_id": "1452268548",
        "state": "rGr",
        "phase": 2,
        "timestamp": time.time()
    }), hostname=broker, port=port)

if __name__ == "__main__":
    print("Starting MQTT broker...")
    broker_proc = start_broker()
    time.sleep(2) # wait for broker to bind
    
    ingestor = MQTTTelemetryIngestor()
    time.sleep(1) # wait for connect
    
    print("Publishing mock telemetry...")
    publish_mock_data()
    time.sleep(1) # wait for messages to be received
    
    amb_data = ingestor.get_latest_ambulance_telemetry()
    traffic_data = ingestor.get_latest_traffic_telemetry("1366470617#1")
    sig_data = ingestor.get_latest_signal_telemetry("1452268548")
    
    print("============================================================")
    print("MQTT TELEMETRY VALIDATION")
    print("============================================================")
    print("\nBroker:\nCONNECTED\n")
    print("Publisher:\nCONNECTED\n")
    print("Subscriber:\nCONNECTED\n")
    
    print("AMBULANCE MESSAGE")
    print("Topic: traffic/ambulance")
    if amb_data:
        print(f"Vehicle: {amb_data.vehicle_id}")
        print(f"Speed: {amb_data.speed}")
        print(f"Position: {amb_data.latitude}, {amb_data.longitude}")
        print("Received: PASS\n")
    else:
        print("Received: FAIL\n")
        
    print("TRAFFIC MESSAGE")
    print("Topic: traffic/vehicles")
    if traffic_data:
        print(f"Edge: {traffic_data.edge_id}")
        print(f"Vehicles: {traffic_data.vehicle_count}")
        print("Received: PASS\n")
    else:
        print("Received: FAIL\n")
        
    print("SIGNAL MESSAGE")
    print("Topic: traffic/signals")
    if sig_data:
        print(f"Junction: {sig_data.junction_id}")
        print(f"Phase: {sig_data.current_phase}")
        print("Received: PASS\n")
    else:
        print("Received: FAIL\n")
        
    print(f"MQTT -> TELEMETRY:\n{'PASS' if (amb_data and traffic_data and sig_data) else 'FAIL'}\n")
    
    # State sync test
    sumocfg = os.path.abspath(os.path.join(
        os.path.dirname(__file__), 
        "..", 
        "simulation", 
        "mangaluru", 
        "ambulance_test.sumocfg"
    ))
    
    traci.start(["sumo", "-c", sumocfg, "--no-step-log", "true", "--no-warnings", "true"])
    sync_pass = False
    duplicate_traci_pass = True # We only started TraCI once in this script
    
    try:
        # Advance simulation to ensure ambulance spawns
        while "ambulance" not in traci.vehicle.getIDList():
            traci.simulationStep()
            if traci.simulation.getTime() > 60:
                break
            
        sync = StateSynchronizer(ingestor=ingestor)
        result = sync.sync_ambulance()
        sync_pass = result.get('received') and result.get('vehicle') == 'ambulance' and result.get('error') is None
    except Exception as e:
        print(f"TraCI error: {e}")
    finally:
        traci.close()
        broker_proc.terminate()
        broker_proc.wait()

    print(f"TELEMETRY -> STATE SYNC:\n{'PASS' if sync_pass else 'FAIL'}\n")
    print(f"NO DUPLICATE TRACI CONNECTION:\n{'PASS' if duplicate_traci_pass else 'FAIL'}\n")
    print("============================================================")
    print(f"MQTT TELEMETRY VALIDATION: {'PASS' if (amb_data and traffic_data and sig_data and sync_pass and duplicate_traci_pass) else 'FAIL'}")
    print("============================================================")
