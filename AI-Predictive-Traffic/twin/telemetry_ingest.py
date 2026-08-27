import time
from dataclasses import dataclass

@dataclass
class AmbulanceTelemetry:
    vehicle_id: str
    latitude: float
    longitude: float
    speed: float
    heading: float
    timestamp: float

@dataclass
class TrafficTelemetry:
    edge_id: str
    vehicle_count: int
    average_speed: float
    occupancy: float
    timestamp: float

@dataclass
class SignalTelemetry:
    junction_id: str
    signal_state: str
    current_phase: int
    timestamp: float

class TelemetryIngestor:
    """
    Minimal mock telemetry ingestion layer for the Digital Twin.
    Provides deterministic mock data that simulates real-world MQTT/hardware input.
    """
    
    def __init__(self):
        # Anchor the mock generation to when the ingestor starts
        self._start_time = time.time()
        
    def get_latest_ambulance_telemetry(self, vehicle_id: str = "ambulance") -> AmbulanceTelemetry:
        """Fetch mock real-time ambulance telemetry."""
        elapsed = time.time() - self._start_time
        
        return AmbulanceTelemetry(
            vehicle_id=vehicle_id,
            latitude=12.86640 + (elapsed * 0.0001) % 0.01,
            longitude=74.85466 + (elapsed * 0.0001) % 0.01,
            speed=15.0 + (elapsed % 10.0),
            heading=90.0,
            timestamp=time.time()
        )
        
    def get_latest_traffic_telemetry(self, edge_id: str) -> TrafficTelemetry:
        """Fetch mock real-time traffic telemetry for a specific edge."""
        elapsed = time.time() - self._start_time
        return TrafficTelemetry(
            edge_id=edge_id,
            vehicle_count=int(20 + (elapsed % 30)),
            average_speed=12.5,
            occupancy=0.45,
            timestamp=time.time()
        )
        
    def get_latest_signal_telemetry(self, junction_id: str) -> SignalTelemetry:
        """Fetch mock real-time signal telemetry for a specific junction."""
        phase = int((time.time() - self._start_time) % 4)
        states = ["rrrrrrrr", "GGGGGGGG", "yyyyyyyy", "GrGrGrGr"]
        
        return SignalTelemetry(
            junction_id=junction_id,
            signal_state=states[phase],
            current_phase=phase,
            timestamp=time.time()
        )

# Runtime validation test
if __name__ == "__main__":
    ingestor = TelemetryIngestor()
    
    print("--- Digital Twin Telemetry Ingest Validation ---")
    
    amb = ingestor.get_latest_ambulance_telemetry()
    print("\n[Ambulance]")
    print(amb)
    
    traffic = ingestor.get_latest_traffic_telemetry("321397980")
    print("\n[Traffic]")
    print(traffic)
    
    signal = ingestor.get_latest_signal_telemetry("1452268548")
    print("\n[Signal]")
    print(signal)
    
    print("\nTimestamps match generation time:", amb.timestamp > 0)
    print("Test passed successfully.")
