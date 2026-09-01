from pydantic import BaseModel
from typing import List, Optional

class AmbulanceState(BaseModel):
    vehicle_id: str
    latitude: float
    longitude: float
    speed: float
    current_edge: str
    current_route: str
    destination: str
    eta: float

class TrafficState(BaseModel):
    edge_id: str
    vehicle_count: int
    average_speed: float
    occupancy: float
    timestamp: float

class SignalState(BaseModel):
    junction_id: str
    state: str
    phase: int
    timestamp: float

class DecisionState(BaseModel):
    action: str
    timestamp: float
    details: str

class DigitalTwinState(BaseModel):
    simulation_time: float
    ambulance: Optional[AmbulanceState]
    traffic: List[TrafficState]
    signals: List[SignalState]
    decisions: List[DecisionState]

class TripStartRequest(BaseModel):
    emergency: bool
    hospital_id: str
    start_edge: Optional[str] = None

class HospitalResponse(BaseModel):
    id: str
    name: str
    available: bool
    reason: Optional[str] = None
    distance_km: Optional[float] = None

class StartPointResponse(BaseModel):
    id: str
    label: str
    outgoing_edge: str
