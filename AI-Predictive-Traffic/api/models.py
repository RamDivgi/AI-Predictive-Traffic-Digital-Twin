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
    id: Optional[str] = None
    junction_id: Optional[str] = None
    state: str
    current_state: Optional[str] = None
    phase: Optional[int] = 0
    timestamp: Optional[float] = 0.0
    coordinates: Optional[dict] = None
    x: Optional[float] = None
    y: Optional[float] = None

class DecisionState(BaseModel):
    action: str
    timestamp: float
    details: str

class TrafficMetrics(BaseModel):
    round_id: int = 0
    scenario: str = "medium"
    scheduled: int = 0
    inserted: int = 0
    active: int = 0
    arrived: int = 0
    removed: int = 0
    waiting: int = 0
    mean_speed_kmh: float = 0.0
    edge_speeds: Optional[dict] = {}
    edge_queues: Optional[dict] = {}

class DigitalTwinState(BaseModel):
    simulation_time: float
    ambulance: Optional[AmbulanceState] = None
    route: Optional[dict] = None
    traffic: List[TrafficState] = []
    signals: List[SignalState] = []
    decisions: List[DecisionState] = []
    traffic_metrics: Optional[TrafficMetrics] = None
    incidents: Optional[List[dict]] = []
    green_corridor: Optional[dict] = None
    decision_support: Optional[dict] = None

class TripStartRequest(BaseModel):
    emergency: bool
    hospital_id: str
    start_edge: Optional[str] = None
    traffic_scenario: Optional[str] = "medium"

class TripModeRequest(BaseModel):
    emergency: bool

class IncidentCreateRequest(BaseModel):
    edge_id: str
    severity: Optional[str] = "blockage"  # "blockage" or "slowdown"
    description: Optional[str] = None

class IncidentClearRequest(BaseModel):
    edge_id: str

class SimControlRequest(BaseModel):
    action: str  # "pause", "resume", "reset"

class HospitalResponse(BaseModel):
    id: str
    name: str
    available: bool
    reason: Optional[str] = None
    distance_km: Optional[float] = None
    nearest_edge: Optional[str] = None
    coordinates: Optional[dict] = None
    x: Optional[float] = None
    y: Optional[float] = None
    destination_type: Optional[str] = "hospital"

class StartPointResponse(BaseModel):
    id: str
    label: str
    name: Optional[str] = None
    outgoing_edge: str
    edge_id: Optional[str] = None
