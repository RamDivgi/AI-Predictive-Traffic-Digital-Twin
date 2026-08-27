from dataclasses import dataclass

import traci


AMBULANCE_ID = "ambulance"


@dataclass
class RouteState:
    vehicle_id: str
    route: list[str]
    current_edge: str
    current_edge_index: int
    remaining_edges: list[str]


def get_route_state() -> RouteState | None:
    """
    Retrieve the current route state of the ambulance.

    Returns None if the ambulance is not currently
    present in the SUMO simulation.
    """

    if AMBULANCE_ID not in traci.vehicle.getIDList():
        return None

    route = list(traci.vehicle.getRoute(AMBULANCE_ID))
    current_edge = traci.vehicle.getRoadID(AMBULANCE_ID)
    current_edge_index = traci.vehicle.getRouteIndex(AMBULANCE_ID)

    if current_edge_index < 0:
        remaining_edges = []
    else:
        remaining_edges = route[current_edge_index:]

    return RouteState(
        vehicle_id=AMBULANCE_ID,
        route=route,
        current_edge=current_edge,
        current_edge_index=current_edge_index,
        remaining_edges=remaining_edges,
    )


def format_route_state(state: RouteState) -> str:
    """
    Format the route state for readable console output.
    """

    route_text = " -> ".join(state.route)
    remaining_text = " -> ".join(state.remaining_edges)

    return (
        f"Vehicle: {state.vehicle_id}\n"
        f"Full route: {route_text}\n"
        f"Current edge: {state.current_edge}\n"
        f"Current route index: {state.current_edge_index}\n"
        f"Remaining route: {remaining_text}"
    )