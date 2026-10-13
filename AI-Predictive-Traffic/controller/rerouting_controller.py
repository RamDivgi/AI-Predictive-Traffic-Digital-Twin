from __future__ import annotations

from dataclasses import dataclass
import traci

import config
from route_evaluator import (
    evaluate_route,
    RouteEvaluation,
    _get_edge_length_safe,
)
from astar_router import AStarRouter, AStarRoute


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
        min_improvement_s: float = config.REROUTE_MIN_IMPROVEMENT_S,
        min_improvement_percent: float = config.REROUTE_MIN_IMPROVEMENT_PERCENT,
        cooldown_s: float = config.REROUTE_COOLDOWN_S,
        min_distance_to_dest_m: float = config.REROUTE_MIN_DISTANCE_TO_DEST_M,
        ambulance_id: str = config.AMBULANCE_ID,
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
            max_speed_mps=42.0,
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
        ambulance_id: str | None = None,
        ml_etas: dict[str, float] | None = None,
    ) -> bool:
        """
        Evaluate candidate routes and trigger rerouting if justified.
        Returns True if the ambulance was rerouted, False otherwise.
        """
        target_id = ambulance_id if ambulance_id is not None else self.ambulance_id

        try:
            vehicle_ids = traci.vehicle.getIDList()
        except Exception:
            return False

        if target_id not in vehicle_ids:
            return False

        current_time = 0.0
        try:
            current_time = traci.simulation.getTime()
        except Exception:
            pass

        try:
            current_traci_route_id = traci.vehicle.getRouteID(target_id)
            current_edges = list(traci.vehicle.getRoute(target_id))
            current_edge = traci.vehicle.getRoadID(target_id)
            current_lane_pos = traci.vehicle.getLanePosition(target_id)
            ambulance_speed = traci.vehicle.getSpeed(target_id)
            route_index = traci.vehicle.getRouteIndex(target_id)
        except Exception:
            return False

        # Guardrail 1: Internal junction edges
        if current_edge.startswith(":"):
            # Inside an intersection; defer rerouting until on a normal edge
            return False

        # Guardrail 2: Route connectivity and current edge presence
        if route_index < 0 or not current_edges:
            return False

        if current_edge not in current_edges:
            return False

        if self.current_route_id != current_traci_route_id:
            self.current_route_id = current_traci_route_id
            if self.initial_route_id is None:
                self.initial_route_id = current_traci_route_id

        start_idx = current_edges.index(current_edge)
        remaining_current_edges = current_edges[start_idx:]
        destination_edge = current_edges[-1]

        # Guardrail 3: Already at destination edge
        if current_edge == destination_edge:
            return False

        # Guardrail 4: Minimum distance to destination threshold
        remaining_distance = max(0.0, _get_edge_length_safe(current_edge) - current_lane_pos)
        for e in remaining_current_edges[1:]:
            remaining_distance += _get_edge_length_safe(e)

        if remaining_distance < self.min_distance_to_dest_m:
            return False

        # Guardrail 5: Cooldown check
        if self.last_reroute_time is not None and (current_time - self.last_reroute_time) < self.cooldown_s:
            return False

        # -------------------------------------------------------------------
        # Route Evaluation under consistent A* time-based cost model
        # -------------------------------------------------------------------
        effective_speed = max(15.0, ambulance_speed)

        # 1. Evaluate remaining current route
        curr_route_eval = self.astar_router.evaluate_path(
            edge_ids=remaining_current_edges,
            start_lane_position=current_lane_pos,
            ambulance_speed_mps=effective_speed,
        )
        if curr_route_eval is None:
            return False

        current_eta = curr_route_eval.total_cost

        # 2. Find best alternative route from current position
        astar_route = self.astar_router.find_route(
            start_edge=current_edge,
            destination_edge=destination_edge,
            start_lane_position=current_lane_pos,
            ambulance_speed_mps=effective_speed,
        )

        if astar_route is None:
            return False

        is_same_route = (astar_route.edge_ids == remaining_current_edges)
        alt_eta = astar_route.total_cost

        improvement_s = current_eta - alt_eta
        improvement_pct = 0.0
        if current_eta > 0:
            improvement_pct = (improvement_s / current_eta) * 100.0

        # -------------------------------------------------------------------
        # Print Evaluation
        # -------------------------------------------------------------------
        print("\n[A*]")
        print(f"Current route: {self.current_route_id}")
        print(f"A* route: {' -> '.join(astar_route.edge_ids)}")
        print(f"Current estimated ETA: {current_eta:.1f} s")
        
        if not is_same_route:
            print(f"A* estimated ETA: {alt_eta:.1f} s")
            print(f"Improvement: {improvement_s:.1f} s ({improvement_pct:.1f}%)")
        else:
            print(f"A* estimated ETA: {current_eta:.1f} s (Identical to current)")
            print("Improvement: 0.0 s (0.0%)")

        print("\n[REROUTING]")

        # -------------------------------------------------------------------
        # Rerouting Policy, Oscillation Safeguard & Decision
        # -------------------------------------------------------------------
        should_reroute = False
        reason = ""

        # Oscillation prevention
        is_oscillation_risk = False
        if (
            self.previous_route_id is not None
            and not self.previous_route_id.startswith("!")
            and not is_same_route
        ):
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

        if is_same_route:
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
                reason = f"Rerouting justified by significant ETA improvement ({improvement_s:.1f}s saved, {improvement_pct:.1f}%)."

        print(f"Reroute decision: {'YES' if should_reroute else 'NO'}")
        print(f"Reason: {reason}\n")

        # -------------------------------------------------------------------
        # Apply Reroute in TraCI
        # -------------------------------------------------------------------
        if should_reroute:
            try:
                self.reroute_count += 1
                unique_route_id = f"dynamic_astar_{int(current_time)}_{self.reroute_count}"
                traci.route.add(unique_route_id, astar_route.edge_ids)
                traci.vehicle.setRouteID(target_id, unique_route_id)
                
                self.previous_route_id = self.current_route_id
                self.current_route_id = unique_route_id
                self.last_reroute_time = current_time
                self.estimated_improvement_s = improvement_s

                print(f"[REROUTE_APPLIED]")
                print(f"Ambulance: {target_id} at sim_time {current_time:.1f}s")
                print(f"Previous Route: {' -> '.join(remaining_current_edges)}")
                print(f"New Route: {' -> '.join(astar_route.edge_ids)}")
                print(f"Time Saved: {improvement_s:.1f}s ({improvement_pct:.1f}%)")
                print(f"TraCI Route ID: {unique_route_id} (ASSIGNED_SUCCESSFULLY)\n")
                return True
            except traci.TraCIException as e:
                print(f"[REROUTING_ERROR] Failed to apply reroute in TraCI: {e}")
                return False

        return False
