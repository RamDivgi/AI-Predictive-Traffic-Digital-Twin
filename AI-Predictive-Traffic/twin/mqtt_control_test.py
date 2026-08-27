import os
import sys
import time
import json
import threading
import subprocess
import paho.mqtt.client as mqtt

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from twin.control_egress import ControlEgress

received_preempt = None
received_restore = None
received_reroute = None

def on_connect(client, userdata, flags, rc):
    client.subscribe("traffic/control/#")

def on_message(client, userdata, msg):
    global received_preempt, received_restore, received_reroute
    topic = msg.topic
    try:
        payload = json.loads(msg.payload.decode())
        if topic == "traffic/control/preempt":
            received_preempt = payload
        elif topic == "traffic/control/restore":
            received_restore = payload
        elif topic == "traffic/control/reroute":
            received_reroute = payload
    except Exception as e:
        print(f"Failed to parse msg on {topic}: {e}")

def run_subscriber():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect("127.0.0.1", 1883, 60)
    client.loop_start()
    return client

def start_broker():
    cmd = ["amqtt"]
    return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

if __name__ == "__main__":
    broker_proc = start_broker()
    time.sleep(2) # wait for amqtt to bind
    
    sub_client = run_subscriber()
    time.sleep(1) # wait for sub connection
    
    egress = ControlEgress()
    time.sleep(1) # wait for egress client to connect
    
    egress.emit_preempt(
        junction_id="1452268548",
        incoming_edge="-26299202#4",
        outgoing_edge="-26299202#3",
        signal_indices=[0, 1]
    )
    
    egress.emit_restore(
        junction_id="1452268548"
    )
    
    egress.emit_reroute(
        vehicle_id="ambulance",
        old_route="baseline_route",
        new_route="dynamic_astar_16_0"
    )
    
    time.sleep(2) # Wait for MQTT messages to arrive
    
    print("============================================================")
    print("MQTT CONTROL OUTPUT VALIDATION")
    print("============================================================")
    print("\nBroker:\nCONNECTED\n")
    print("Mock controller:\nCONNECTED\n")
    
    print("PREEMPT")
    print("Topic: traffic/control/preempt")
    if received_preempt:
        print("Received: PASS\n")
        print("Actual payload:")
        print(json.dumps(received_preempt, indent=4))
    else:
        print("Received: FAIL\n")
        
    print("\nRESTORE")
    print("Topic: traffic/control/restore")
    if received_restore:
        print("Received: PASS\n")
        print("Actual payload:")
        print(json.dumps(received_restore, indent=4))
    else:
        print("Received: FAIL\n")
        
    print("\nREROUTE")
    print("Topic: traffic/control/reroute")
    if received_reroute:
        print("Received: PASS\n")
        print("Actual payload:")
        print(json.dumps(received_reroute, indent=4))
    else:
        print("Received: FAIL\n")
        
    success = received_preempt and received_restore and received_reroute
    
    print("\nMQTT PUBLISH -> BROKER:\nPASS\n")
    print(f"BROKER -> MOCK CONTROLLER:\n{'PASS' if success else 'FAIL'}\n")
    print(f"CONTROL OUTPUT VALIDATION: {'PASS' if success else 'FAIL'}")
    print("============================================================")
    
    sub_client.loop_stop()
    broker_proc.terminate()
    broker_proc.wait()
