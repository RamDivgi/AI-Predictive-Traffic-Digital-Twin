from __future__ import annotations

from dataclasses import dataclass
import traci

from route_evaluator import (
    evaluate_route,
    RouteEvaluation,
    _get_edge_length_safe,
)
from astar_router import AStarRouter


@dataclass
class ReroutingStatus:
    initial_route_id: str | None
    current_route_id: str | None
    previous_route_id: str | None
    last_reroute_time: float | None
    reroute_count: int
    estimated_improvement_s: float


class ReroutingController:
    """
    Dynamic ambulance route-selection and rerouting decision layer.
    Integrates A* pathfinding with traffic-aware evaluation.
    """

    def __init__(
        self,
        min_improvement_s: float = 10.0,
        min_improvement_percent: float = 5.0,
        cooldown_s: float = 30.0,
        min_distance_to_dest_m: float = 150.0,
        ambulance_id: str = "ambulance",
    ) -> None:
        self.min_improvement_s = min_improvement_s
        self.min_improvement_percent = min_improvement_percent
        self.cooldown_s = cooldown_s
        self.min_distance_to_dest_m = min_distance_to_dest_m
        self.ambulance_id = ambulance_id

        self.last_reroute_time: float | None = None
        self.reroute_count: int = 0
        self.previous_route_id: str | None = None
        self.initial_route_id: str | None = None
        self.current_route_id: str | None = None
        self.estimated_improvement_s: float = 0.0
        
        self.astar_router = AStarRouter(
            travel_time_weight=1.0,
            congestion_weight=1.0,
            halted_weight=3.0,
            signal_delay_weight=1.0,
        )

    def reset(self) -> None:
        """
        Reset the controller state for a new simulation run.
        """
        self.last_reroute_time = None
        self.reroute_count = 0
        self.previous_route_id = None
        self.initial_route_id = None
        self.current_route_id = None
        self.estimated_improvement_s = 0.0

    def get_status(self) -> ReroutingStatus:
        """
        Return the current state of the rerouting controller.
        """
        return ReroutingStatus(
            initial_route_id=self.initial_route_id,
            current_route_id=self.current_route_id,
            previous_route_id=self.previous_route_id,
            last_reroute_time=self.last_reroute_time,
            reroute_count=self.reroute_count,
            estimated_improvement_s=self.estimated_improvement_s,
        )

    def evaluate_and_reroute(
        self,
        ml_etas: dict[str, float] | None = None,
    ) -> bool:
        """
        Evaluate candidate routes and trigger rerouting if justified.
        Returns True if the ambulance was rerouted, False otherwise.
        """

        vehicle_ids = traci.vehicle.getIDList()
        if self.ambulance_id not in vehicle_ids:
            return False

        current_time = traci.simulation.getTime()

        try:
            current_traci_route_id = traci.vehicle.getRouteID(self.ambulance_id)
            current_edges = list(traci.vehicle.getRoute(self.ambulance_id))
            current_edge = traci.vehicle.getRoadID(self.ambulance_id)
            current_lane_pos = traci.vehicle.getLanePosition(self.ambulance_id)
            ambulance_speed = traci.vehicle.getSpeed(self.ambulance_id)
            route_index = traci.vehicle.getRouteIndex(self.ambulance_id)
        except traci.TraCIException:
            return False

        if current_edge.startswith(":"):
            # Inside an intersection; defer rerouting until on a normal edge
            return False

        if route_index < 0 or not current_edges:
            return False

        if self.current_route_id != current_traci_route_id:
            self.current_route_id = current_traci_route_id
            if self.initial_route_id is None:
                self.initial_route_id = current_traci_route_id

        destination_edge = current_edges[-1]

        # Calculate remaining distance to destination
        remaining_distance = 0.0
        start_idx = current_edges.index(current_edge) if current_edge in current_edges else 0
        for i in range(start_idx, len(current_edges)):
            edge_len = _get_edge_length_safe(current_edges[i])
            if i == start_idx:
                remaining_distance += max(0.0, edge_len - current_lane_pos)
            else:
                remaining_distance += edge_len

        # -------------------------------------------------------------------
        # Define candidate routes
        # -------------------------------------------------------------------

        candidate_routes = []
        if current_edges:
            candidate_routes.append((self.current_route_id, current_edges))

        astar_route = self.astar_router.find_route(
            start_edge=current_edge,
            destination_edge=destination_edge,
            start_lane_position=current_lane_pos,
            ambulance_speed_mps=max(0.1, ambulance_speed),
        )

        astar_route_id = "astar_dynamic_route"
        is_same_route = False
        
        if astar_route is not None:
            remaining_current_edges = current_edges[start_idx:]
            if remaining_current_edges == astar_route.edge_ids:
                is_same_route = True
            else:
                candidate_routes.append((astar_route_id, astar_route.edge_ids))

        if not candidate_routes:
            return False

        # -------------------------------------------------------------------
        # Evaluate candidate routes
        # -------------------------------------------------------------------

        evaluations: dict[str, RouteEvaluation] = {}
        for r_id, r_edges in candidate_routes:
            eval_result = evaluate_route(
                route_id=r_id,
                route_edges=r_edges,
                current_edge=current_edge,
                current_lane_position=current_lane_pos,
                ambulance_speed_mps=max(0.1, ambulance_speed),
                ml_etas=ml_etas,
            )
            if eval_result is not None:
                evaluations[r_id] = eval_result

        if self.current_route_id not in evaluations:
            return False

        current_eval = evaluations[self.current_route_id]
        best_route_id = self.current_route_id
        best_eval = current_eval
        
        astar_eval = evaluations.get(astar_route_id)

        if astar_eval is not None and not is_same_route:
            if astar_eval.total_time_s < current_eval.total_time_s:
                best_route_id = astar_route_id
                best_eval = astar_eval

        improvement_s = current_eval.total_time_s - best_eval.total_time_s
        improvement_pct = 0.0
        if current_eval.total_time_s > 0:
            improvement_pct = (improvement_s / current_eval.total_time_s) * 100.0

        # -------------------------------------------------------------------
        # Print Evaluation
        # -------------------------------------------------------------------

        print("\n[A*]")
        print(f"Current route: {self.current_route_id}")
        
        if astar_route is not None:
            print(f"A* route: {' -> '.join(astar_route.edge_ids)}")
        else:
            print("A* route: None found")
            
        print(f"Current estimated ETA: {current_eval.total_time_s:.1f} s")
        
        if astar_eval is not None:
            print(f"A* estimated ETA: {astar_eval.total_time_s:.1f} s")
            print(f"Improvement: {improvement_s:.1f} s ({improvement_pct:.1f}%)")
        elif is_same_route:
            print(f"A* estimated ETA: {current_eval.total_time_s:.1f} s (Identical to current)")
            print("Improvement: 0.0 s (0.0%)")
        else:
            print("A* estimated ETA: N/A")
            print("Improvement: N/A")

        print("\n[REROUTING]")

        # -------------------------------------------------------------------
        # Rerouting Policy & Safeguards
        # -------------------------------------------------------------------

        should_reroute = False
        reason = ""

        # Oscillation prevention
        is_oscillation_risk = False
        if self.previous_route_id is not None and not self.previous_route_id.startswith("!") and best_route_id == astar_route_id and astar_route is not None:
            try:
                prev_edges = list(traci.route.getEdges(self.previous_route_id))
                if current_edge in prev_edges:
                    prev_rem = prev_edges[prev_edges.index(current_edge):]
                    if astar_route.edge_ids == prev_rem:
                        is_oscillation_risk = True
            except traci.TraCIException:
                pass
        
        req_improvement_s = self.min_improvement_s * (1.5 if is_oscillation_risk else 1.0)
        req_pct = self.min_improvement_percent * (1.5 if is_oscillation_risk else 1.0)

        if best_route_id == self.current_route_id:
            reason = "Current route is already the best."
        elif remaining_distance < self.min_distance_to_dest_m:
            reason = f"Too close to destination ({remaining_distance:.1f}m < {self.min_distance_to_dest_m}m)."
        elif self.last_reroute_time is not None and (current_time - self.last_reroute_time) < self.cooldown_s:
            reason = f"Rerouting cooldown active ({(current_time - self.last_reroute_time):.1f}s < {self.cooldown_s}s)."
        elif improvement_s < req_improvement_s:
            reason = f"Improvement ({improvement_s:.1f}s) is below threshold ({req_improvement_s:.1f}s)."
        elif improvement_pct < req_pct:
            reason = f"Improvement ({improvement_pct:.1f}%) is below threshold ({req_pct:.1f}%)."
        else:
            should_reroute = True
            if is_oscillation_risk:
                reason = "Rerouting justified despite oscillation risk (strict thresholds met)."
            else:
                reason = "Rerouting justified by significant ETA improvement."

        print(f"Reroute decision: {'YES' if should_reroute else 'NO'}")
        print(f"Reason: {reason}\n")

        # -------------------------------------------------------------------
        # Apply Reroute
        # -------------------------------------------------------------------

        if should_reroute:
            try:
                unique_route_id = f"dynamic_astar_{int(current_time)}_{self.reroute_count}"
                traci.route.add(unique_route_id, best_eval.route_edges)
                traci.vehicle.setRouteID(self.ambulance_id, unique_route_id)
                
                self.previous_route_id = self.current_route_id
                self.current_route_id = unique_route_id
                self.last_reroute_time = current_time
                self.reroute_count += 1
                self.estimated_improvement_s = improvement_s
                return True
            except traci.TraCIException as e:
                print(f"Failed to apply reroute in TraCI: {e}")
                return False

        return False
