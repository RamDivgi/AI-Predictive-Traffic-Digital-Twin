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
        max_speed_mps: float = 42.0,
        queue_clearance_s_per_veh: float = 2.5,
    ) -> None:
        # Default weights explanation:
        # travel_time_weight (1.0): 1 unit of cost = 1 second of road traversal time.
        # congestion_weight (1.0): Weight modifier for traffic delay calculations.
        # halted_weight (3.0): Preserved for API backward compatibility.
        # signal_delay_weight (1.0): 1 unit of cost = 1 second of signal waiting time.
        # max_speed_mps (42.0): Maximum legal vehicle speed bound across the network in m/s (27.78 m/s * 1.5 speedFactor = 41.67 m/s).
        # queue_clearance_s_per_veh (2.5): Saturation flow discharge headway per halted vehicle in seconds.
        self.travel_time_weight = travel_time_weight
        self.congestion_weight = congestion_weight
        self.halted_weight = halted_weight
        self.signal_delay_weight = signal_delay_weight
        self.max_speed_mps = max_speed_mps
        self.queue_clearance_s_per_veh = queue_clearance_s_per_veh

    def _heuristic(self, current_node_id: str, dest_node_id: str) -> float:
        """
        Admissible Euclidean heuristic:
        h(n) = distance(n, dest) / max_speed_mps (strictly in seconds).
        
        Mathematical Proof of Admissibility & Optimality:
        In the Mangaluru network (presentation_selection2.net.xml), the maximum legal edge
        speed limit is 27.78 m/s (100 km/h). With the emergency vehicle speedFactor="1.5",
        the maximum possible vehicle speed on any edge is 27.78 * 1.5 = 41.67 m/s.
        By setting max_speed_mps >= 41.67 m/s (default 42.0 m/s), for any road edge e:
          C_e >= t_free = length(e) / v_free >= length(e) / max_speed_mps
        Because straight-line Euclidean distance dist(u, v) <= road path distance length(e):
          dist(u, dest) / max_speed_mps <= length(e) / max_speed_mps <= C_e
        Hence h(n) <= h*(n) for all nodes n, guaranteeing mathematical admissibility
        and optimality across all network edges and vehicle speed factors.
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

    def _get_edge_traffic_cost(
        self, 
        edge_id: str, 
        edge_length: float, 
        ambulance_speed_mps: float = 15.0
    ) -> tuple[float, float, float]:
        """
        Calculates travel time and congestion delay for an edge in SECONDS.

        1. Free-Flow Time (t_free):
           Base travel time on an empty road at legal speed limit / ambulance cruising capability:
           v_free = min(ambulance_speed_mps, speed_limit)
           t_free = edge_length / max(1.0, v_free)

        2. Speed-Depression Delay (slowdown_delay_s):
           Extra seconds required to traverse the edge due to reduced average cruising speed:
           If background traffic is moving at mean_speed_mps < v_free:
             v_eff = max(1.0, min(v_free, mean_speed_mps))
             t_moving = edge_length / v_eff
             slowdown_delay_s = max(0.0, t_moving - t_free)
           Otherwise 0.0s.

        3. Queue Dissipation Delay (queue_delay_s):
           Time penalty for queued / halted vehicles (v < 0.1 m/s) blocking the lane:
           In standard traffic engineering (HCM saturation flow headway), clearing each queued
           vehicle takes ~2.0 to 2.5s:
           queue_delay_s = halted_vehicle_count * self.queue_clearance_s_per_veh

        4. Total Congestion Delay (congestion_delay_s):
           congestion_delay_s = slowdown_delay_s + queue_delay_s (strictly in seconds).

        Returns:
           (t_free, congestion_delay_s, edge_length)
        """
        net = _get_network()
        speed_limit = ambulance_speed_mps
        try:
            e_obj = net.getEdge(edge_id)
            speed_limit = max(1.0, e_obj.getSpeed())
        except Exception:
            pass

        v_amb = max(5.0, ambulance_speed_mps)
        v_free = max(1.0, min(v_amb, speed_limit))
        t_free = max(0.05, edge_length / v_free)

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
            mean_speed_kmh = v_free * 3.6
            occupancy_percent = 0.0

        slowdown_delay_s = 0.0
        if vehicle_count > 0:
            mean_speed_mps = max(0.1, mean_speed_kmh / 3.6)
            if halted_vehicle_count > 0:
                v_eff = max(1.0, min(v_free, mean_speed_mps))
            else:
                friction = max(0.2, 1.0 - 0.005 * occupancy_percent)
                v_eff = max(2.0, min(v_free, max(mean_speed_mps, v_free * friction)))
            t_moving = edge_length / v_eff
            slowdown_delay_s = max(0.0, t_moving - t_free)

        queue_delay_s = halted_vehicle_count * self.queue_clearance_s_per_veh
        congestion_delay_s = slowdown_delay_s + queue_delay_s

        return t_free, congestion_delay_s, edge_length

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
        
        total_free_flow = 0.0
        total_sig_delay = 0.0
        total_cong = 0.0
        total_dist = 0.0
        
        for e in path:
            metrics = edge_metrics.get(e, {})
            total_free_flow += metrics.get("travel_time", 0.0)
            total_sig_delay += metrics.get("signal_delay", 0.0)
            total_cong += metrics.get("congestion", 0.0)
            total_dist += metrics.get("length", 0.0)
            
        total_road_time = total_free_flow + total_cong
        total_cost = (
            (total_road_time * self.travel_time_weight) +
            (total_sig_delay * self.signal_delay_weight)
        )
        
        return AStarRoute(
            edge_ids=path,
            node_ids=node_ids,
            total_cost=total_cost,
            estimated_travel_time_s=total_road_time,
            total_signal_delay_s=total_sig_delay,
            total_congestion_cost=total_cong,
            total_distance_m=total_dist
        )

    def evaluate_path(
        self,
        edge_ids: list[str],
        start_lane_position: float = 0.0,
        ambulance_speed_mps: float = 15.0,
    ) -> AStarRoute | None:
        """
        Evaluate an arbitrary edge sequence under the authoritative A* time-based cost model.
        Returns an AStarRoute with consistent travel time, signal delay, congestion, and total cost in seconds.
        """
        if not edge_ids:
            return None

        net = _get_network()
        node_ids = []
        total_free_flow = 0.0
        total_sig_delay = 0.0
        total_cong = 0.0
        total_dist = 0.0

        for i, edge_id in enumerate(edge_ids):
            try:
                e_obj = net.getEdge(edge_id)
                edge_len = e_obj.getLength()
                node_ids.append(e_obj.getToNode().getID())
            except Exception:
                edge_len = 100.0
                node_ids.append("unknown")

            rem_len = max(0.0, edge_len - start_lane_position) if i == 0 else edge_len

            t_time, c_cost, _ = self._get_edge_traffic_cost(edge_id, rem_len, ambulance_speed_mps)

            sig_delay = 0.0
            if i < len(edge_ids) - 1:
                next_edge = edge_ids[i + 1]
                try:
                    to_node = net.getEdge(edge_id).getToNode().getID()
                    sig_delay = get_signal_delay(to_node, edge_id, next_edge)
                except Exception:
                    sig_delay = 0.0

            total_free_flow += t_time
            total_cong += c_cost
            total_sig_delay += sig_delay
            total_dist += rem_len

        total_road_time = total_free_flow + total_cong
        total_cost = (
            (total_road_time * self.travel_time_weight) +
            (total_sig_delay * self.signal_delay_weight)
        )

        return AStarRoute(
            edge_ids=list(edge_ids),
            node_ids=node_ids,
            total_cost=total_cost,
            estimated_travel_time_s=total_road_time,
            total_signal_delay_s=total_sig_delay,
            total_congestion_cost=total_cong,
            total_distance_m=total_dist,
        )

    def _is_diverse(self, route1: AStarRoute, route2: AStarRoute, threshold: float = 0.85) -> bool:
        edges1 = set(route1.edge_ids)
        edges2 = set(route2.edge_ids)
        overlap = len(edges1.intersection(edges2))
        min_len = min(len(edges1), len(edges2))
        if min_len == 0:
            return False
        return (overlap / min_len) <= threshold

    def _find_route_penalized(
        self,
        start_edge: str,
        destination_edge: str,
        start_lane_position: float,
        ambulance_speed_mps: float,
        penalized_edges: set[str],
        penalty_cost: float = 10000.0
    ) -> AStarRoute | None:
        net = _get_network()
        try:
            start_e = net.getEdge(start_edge)
            dest_e = net.getEdge(destination_edge)
        except Exception:
            return None

        open_set = []
        heapq.heappush(open_set, (0.0, 0.0, start_edge))
        
        g_scores = {start_edge: 0.0}
        came_from = {}
        edge_metrics = {}
        
        dest_node_id = dest_e.getToNode().getID()

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

        initial_h = self._heuristic(start_e.getToNode().getID(), dest_node_id)
        open_set[0] = (init_cost + initial_h, init_cost, start_edge)

        closed_set = set()

        while open_set:
            _, current_g, current_edge = heapq.heappop(open_set)

            if current_edge in closed_set:
                continue
                
            closed_set.add(current_edge)

            if current_edge == destination_edge:
                return self._reconstruct_path(came_from, edge_metrics, current_edge)

            try:
                curr_e_obj = net.getEdge(current_edge)
                outgoing = curr_e_obj.getOutgoing().keys()
            except Exception:
                continue
                
            curr_to_node = curr_e_obj.getToNode().getID()

            for next_e_obj in outgoing:
                next_edge = next_e_obj.getID()
                
                try:
                    if not next_e_obj.allows("emergency"):
                        continue
                except AttributeError:
                    pass
                    
                try:
                    sig_delay = get_signal_delay(curr_to_node, current_edge, next_edge)
                except Exception:
                    sig_delay = 0.0
                
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
                
                if next_edge in penalized_edges:
                    transition_cost += penalty_cost
                
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

        return None

    def find_alternative_routes(
        self,
        start_edge: str,
        destination_edge: str,
        start_lane_position: float = 0.0,
        ambulance_speed_mps: float = 15.0,
    ) -> list[AStarRoute]:
        """
        Generates genuinely distinct and valid candidate routes.
        Validates topology, checks connectivity, eliminates cycles and duplicates,
        and scores all candidates under the consistent time-based cost function.
        """
        amb_speed = max(10.0, ambulance_speed_mps)
        primary_route = self.find_route(
            start_edge, destination_edge, start_lane_position, amb_speed
        )
        if not primary_route:
            return []
            
        net = _get_network()

        def is_valid_route(route: AStarRoute) -> bool:
            if not route or not route.edge_ids:
                return False
            if route.edge_ids[0] != start_edge or route.edge_ids[-1] != destination_edge:
                return False
            # Verify connectivity across all consecutive edges
            for i in range(len(route.edge_ids) - 1):
                u = route.edge_ids[i]
                v = route.edge_ids[i + 1]
                try:
                    u_obj = net.getEdge(u)
                    outgoing_ids = [e.getID() for e in u_obj.getOutgoing().keys()]
                    if v not in outgoing_ids:
                        return False
                except Exception:
                    return False
            return True

        if not is_valid_route(primary_route):
            return []

        routes = [primary_route]
        penalized_edges = set()
        seen_edge_tuples = {tuple(primary_route.edge_ids)}
        
        max_attempts = 10
        attempts = 0
        last_edges_to_penalize = primary_route.edge_ids[1:-1]
        
        while len(routes) < 4 and attempts < max_attempts:
            attempts += 1
            
            for edge in last_edges_to_penalize:
                penalized_edges.add(edge)
                
            candidate = self._find_route_penalized(
                start_edge, 
                destination_edge, 
                start_lane_position, 
                amb_speed,
                penalized_edges,
                penalty_cost=10000.0
            )
            
            if not candidate or not is_valid_route(candidate):
                break
                
            cand_tuple = tuple(candidate.edge_ids)
            if cand_tuple in seen_edge_tuples:
                continue

            is_diverse = True
            for accepted_route in routes:
                if not self._is_diverse(accepted_route, candidate, threshold=0.85):
                    is_diverse = False
                    break
                    
            if is_diverse:
                routes.append(candidate)
                seen_edge_tuples.add(cand_tuple)
                last_edges_to_penalize = candidate.edge_ids[1:-1]
            else:
                last_edges_to_penalize = candidate.edge_ids[1:-1]
                
        return routes