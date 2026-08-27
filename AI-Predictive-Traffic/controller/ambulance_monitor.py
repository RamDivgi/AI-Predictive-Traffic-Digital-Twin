from dataclasses import dataclass

import traci


@dataclass
class AmbulanceState:
    vehicle_id: str
    simulation_time: float
    edge_id: str
    position_x: float
    position_y: float
    speed_mps: float


AMBULANCE_ID = "ambulance"


def get_ambulance_state() -> AmbulanceState | None:
    """
    Read the current state of the ambulance from SUMO.

    Returns None if the ambulance is not currently
    present in the simulation.
    """

    vehicle_ids = traci.vehicle.getIDList()

    if AMBULANCE_ID not in vehicle_ids:
        return None

    position_x, position_y = traci.vehicle.getPosition(AMBULANCE_ID)

    return AmbulanceState(
        vehicle_id=AMBULANCE_ID,
        simulation_time=traci.simulation.getTime(),
        edge_id=traci.vehicle.getRoadID(AMBULANCE_ID),
        position_x=position_x,
        position_y=position_y,
        speed_mps=traci.vehicle.getSpeed(AMBULANCE_ID),
    )


def format_ambulance_state(state: AmbulanceState) -> str:
    """
    Format the ambulance state for readable console output.
    """

    speed_kmh = state.speed_mps * 3.6

    return (
        f"Time: {state.simulation_time:6.1f}s | "
        f"Edge: {state.edge_id:>3} | "
        f"Position: ({state.position_x:7.2f}, {state.position_y:7.2f}) | "
        f"Speed: {state.speed_mps:5.2f} m/s "
        f"({speed_kmh:5.1f} km/h)"
    )