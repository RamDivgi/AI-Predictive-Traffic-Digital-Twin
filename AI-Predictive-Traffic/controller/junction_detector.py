from dataclasses import dataclass
from pathlib import Path

import sumolib
import traci


AMBULANCE_ID = "ambulance"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
NETWORK_FILE = "simulation/mangaluru/mangaluru_ai.net.xml.gz"
SUMO_NETWORK = sumolib.net.readNet(str(PROJECT_ROOT / NETWORK_FILE).replace('\\', '/'))


@dataclass
class JunctionInfo:
    junction_id: str
    incoming_edge: str
    outgoing_edge: str
    distance_from_ambulance_m: float


def _get_edge_length(edge_id: str) -> float:
    """
    Return the length of a SUMO edge using the loaded SUMO network.
    """

    edge = SUMO_NETWORK.getEdge(edge_id)
    return edge.getLength()


def _get_edge_destination(edge_id: str) -> str:
    """
    Return the destination junction ID of a SUMO edge.
    """

    edge = SUMO_NETWORK.getEdge(edge_id)
    return edge.getToNode().getID()


def get_upcoming_junctions(
    max_junctions: int = 3,
    ambulance_id: str = "ambulance",
) -> list[JunctionInfo]:
    """
    Find upcoming junctions along the ambulance's planned route.

    The ambulance route contains normal road edges. SUMO may also
    report internal junction edges such as :B_7 while a vehicle is
    physically crossing an intersection. Those internal edges are
    handled separately and are not treated as route edges.
    """

    if ambulance_id not in traci.vehicle.getIDList():
        return []

    route = list(traci.vehicle.getRoute(ambulance_id))
    route_index = traci.vehicle.getRouteIndex(ambulance_id)

    if not route or route_index < 0 or route_index >= len(route):
        return []

    current_edge_id = traci.vehicle.getRoadID(ambulance_id)
    current_lane_id = traci.vehicle.getLaneID(ambulance_id)
    current_lane_position = traci.vehicle.getLanePosition(ambulance_id)

    try:
        current_lane_length = traci.lane.getLength(current_lane_id)
    except traci.TraCIException:
        current_lane_length = 0.0

    distance_to_current_junction = max(
        0.0,
        current_lane_length - current_lane_position,
    )

    junctions: list[JunctionInfo] = []

    # If the vehicle is currently inside a SUMO internal junction edge,
    # the current route index still refers to the route edge that led
    # into that junction.
    current_route_edge = route[route_index]

    try:
        current_junction_id = _get_edge_destination(current_route_edge)
    except Exception:
        current_junction_id = None

    if current_junction_id is not None:
        if current_edge_id.startswith(":"):
            distance_to_junction = distance_to_current_junction
        else:
            try:
                current_edge_length = _get_edge_length(current_route_edge)
            except Exception:
                current_edge_length = current_lane_length

            distance_to_junction = max(
                0.0,
                current_edge_length - current_lane_position,
            )

        if route_index + 1 < len(route):
            import signal_mapping
            tls_id, indices = signal_mapping.get_tls_and_indices_for_movement(current_route_edge, route[route_index + 1])
            if tls_id and indices:
                junctions.append(
                    JunctionInfo(
                        junction_id=current_junction_id,
                        incoming_edge=current_route_edge,
                        outgoing_edge=route[route_index + 1],
                        distance_from_ambulance_m=distance_to_junction,
                    )
                )

    # Distance from the ambulance to the end of the current route edge.
    if current_edge_id.startswith(":"):
        distance_to_next_route_junction = distance_to_current_junction
    else:
        try:
            current_edge_length = _get_edge_length(current_route_edge)
        except Exception:
            current_edge_length = current_lane_length

        distance_to_next_route_junction = max(
            0.0,
            current_edge_length - current_lane_position,
        )

    # We need signal_mapping to check if the junction is actually signalized
    import signal_mapping

    # Add distances for subsequent route edges.
    for index in range(route_index + 1, len(route) - 1):
        incoming_edge = route[index]
        outgoing_edge = route[index + 1]

        try:
            edge_length = _get_edge_length(incoming_edge)
            junction_id = _get_edge_destination(incoming_edge)
        except Exception as e:
            print(f"DEBUG_JUNC: Exception for {incoming_edge}: {e}")
            continue

        if index == route_index + 1:
            cumulative_distance = distance_to_next_route_junction + edge_length
        else:
            cumulative_distance += edge_length

        # Avoid duplicating the junction already added above.
        if junctions and junctions[-1].junction_id == junction_id:
            continue

        # ONLY add if it is a valid traffic light mapping with signal indices
        tls_id, indices = signal_mapping.get_tls_and_indices_for_movement(incoming_edge, outgoing_edge)
        if not tls_id or not indices:
            continue

        junctions.append(
            JunctionInfo(
                junction_id=junction_id,
                incoming_edge=incoming_edge,
                outgoing_edge=outgoing_edge,
                distance_from_ambulance_m=cumulative_distance,
            )
        )

        if len(junctions) >= max_junctions:
            break

    return junctions[:max_junctions]


def format_junctions(junctions: list[JunctionInfo]) -> str:
    """
    Format upcoming junction information for readable console output.
    """

    if not junctions:
        return "No upcoming junctions."

    lines = []

    for index, junction in enumerate(junctions, start=1):
        lines.append(
            f"{index}. Junction {junction.junction_id} | "
            f"{junction.incoming_edge} -> {junction.outgoing_edge} | "
            f"Distance: {junction.distance_from_ambulance_m:.2f} m"
        )

    return "\n".join(lines)