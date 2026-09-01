from __future__ import annotations

import heapq
import math
from dataclasses import dataclass
from pathlib import Path
import sys

# Ensure local imports work regardless of how the script is executed
sys.path.append(str(Path(__file__).resolve().parent))

import sumolib
import traci

from traffic_features import get_edge_traffic_features
from route_evaluator import get_signal_delay


PROJECT_ROOT = Path(__file__).resolve().parent.parent
NETWORK_FILE = PROJECT_ROOT / "simulation" / "network" / "test.net.xml"

_SUMO_NETWORK = None


def _get_network() -> sumolib.net.Net:
    global _SUMO_NETWORK
    if _SUMO_NETWORK is None:
        import config
        _SUMO_NETWORK = sumolib.net.readNet(str(config.NET_FILE))
    return _SUMO_NETWORK


@dataclass
class AStarRoute:
    edge_ids: list[str]
    node_ids: list[str]
    total_cost: float
    estimated_travel_time_s: float
    total_signal_delay_s: float
    total_congestion_cost: float
    total_distance_m: float

    def format(self) -> str:
        edges_str = " → ".join(self.edge_ids)
        return (
            f"A* ROUTE\n"
            f"Start: {self.edge_ids[0]}\n"
            f"Destination: {self.edge_ids[-1]}\n\n"
            f"Edges:\n{edges_str}\n\n"
            f"Distance:\n{self.total_distance_m:.1f} m\n\n"
            f"Estimated travel time:\n{self.estimated_travel_time_s:.1f} s\n\n"
            f"Signal delay:\n{self.total_signal_delay_s:.1f} s\n\n"
            f"Congestion cost:\n{self.total_congestion_cost:.1f}\n\n"
            f"Total cost:\n{self.total_cost:.1f}"
        )


class AStarRouter:
    """
    A production-quality A* pathfinding engine that operates on the SUMO road network.
    Dynamically generates valid ambulance routes using traffic-aware edge costs.
    """

    def __init__(
        self,
        travel_time_weight: float = 1.0,
        congestion_weight: float = 1.0,
        halted_weight: float = 3.0,
        signal_delay_weight: float = 1.0,
        max_speed_mps: float = 25.0,
    ) -> None:
        # Default weights explanation:
        # travel_time_weight (1.0): Base time penalty. 1 unit of cost = 1 second.
        # congestion_weight (1.0): Penalty for edge occupancy and overall vehicle count. 
        # halted_weight (3.0): High penalty for completely stopped vehicles (blockages).
        # signal_delay_weight (1.0): Adds actual estimated signal waiting time directly in seconds.
        self.travel_time_weight = travel_time_weight
        self.congestion_weight = congestion_weight
        self.halted_weight = halted_weight
        self.signal_delay_weight = signal_delay_weight
        self.max_speed_mps = max_speed_mps

    def _heuristic(self, current_node_id: str, dest_node_id: str) -> float:
        """
        Admissible heuristic: straight-line Euclidean distance divided by max speed.
        
        Note on admissibility: Because our edge cost includes traffic penalties 
        and signal delays on top of pure travel time, the actual edge cost will 
        always be >= the pure free-flow travel time. Therefore, this Euclidean 
        free-flow heuristic systematically underestimates the true cost and 
        maintains admissibility for the A* search.
        """
        net = _get_network()
        try:
            n1 = net.getNode(current_node_id)
            n2 = net.getNode(dest_node_id)
            x1, y1 = n1.getCoord()
            x2, y2 = n2.getCoord()
            dist = math.dist((x1, y1), (x2, y2))
            return dist / self.max_speed_mps
        except Exception:
            return 0.0

    def _get_edge_traffic_cost(self, edge_id: str, edge_length: float, ambulance_speed_mps: float) -> tuple[float, float, float]:
        """
        Calculates travel time and congestion cost for a single edge.
        Returns (travel_time_s, congestion_cost, length)
        """
        try:
            (
                vehicle_count,
                halted_vehicle_count,
                mean_speed_kmh,
                occupancy_percent,
            ) = get_edge_traffic_features(edge_id)
        except Exception:
            vehicle_count = 0
            halted_vehicle_count = 0
            mean_speed_kmh = ambulance_speed_mps * 3.6
            occupancy_percent = 0.0

        mean_speed_mps = max(0.1, mean_speed_kmh / 3.6)
        
        # If vehicles are halted, ambulance will likely be restricted to traffic speed.
        # Otherwise, assume it can travel closer to its own speed.
        if halted_vehicle_count > 0:
            speed = min(ambulance_speed_mps, mean_speed_mps)
            speed = max(speed, 0.1)
        else:
            speed = max(ambulance_speed_mps, mean_speed_mps, 0.1)

        travel_time = edge_length / speed
        congestion_cost = (
            (vehicle_count * self.congestion_weight) +
            (halted_vehicle_count * self.halted_weight) +
            (occupancy_percent * 0.5 * self.congestion_weight)
        )
        
        return travel_time, congestion_cost, edge_length

    def find_route(
        self,
        start_edge: str,
        destination_edge: str,
        start_lane_position: float = 0.0,
        ambulance_speed_mps: float = 15.0,
    ) -> AStarRoute | None:
        """
        Execute A* pathfinding from start_edge to destination_edge.
        
        Limitation: start_lane_position reduces the travel time cost of the initial edge, 
        but does not change the congestion penalty scaling. This is a practical approximation 
        for partial edge traversal.
        """
        net = _get_network()

        try:
            start_e = net.getEdge(start_edge)
            dest_e = net.getEdge(destination_edge)
        except Exception as e:
            print(f"AStarRouter Error: Invalid start or destination edge. {e}")
            return None

        # Priority queue stores tuples: (f_score, g_score, edge_id)
        open_set = []
        heapq.heappush(open_set, (0.0, 0.0, start_edge))
        
        # tracking costs
        g_scores = {start_edge: 0.0}
        
        # tracking path
        came_from = {}
        
        # Additional tracking for final result reconstruction
        edge_metrics = {}
        
        dest_node_id = dest_e.getToNode().getID()

        # Calculate initial edge cost
        try:
            start_len = start_e.getLength()
            rem_len = max(0.0, start_len - start_lane_position)
        except Exception:
            rem_len = 100.0
            
        t_time, c_cost, _ = self._get_edge_traffic_cost(start_edge, rem_len, ambulance_speed_mps)
        init_cost = (t_time * self.travel_time_weight) + c_cost
        g_scores[start_edge] = init_cost
        
        edge_metrics[start_edge] = {
            "travel_time": t_time,
            "congestion": c_cost,
            "signal_delay": 0.0,
            "length": rem_len
        }

        # Update initial f_score
        initial_h = self._heuristic(start_e.getToNode().getID(), dest_node_id)
        open_set[0] = (init_cost + initial_h, init_cost, start_edge)

        closed_set = set()

        while open_set:
            _, current_g, current_edge = heapq.heappop(open_set)

            if current_edge in closed_set:
                continue
                
            closed_set.add(current_edge)

            if current_edge == destination_edge:
                # Path found, reconstruct
                return self._reconstruct_path(came_from, edge_metrics, current_edge)

            try:
                curr_e_obj = net.getEdge(current_edge)
                outgoing = curr_e_obj.getOutgoing().keys()
            except Exception:
                continue
                
            curr_to_node = curr_e_obj.getToNode().getID()

            for next_e_obj in outgoing:
                next_edge = next_e_obj.getID()
                
                # Filter out edges that don't allow emergency vehicles
                try:
                    if not next_e_obj.allows("emergency"):
                        continue
                except AttributeError:
                    pass
                    
                # Signal delay to transition
                try:
                    sig_delay = get_signal_delay(curr_to_node, current_edge, next_edge)
                except Exception:
                    sig_delay = 0.0
                
                # Next edge traversal cost
                try:
                    next_len = next_e_obj.getLength()
                except Exception:
                    next_len = 100.0
                    
                t_time, c_cost, _ = self._get_edge_traffic_cost(next_edge, next_len, ambulance_speed_mps)
                
                transition_cost = (
                    (sig_delay * self.signal_delay_weight) +
                    (t_time * self.travel_time_weight) +
                    c_cost
                )
                
                tentative_g = current_g + transition_cost
                
                if next_edge not in g_scores or tentative_g < g_scores[next_edge]:
                    g_scores[next_edge] = tentative_g
                    came_from[next_edge] = current_edge
                    
                    edge_metrics[next_edge] = {
                        "travel_time": t_time,
                        "congestion": c_cost,
                        "signal_delay": sig_delay,
                        "length": next_len
                    }
                    
                    next_to_node = next_e_obj.getToNode().getID()
                    h = self._heuristic(next_to_node, dest_node_id)
                    f = tentative_g + h
                    
                    heapq.heappush(open_set, (f, tentative_g, next_edge))

        # No path found
        return None

    def _reconstruct_path(
        self, 
        came_from: dict[str, str], 
        edge_metrics: dict[str, dict], 
        current_edge: str
    ) -> AStarRoute:
        
        path = [current_edge]
        while current_edge in came_from:
            current_edge = came_from[current_edge]
            path.append(current_edge)
            
        path.reverse()
        
        net = _get_network()
        node_ids = []
        for e in path:
            try:
                node_ids.append(net.getEdge(e).getToNode().getID())
            except Exception:
                pass
                
        total_travel_time = 0.0
        total_sig_delay = 0.0
        total_cong = 0.0
        total_dist = 0.0
        
        for e in path:
            metrics = edge_metrics.get(e, {})
            total_travel_time += metrics.get("travel_time", 0.0)
            total_sig_delay += metrics.get("signal_delay", 0.0)
            total_cong += metrics.get("congestion", 0.0)
            total_dist += metrics.get("length", 0.0)
            
        total_cost = (
            (total_travel_time * self.travel_time_weight) +
            (total_sig_delay * self.signal_delay_weight) +
            total_cong
        )
        
        return AStarRoute(
            edge_ids=path,
            node_ids=node_ids,
            total_cost=total_cost,
            estimated_travel_time_s=total_travel_time,
            total_signal_delay_s=total_sig_delay,
            total_congestion_cost=total_cong,
            total_distance_m=total_dist
        )