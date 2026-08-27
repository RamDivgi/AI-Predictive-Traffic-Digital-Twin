from dataclasses import dataclass

import traci


AMBULANCE_ID = "ambulance"


@dataclass
class ETAResult:
    vehicle_id: str
    current_edge: str
    target_edge: str
    distance_m: float
    speed_mps: float
    eta_seconds: float


def calculate_eta_to_edge(target_edge: str) -> ETAResult | None:
    """
    Estimate the ambulance's arrival time at a target edge.

    The estimate uses the ambulance's current position, current
    speed, and the remaining route distance.
    """

    if AMBULANCE_ID not in traci.vehicle.getIDList():
        return None

    route = list(traci.vehicle.getRoute(AMBULANCE_ID))
    current_edge_index = traci.vehicle.getRouteIndex(AMBULANCE_ID)

    if current_edge_index < 0:
        return None

    if target_edge not in route[current_edge_index:]:
        return None

    current_edge = traci.vehicle.getRoadID(AMBULANCE_ID)
    speed_mps = traci.vehicle.getSpeed(AMBULANCE_ID)

    if speed_mps <= 0:
        return None

    current_lane_position = traci.vehicle.getLanePosition(AMBULANCE_ID)

    distance_m = 0.0

    if current_edge == target_edge:
        edge_length = traci.lane.getLength(
            traci.vehicle.getLaneID(AMBULANCE_ID)
        )

        distance_m = max(
            0.0,
            edge_length - current_lane_position,
        )

    else:
        current_lane_id = traci.vehicle.getLaneID(AMBULANCE_ID)
        current_edge_length = traci.lane.getLength(current_lane_id)

        distance_m += max(
            0.0,
            current_edge_length - current_lane_position,
        )

        target_index = route.index(target_edge, current_edge_index + 1)

        for edge_id in route[current_edge_index + 1:target_index]:
            edge_lanes = traci.edge.getLaneNumber(edge_id)

            if edge_lanes <= 0:
                continue

            edge_lane_id = f"{edge_id}_0"
            distance_m += traci.lane.getLength(edge_lane_id)

    eta_seconds = distance_m / speed_mps

    return ETAResult(
        vehicle_id=AMBULANCE_ID,
        current_edge=current_edge,
        target_edge=target_edge,
        distance_m=distance_m,
        speed_mps=speed_mps,
        eta_seconds=eta_seconds,
    )


def format_eta_result(result: ETAResult) -> str:
    """Format ETA information for readable console output."""

    return (
        f"Current edge: {result.current_edge} | "
        f"Target edge: {result.target_edge} | "
        f"Distance: {result.distance_m:.2f} m | "
        f"Speed: {result.speed_mps:.2f} m/s | "
        f"ETA: {result.eta_seconds:.2f} s"
    )