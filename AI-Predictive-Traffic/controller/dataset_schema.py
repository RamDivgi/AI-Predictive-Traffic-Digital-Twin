from dataclasses import dataclass, asdict
from typing import Dict, Any


@dataclass
class TrafficObservation:
    """
    Single traffic observation collected from the SUMO simulation.

    Each observation represents the state of the ambulance, traffic,
    and upcoming junction at one simulation timestep.
    """

    simulation_time: float

    # Ambulance information
    ambulance_id: str
    ambulance_edge: str
    ambulance_speed_mps: float
    ambulance_speed_kmh: float

    # Junction information
    junction_id: str
    incoming_edge: str
    outgoing_edge: str
    distance_to_junction_m: float
    ambulance_eta_s: float

    # Traffic information
    vehicle_count: int
    halted_vehicle_count: int
    mean_speed_kmh: float
    occupancy_percent: float

    # Traffic signal information
    signal_phase: int
    signal_state: str
    signal_time_to_switch_s: float

    def to_dict(self) -> Dict[str, Any]:
        """Convert the observation into a dictionary."""
        return asdict(self)

    @staticmethod
    def csv_headers():
        """Return CSV column names in the correct order."""
        return [
            "simulation_time",
            "ambulance_id",
            "ambulance_edge",
            "ambulance_speed_mps",
            "ambulance_speed_kmh",
            "junction_id",
            "incoming_edge",
            "outgoing_edge",
            "distance_to_junction_m",
            "ambulance_eta_s",
            "vehicle_count",
            "halted_vehicle_count",
            "mean_speed_kmh",
            "occupancy_percent",
            "signal_phase",
            "signal_state",
            "signal_time_to_switch_s",
        ]