from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import sumolib
import traci

from traffic_features import get_edge_traffic_features
from signal_mapping import get_signal_indices_for_movement


PROJECT_ROOT = Path(__file__).resolve().parent.parent
NETWORK_FILE = PROJECT_ROOT / "simulation" / "network" / "test.net.xml"

_SUMO_NETWORK = None


def _get_network() -> sumolib.net.Net:
    global _SUMO_NETWORK
    if _SUMO_NETWORK is None:
        try:
            import config
            _SUMO_NETWORK = sumolib.net.readNet(str(config.NET_FILE))
        except Exception:
            _SUMO_NETWORK = sumolib.net.readNet(str(NETWORK_FILE))
    return _SUMO_NETWORK


def _get_edge_length_safe(edge_id: str) -> float:
    """
    Retrieve edge length safely without relying on external private helpers.
    """
    try:
        return _get_network().getEdge(edge_id).getLength()
    except Exception:
        try:
            return traci.lane.getLength(f"{edge_id}_0")
        except traci.TraCIException:
            return 100.0


def _get_destination_junction(edge_id: str) -> str | None:
    """
    Retrieve the destination junction ID for an edge.
    """
    try:
        return _get_network().getEdge(edge_id).getToNode().getID()
    except Exception:
        return None


_CACHED_TLS_IDS: set[str] | None = None
_CACHED_TLS_CONNECTION = None

_STEP_SIGNAL_DELAY_CACHE: dict[tuple[str, str, str], float] = {}
_STEP_SIGNAL_DELAY_TIME: float = -1.0
_STEP_SIGNAL_DELAY_CONN = None


def get_network_tls_ids() -> set[str]:
    """
    Return the set of TLS IDs for the active SUMO network.
    Caches TLS IDs per TraCI connection so that static network topology
    is not repeatedly queried over the socket on every junction transition,
    while automatically invalidating if TraCI reconnects.
    """
    global _CACHED_TLS_IDS, _CACHED_TLS_CONNECTION
    try:
        current_conn = traci.getConnection()
    except Exception:
        _CACHED_TLS_IDS = None
        _CACHED_TLS_CONNECTION = None
        return set()

    if _CACHED_TLS_IDS is None or _CACHED_TLS_CONNECTION is not current_conn:
        try:
            _CACHED_TLS_IDS = set(traci.trafficlight.getIDList())
            _CACHED_TLS_CONNECTION = current_conn
        except Exception:
            return set()

    return _CACHED_TLS_IDS


def clear_network_tls_ids_cache() -> None:
    """Explicitly invalidate the TLS IDs and signal delay cache if needed."""
    global _CACHED_TLS_IDS, _CACHED_TLS_CONNECTION, _STEP_SIGNAL_DELAY_CACHE, _STEP_SIGNAL_DELAY_TIME, _STEP_SIGNAL_DELAY_CONN
    _CACHED_TLS_IDS = None
    _CACHED_TLS_CONNECTION = None
    _STEP_SIGNAL_DELAY_CACHE.clear()
    _STEP_SIGNAL_DELAY_TIME = -1.0
    _STEP_SIGNAL_DELAY_CONN = None


def get_signal_delay(
    junction_id: str,
    incoming_edge: str,
    outgoing_edge: str,
) -> float:
    """
    Determine the expected signal delay for a specific movement,
    reusing the existing movement-specific signal mapping.
    Results are cached within each simulation step to eliminate thousands of
    redundant socket queries during A* path search.
    """
    global _STEP_SIGNAL_DELAY_CACHE, _STEP_SIGNAL_DELAY_TIME, _STEP_SIGNAL_DELAY_CONN

    tls_ids = get_network_tls_ids()
    if junction_id not in tls_ids:
        return 0.0

    try:
        current_conn = traci.getConnection()
        current_time = traci.simulation.getTime()
    except Exception:
        current_conn = None
        current_time = -1.0

    if current_conn != _STEP_SIGNAL_DELAY_CONN or current_time != _STEP_SIGNAL_DELAY_TIME:
        _STEP_SIGNAL_DELAY_CACHE.clear()
        _STEP_SIGNAL_DELAY_CONN = current_conn
        _STEP_SIGNAL_DELAY_TIME = current_time

    cache_key = (junction_id, incoming_edge, outgoing_edge)
    cached = _STEP_SIGNAL_DELAY_CACHE.get(cache_key)
    if cached is not None:
        return cached

    try:
        state = traci.trafficlight.getRedYellowGreenState(junction_id)
    except Exception:
        return 0.0
    
    indices = get_signal_indices_for_movement(
        junction_id,
        incoming_edge,
        outgoing_edge,
    )

    if not indices:
        _STEP_SIGNAL_DELAY_CACHE[cache_key] = 0.0
        return 0.0

    movement_chars = []
    for idx in indices:
        if 0 <= idx < len(state):
            movement_chars.append(state[idx])

    movement_state = "".join(movement_chars).strip().lower()

    if not movement_state:
        _STEP_SIGNAL_DELAY_CACHE[cache_key] = 0.0
        return 0.0

    is_unfavorable = any(c != "g" for c in movement_state)

    if is_unfavorable:
        try:
            next_switch = traci.trafficlight.getNextSwitch(junction_id)
            delay = max(0.0, next_switch - current_time)
            res = delay if delay > 0.0 else 5.0
        except Exception:
            res = 5.0
        _STEP_SIGNAL_DELAY_CACHE[cache_key] = res
        return res

    _STEP_SIGNAL_DELAY_CACHE[cache_key] = 0.0
    return 0.0


@dataclass
class RouteEvaluation:
    route_id: str
    route_edges: list[str]
    road_travel_time_s: float
    signal_delay_s: float
    total_time_s: float
    traffic_cost: float
    vehicle_count: int
    halted_vehicle_count: int
    mean_speed_kmh: float

    def format(self) -> str:
        return (
            f"Route {self.route_id}:\n"
            f"    estimated ETA = {self.total_time_s:.1f} seconds\n"
            f"    traffic cost = {self.traffic_cost:.1f}\n"
            f"    signal delay = {self.signal_delay_s:.1f} seconds\n"
            f"    total cost = {self.total_time_s + self.traffic_cost:.1f}"
        )


def evaluate_route(
    route_id: str,
    route_edges: list[str],
    current_edge: str,
    current_lane_position: float,
    ambulance_speed_mps: float,
    ml_etas: dict[str, float] | None = None,
) -> RouteEvaluation | None:
    """
    Evaluate a candidate route.

    Combines ML ETA for the immediate upcoming junction with custom 
    distance/speed/signal estimations for the remaining edges.
    """
    
    if ml_etas is None:
        ml_etas = {}
        
    try:
        start_index = route_edges.index(current_edge)
    except ValueError:
        return None
        
    remaining_edges = route_edges[start_index:]
    
    if not remaining_edges:
        return None
    
    total_road_time = 0.0
    total_signal_delay = 0.0
    total_vehicles = 0
    total_halted = 0
    sum_mean_speed = 0.0
    edge_count = 0
    traffic_cost = 0.0
    
    for i, edge_id in enumerate(remaining_edges):
        
        edge_length = _get_edge_length_safe(edge_id)
                
        if i == 0:
            distance_to_travel = max(0.0, edge_length - current_lane_position)
        else:
            distance_to_travel = edge_length
            
        (
            vehicle_count,
            halted_vehicle_count,
            mean_speed_kmh,
            occupancy_percent,
        ) = get_edge_traffic_features(edge_id)
        
        mean_speed_mps = max(0.1, mean_speed_kmh / 3.6) if vehicle_count > 0 else max(ambulance_speed_mps, 15.0)
        
        if halted_vehicle_count > 0:
            speed = min(max(5.0, ambulance_speed_mps), mean_speed_mps)
            speed = max(speed, 0.1)
        elif vehicle_count > 0:
            speed = max(ambulance_speed_mps, mean_speed_mps, 1.0)
        else:
            speed = max(ambulance_speed_mps, 15.0)
            
        road_time = distance_to_travel / speed
        
        junction_id = _get_destination_junction(edge_id)
            
        if i == 0 and junction_id and junction_id in ml_etas:
            road_time = ml_etas[junction_id]

        total_road_time += road_time
        
        total_vehicles += vehicle_count
        total_halted += halted_vehicle_count
        sum_mean_speed += mean_speed_kmh
        edge_count += 1
        traffic_cost += (vehicle_count * 1.0) + (halted_vehicle_count * 3.0) + (occupancy_percent * 0.5)
        
        # Signal delay
        if i < len(remaining_edges) - 1:
            next_edge = remaining_edges[i + 1]
            if junction_id:
                delay = get_signal_delay(junction_id, edge_id, next_edge)
                total_signal_delay += delay
                    
    total_time = total_road_time + total_signal_delay
    avg_mean_speed = sum_mean_speed / edge_count if edge_count > 0 else 0.0
    
    return RouteEvaluation(
        route_id=route_id,
        route_edges=route_edges,
        road_travel_time_s=total_road_time,
        signal_delay_s=total_signal_delay,
        total_time_s=total_time,
        traffic_cost=traffic_cost,
        vehicle_count=total_vehicles,
        halted_vehicle_count=total_halted,
        mean_speed_kmh=avg_mean_speed,
    )
