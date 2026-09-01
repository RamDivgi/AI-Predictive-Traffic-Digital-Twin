from __future__ import annotations

from dataclasses import dataclass

import traci

from signal_mapping import (
    get_signal_indices_for_movement,
)


@dataclass
class TrafficFeatures:
    junction_id: str
    incoming_edge: str
    outgoing_edge: str

    ambulance_distance_m: float
    ambulance_speed_mps: float
    ambulance_eta_s: float

    vehicle_count: int
    halted_vehicle_count: int
    mean_speed_kmh: float
    occupancy_percent: float

    signal_phase: int
    signal_state: str
    movement_signal_indices: list[int]
    movement_signal_state: str
    signal_time_to_switch_s: float


def get_edge_traffic_features(
    edge_id: str,
) -> tuple[int, int, float, float]:
    """
    Collect traffic statistics for a SUMO edge.

    Returns:
        vehicle_count
        halted_vehicle_count
        mean_speed_kmh
        occupancy_percent
    """

    edge_ids = traci.edge.getIDList()

    if edge_id not in edge_ids:
        return 0, 0, 0.0, 0.0

    vehicle_count = traci.edge.getLastStepVehicleNumber(
        edge_id
    )

    halted_vehicle_count = traci.edge.getLastStepHaltingNumber(
        edge_id
    )

    mean_speed_mps = traci.edge.getLastStepMeanSpeed(
        edge_id
    )

    occupancy = traci.edge.getLastStepOccupancy(
        edge_id
    )

    mean_speed_kmh = max(
        0.0,
        mean_speed_mps * 3.6,
    )

    occupancy_percent = max(
        0.0,
        occupancy * 100.0,
    )

    return (
        vehicle_count,
        halted_vehicle_count,
        mean_speed_kmh,
        occupancy_percent,
    )


def get_signal_features(
    junction_id: str,
    incoming_edge: str,
    outgoing_edge: str,
) -> tuple[
    int,
    str,
    list[int],
    str,
    float,
]:
    """
    Collect the current traffic-signal state and determine
    the signal state specifically for the ambulance movement.
    """
    
    from signal_mapping import get_tls_and_indices_for_movement
    tls_id, movement_indices = get_tls_and_indices_for_movement(
        incoming_edge,
        outgoing_edge,
    )

    if not tls_id or tls_id not in traci.trafficlight.getIDList():
        return (
            -1,
            "",
            [],
            "",
            0.0,
        )

    current_time = traci.simulation.getTime()

    phase = traci.trafficlight.getPhase(tls_id)
    state = traci.trafficlight.getRedYellowGreenState(tls_id)
    next_switch = traci.trafficlight.getNextSwitch(tls_id)
    time_to_switch = max(0.0, next_switch - current_time)

    movement_state_chars = []

    for index in movement_indices:
        if 0 <= index < len(state):
            movement_state_chars.append(state[index])

    movement_signal_state = "".join(movement_state_chars)

    return (
        phase,
        state,
        movement_indices,
        movement_signal_state,
        time_to_switch,
    )


def build_traffic_features(
    junction,
    eta,
) -> TrafficFeatures:
    """
    Build a complete traffic feature vector for one
    upcoming ambulance junction.
    """

    vehicle_ids = traci.vehicle.getIDList()

    ambulance_speed_mps = 0.0

    if "ambulance" in vehicle_ids:
        ambulance_speed_mps = traci.vehicle.getSpeed(
            "ambulance"
        )

    (
        vehicle_count,
        halted_vehicle_count,
        mean_speed_kmh,
        occupancy_percent,
    ) = get_edge_traffic_features(
        junction.incoming_edge
    )

    (
        signal_phase,
        signal_state,
        movement_signal_indices,
        movement_signal_state,
        signal_time_to_switch_s,
    ) = get_signal_features(
        junction.junction_id,
        junction.incoming_edge,
        junction.outgoing_edge,
    )

    return TrafficFeatures(
        junction_id=junction.junction_id,
        incoming_edge=junction.incoming_edge,
        outgoing_edge=junction.outgoing_edge,
        ambulance_distance_m=float(
            eta.distance_m
        ),
        ambulance_speed_mps=float(
            ambulance_speed_mps
        ),
        ambulance_eta_s=float(
            eta.estimated_travel_seconds
        ),
        vehicle_count=int(
            vehicle_count
        ),
        halted_vehicle_count=int(
            halted_vehicle_count
        ),
        mean_speed_kmh=float(
            mean_speed_kmh
        ),
        occupancy_percent=float(
            occupancy_percent
        ),
        signal_phase=int(
            signal_phase
        ),
        signal_state=signal_state,
        movement_signal_indices=(
            movement_signal_indices
        ),
        movement_signal_state=(
            movement_signal_state
        ),
        signal_time_to_switch_s=float(
            signal_time_to_switch_s
        ),
    )


def format_traffic_features(
    features: TrafficFeatures,
) -> str:
    """
    Format traffic features for console output.
    """

    return (
        f"Junction {features.junction_id} | "
        f"{features.incoming_edge} -> "
        f"{features.outgoing_edge} | "
        f"Distance: "
        f"{features.ambulance_distance_m:.1f} m | "
        f"Amb speed: "
        f"{features.ambulance_speed_mps * 3.6:.1f} km/h | "
        f"ETA: "
        f"{features.ambulance_eta_s:.1f} s | "
        f"Vehicles: "
        f"{features.vehicle_count} | "
        f"Halted: "
        f"{features.halted_vehicle_count} | "
        f"Mean speed: "
        f"{features.mean_speed_kmh:.1f} km/h | "
        f"Occupancy: "
        f"{features.occupancy_percent:.2f}% | "
        f"Phase: "
        f"{features.signal_phase} | "
        f"Signal indices: "
        f"{features.movement_signal_indices} | "
        f"Amb signal state: "
        f"{features.movement_signal_state or 'N/A'} | "
        f"Switch: "
        f"{features.signal_time_to_switch_s:.1f} s"
    )