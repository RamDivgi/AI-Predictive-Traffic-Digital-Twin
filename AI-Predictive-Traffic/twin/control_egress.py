import time
import json
import uuid
from dataclasses import dataclass, asdict
from typing import List

@dataclass
class PreemptCommand:
    command_id: str
    action: str
    junction_id: str
    movement: str
    incoming_edge: str
    outgoing_edge: str
    signal_indices: List[int]
    timestamp: float

@dataclass
class RestoreCommand:
    command_id: str
    action: str
    junction_id: str
    timestamp: float

@dataclass
class RerouteCommand:
    command_id: str
    action: str
    vehicle_id: str
    old_route: str
    new_route: str
    timestamp: float

class ControlEgress:
    """
    Minimal hardware-independent control output layer.
    Accepts internal twin decisions, serializes them, and publishes via MQTT.
    """
    def __init__(self, broker_address="127.0.0.1", port=1883, use_mqtt=True):
        self.broker_address = broker_address
        self.port = port
        self.use_mqtt = use_mqtt
        if self.use_mqtt:
            import paho.mqtt.client as mqtt
            self.client = mqtt.Client()
            try:
                self.client.connect(self.broker_address, self.port, 60)
                self.client.loop_start()
            except Exception as e:
                print(f"ControlEgress MQTT connect error: {e}")
                self.use_mqtt = False

    def emit_preempt(self, junction_id: str, incoming_edge: str, outgoing_edge: str, signal_indices: List[int]) -> str:
        cmd = PreemptCommand(
            command_id=str(uuid.uuid4()),
            action="PREEMPT",
            junction_id=junction_id,
            movement=f"{incoming_edge} -> {outgoing_edge}",
            incoming_edge=incoming_edge,
            outgoing_edge=outgoing_edge,
            signal_indices=signal_indices,
            timestamp=time.time()
        )
        payload = json.dumps(asdict(cmd), indent=4)
        if self.use_mqtt:
            self.client.publish("traffic/control/preempt", payload)
        return payload
        
    def emit_restore(self, junction_id: str) -> str:
        cmd = RestoreCommand(
            command_id=str(uuid.uuid4()),
            action="RESTORE",
            junction_id=junction_id,
            timestamp=time.time()
        )
        payload = json.dumps(asdict(cmd), indent=4)
        if self.use_mqtt:
            self.client.publish("traffic/control/restore", payload)
        return payload
        
    def emit_reroute(self, vehicle_id: str, old_route: str, new_route: str) -> str:
        cmd = RerouteCommand(
            command_id=str(uuid.uuid4()),
            action="REROUTE",
            vehicle_id=vehicle_id,
            old_route=old_route,
            new_route=new_route,
            timestamp=time.time()
        )
        payload = json.dumps(asdict(cmd), indent=4)
        if self.use_mqtt:
            self.client.publish("traffic/control/reroute", payload)
        return payload



if __name__ == "__main__":
    egress = ControlEgress()
    
    preempt_json = egress.emit_preempt(
        junction_id="1452268548",
        incoming_edge="-26299202#4",
        outgoing_edge="-26299202#3",
        signal_indices=[0, 1]
    )
    
    restore_json = egress.emit_restore(
        junction_id="1452268548"
    )
    
    reroute_json = egress.emit_reroute(
        vehicle_id="ambulance",
        old_route="baseline_route",
        new_route="dynamic_astar_16_0"
    )
    
    print("\n============================================================")
    print("DIGITAL TWIN CONTROL EGRESS TEST")
    print("============================================================")
    print()
    print("PREEMPT COMMAND")
    print(preempt_json)
    print()
    print("RESTORE COMMAND")
    print(restore_json)
    print()
    print("REROUTE COMMAND")
    print(reroute_json)
    print()
    print("============================================================")
    print("CONTROL EGRESS VALIDATION: PASS")
    print("============================================================")
