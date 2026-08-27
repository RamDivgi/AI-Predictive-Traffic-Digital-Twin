import json
import time
import threading
import paho.mqtt.client as mqtt
from twin.telemetry_ingest import AmbulanceTelemetry, TrafficTelemetry, SignalTelemetry

class MQTTTelemetryIngestor:
    def __init__(self, broker_address="127.0.0.1", port=1883):
        self.broker_address = broker_address
        self.port = port
        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        
        self.latest_ambulance = None
        self.latest_traffic = {}
        self.latest_signals = {}
        
        self.connected = False
        
        self.thread = threading.Thread(target=self._run_mqtt, daemon=True)
        self.thread.start()

    def _run_mqtt(self):
        try:
            self.client.connect(self.broker_address, self.port, 60)
            self.client.loop_forever()
        except Exception as e:
            print(f"MQTT connection failed: {e}")
        
    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.connected = True
            client.subscribe("traffic/ambulance")
            client.subscribe("traffic/vehicles")
            client.subscribe("traffic/signals")
        
    def on_message(self, client, userdata, msg):
        try:
            data = json.loads(msg.payload.decode())
            if msg.topic == "traffic/ambulance":
                self.latest_ambulance = AmbulanceTelemetry(
                    vehicle_id=data.get("vehicle_id", "ambulance"),
                    latitude=data["latitude"],
                    longitude=data["longitude"],
                    speed=data["speed"],
                    heading=data["heading"],
                    timestamp=data.get("timestamp", time.time())
                )
            elif msg.topic == "traffic/vehicles":
                edge_id = data["edge_id"]
                self.latest_traffic[edge_id] = TrafficTelemetry(
                    edge_id=edge_id,
                    vehicle_count=data["vehicle_count"],
                    average_speed=data["average_speed"],
                    occupancy=data["occupancy"],
                    timestamp=data.get("timestamp", time.time())
                )
            elif msg.topic == "traffic/signals":
                junction_id = data["junction_id"]
                self.latest_signals[junction_id] = SignalTelemetry(
                    junction_id=junction_id,
                    signal_state=data["state"],
                    current_phase=data["phase"],
                    timestamp=data.get("timestamp", time.time())
                )
        except Exception as e:
            print(f"Error parsing MQTT message on {msg.topic}: {e}")

    def get_latest_ambulance_telemetry(self, vehicle_id: str = "ambulance") -> AmbulanceTelemetry:
        return self.latest_ambulance
        
    def get_latest_traffic_telemetry(self, edge_id: str) -> TrafficTelemetry:
        return self.latest_traffic.get(edge_id)
        
    def get_latest_signal_telemetry(self, junction_id: str) -> SignalTelemetry:
        return self.latest_signals.get(junction_id)
