from dataclasses import dataclass

import traci


AMBULANCE_ID = "ambulance"


@dataclass
class EdgeTraffic:
    edge_id: str
    vehicle_count: int
    halted_vehicle_count: int
    mean_speed_mps: float
    occupancy_percent: float


def get_route_edges_ahead(max_edges: int = 3) -> list[str]:
    """
    Return the ambulance's current and upcoming normal route edges.

    Internal SUMO junction edges such as :B_7 are ignored.
    """

    if AMBULANCE_ID not in traci.vehicle.getIDList():
        return []

    route = list(traci.vehicle.getRoute(AMBULANCE_ID))
    route_index = traci.vehicle.getRouteIndex(AMBULANCE_ID)

    if not route or route_index < 0:
        return []

    edges_ahead = []

    for edge_id in route[route_index:]:
        if edge_id.startswith(":"):
            continue

        edges_ahead.append(edge_id)

        if len(edges_ahead) >= max_edges:
            break

    return edges_ahead


def get_edge_traffic(edge_id: str) -> EdgeTraffic:
    """
    Read the current traffic conditions on a SUMO edge.
    """

    vehicle_count = traci.edge.getLastStepVehicleNumber(edge_id)
    halted_vehicle_count = traci.edge.getLastStepHaltingNumber(edge_id)
    mean_speed_mps = traci.edge.getLastStepMeanSpeed(edge_id)
    occupancy_percent = traci.edge.getLastStepOccupancy(edge_id)

    return EdgeTraffic(
        edge_id=edge_id,
        vehicle_count=vehicle_count,
        halted_vehicle_count=halted_vehicle_count,
        mean_speed_mps=mean_speed_mps,
        occupancy_percent=occupancy_percent,
    )


def get_upcoming_traffic(
    max_edges: int = 3,
) -> list[EdgeTraffic]:
    """
    Return traffic information for the ambulance's upcoming route edges.
    """

    edges = get_route_edges_ahead(max_edges)

    return [get_edge_traffic(edge_id) for edge_id in edges]


def format_traffic(traffic: list[EdgeTraffic]) -> str:
    """
    Format traffic information for console output.
    """

    if not traffic:
        return "No upcoming traffic data."

    lines = []

    for index, edge in enumerate(traffic, start=1):
        speed_kmh = edge.mean_speed_mps * 3.6

        lines.append(
            f"{index}. Edge {edge.edge_id} | "
            f"Vehicles: {edge.vehicle_count} | "
            f"Halted: {edge.halted_vehicle_count} | "
            f"Mean speed: {speed_kmh:.1f} km/h | "
            f"Occupancy: {edge.occupancy_percent:.1f}%"
        )

    return "\n".join(lines)