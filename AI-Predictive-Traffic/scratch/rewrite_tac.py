import os
import re

file_path = "D:\\AIML\\Projects\\Major\\AI-Predictive-Traffic\\controller\\traffic_aware_controller.py"
with open(file_path, "r") as f:
    content = f.read()

# I will write the complete updated version of the file.
new_content = """from __future__ import annotations

from pathlib import Path

import joblib
import pandas as pd
import traci

from junction_detector import get_upcoming_junctions
from traffic_features import (
    TrafficFeatures,
    build_traffic_features,
    format_traffic_features,
)
from preemption_decision import (
    TrafficAwareDecision,
    decide_traffic_aware_preemption,
    format_decision,
)
import signal_mapping
from signal_controller import SignalController
from rerouting_controller import ReroutingController
from hospital_manager import HospitalManager
import config

import sys
import os
PROJECT_ROOT = Path(__file__).resolve().parent.parent
twin_path = str(PROJECT_ROOT / "twin")
if twin_path not in sys.path:
    sys.path.append(twin_path)
from control_egress import ControlEgress


class TrafficAwareController:
    \"\"\"
    End-to-end predictive traffic controller.

    Pipeline:

        A* Route Generation
              ↓
        Traffic-aware route evaluation
              ↓
        Dynamic rerouting
              ↓
        Junction detection
              ↓
        Traffic features
              ↓
        ML ETA prediction
              ↓
        Traffic-aware decision
              ↓
        Signal preemption
              ↓
        Automatic restoration
    \"\"\"

    def __init__(
        self,
        model_path: Path = config.MODEL_FILE,
    ) -> None:

        if not model_path.exists():
            raise FileNotFoundError(
                f"ETA prediction model not found:\\n{model_path}"
            )

        self.model = joblib.load(model_path)

        # --------------------------------------------------------------
        # PERFORMANCE FIX
        # --------------------------------------------------------------
        self._configure_model_for_realtime_inference()

        self.signal_controller = SignalController()
        
        # Initialize hospital manager
        self.hospital_manager = HospitalManager(str(config.NET_FILE), str(config.HOSPITALS_FILE))
        self.destination_hospital = self.hospital_manager.get_default_hospital()
        
        self.control_egress = ControlEgress(use_mqtt=True)
        
        # Track rerouting controller per ambulance
        self.rerouting_controllers: dict[str, ReroutingController] = {}
        
        self.active_movements: dict[
            str,
            tuple[str, str, str],
        ] = {}

        # Cache predictions within the same SUMO simulation step.
        self._prediction_cache: dict[
            tuple,
            float,
        ] = {}

        self._last_prediction_time: float | None = None
        
        self.state = "NORMAL"
        self.route_logged = {}
        self.last_logged_eta_times = {}

    def get_rerouting_controller(self, ambulance_id: str) -> ReroutingController:
        if ambulance_id not in self.rerouting_controllers:
            self.rerouting_controllers[ambulance_id] = ReroutingController(
                min_improvement_s=config.REROUTE_MIN_IMPROVEMENT_S,
                min_improvement_percent=config.REROUTE_MIN_IMPROVEMENT_PERCENT,
                cooldown_s=config.REROUTE_COOLDOWN_S,
                min_distance_to_dest_m=config.REROUTE_MIN_DISTANCE_TO_DEST_M,
                ambulance_id=ambulance_id,
            )
        return self.rerouting_controllers[ambulance_id]

    # ------------------------------------------------------------------
    # MODEL CONFIGURATION
    # ------------------------------------------------------------------

    def set_hospital_destination(self, hospital_id: str, ambulance_id: str = config.AMBULANCE_ID):
        hospital = self.hospital_manager.get_hospital(hospital_id)
        if hospital and hospital.nearest_edge:
            self.destination_hospital = hospital
            try:
                # ---------------------------------------------------------
                # AMBULANCE ROUTING - CRITICAL
                # Calculate the route exactly ONCE and lock it.
                # ---------------------------------------------------------
                current_edge = traci.vehicle.getRoadID(ambulance_id)
                current_pos = traci.vehicle.getLanePosition(ambulance_id)
                current_speed = traci.vehicle.getSpeed(ambulance_id)
                
                # If inside junction, use the next edge (or just start from where we are)
                if current_edge.startswith(":"):
                    route = traci.vehicle.getRoute(ambulance_id)
                    idx = traci.vehicle.getRouteIndex(ambulance_id)
                    if idx + 1 < len(route):
                        current_edge = route[idx + 1]
                
                rc = self.get_rerouting_controller(ambulance_id)
                astar_route = rc.astar_router.find_route(
                    start_edge=current_edge,
                    destination_edge=hospital.nearest_edge,
                    start_lane_position=current_pos,
                    ambulance_speed_mps=max(0.1, current_speed)
                )
                
                if astar_route is not None:
                    # Apply fixed route ONCE
                    unique_route_id = f"fixed_astar_{hospital_id}_{int(traci.simulation.getTime())}"
                    traci.route.add(unique_route_id, astar_route.edge_ids)
                    traci.vehicle.setRouteID(ambulance_id, unique_route_id)
                    print(f"[HOSPITAL_SELECTED] Route calculated ONCE to {hospital.name} and locked for {ambulance_id}.")
                else:
                    print(f"[ERROR] A* could not find a path to the hospital for {ambulance_id}.")
                    
                rc.reset()
                return True
            except traci.exceptions.TraCIException as e:
                print(f"[ERROR] Failed to update hospital destination: {e}")
        return False

    def _configure_model_for_realtime_inference(self) -> None:
        estimators = []
        if hasattr(self.model, "steps"):
            try:
                estimators.append(
                    self.model.steps[-1][1]
                )
            except (IndexError, TypeError):
                pass
        estimators.append(self.model)
        for estimator in estimators:
            if hasattr(estimator, "n_jobs"):
                try:
                    estimator.set_params(
                        n_jobs=1
                    )
                except (ValueError, TypeError):
                    pass

    # ------------------------------------------------------------------
    # ML ETA
    # ------------------------------------------------------------------

    def predict_eta(
        self,
        features: TrafficFeatures,
    ) -> float:
        current_simulation_time = (
            traci.simulation.getTime()
        )

        if (
            self._last_prediction_time is None
            or current_simulation_time
            != self._last_prediction_time
        ):
            self._prediction_cache.clear()
            self._last_prediction_time = (
                current_simulation_time
            )

        cache_key = (
            features.junction_id,
            features.incoming_edge,
            features.outgoing_edge,
            round(features.ambulance_distance_m, 3),
            round(features.ambulance_speed_mps, 3),
            features.vehicle_count,
            features.halted_vehicle_count,
            round(features.mean_speed_kmh, 3),
            round(features.occupancy_percent, 3),
            features.signal_phase,
            round(features.signal_time_to_switch_s, 3),
        )

        cached_prediction = self._prediction_cache.get(cache_key)
        if cached_prediction is not None:
            return cached_prediction

        row = pd.DataFrame(
            [
                {
                    "ambulance_speed_mps": features.ambulance_speed_mps,
                    "ambulance_speed_kmh": features.ambulance_speed_mps * 3.6,
                    "distance_to_junction_m": features.ambulance_distance_m,
                    "vehicle_count": features.vehicle_count,
                    "halted_vehicle_count": features.halted_vehicle_count,
                    "mean_speed_kmh": features.mean_speed_kmh,
                    "occupancy_percent": features.occupancy_percent,
                    "signal_phase": features.signal_phase,
                    "signal_time_to_switch_s": features.signal_time_to_switch_s,
                    "junction_id": features.junction_id,
                    "incoming_edge": features.incoming_edge,
                    "outgoing_edge": features.outgoing_edge,
                    "traffic_scenario": "normal",
                }
            ]
        )

        prediction = float(self.model.predict(row)[0])
        prediction = max(0.0, prediction)
        self._prediction_cache[cache_key] = prediction
        return prediction

    # ------------------------------------------------------------------
    # Feature preparation with ML ETA
    # ------------------------------------------------------------------

    def build_ml_features(
        self,
        junction,
        ambulance_id: str,
    ) -> TrafficFeatures | None:
        try:
            current_speed = traci.vehicle.getSpeed(ambulance_id)
        except traci.TraCIException:
            return None

        if current_speed < 0.0:
            current_speed = 0.0

        class ETAInput:
            distance_m = junction.distance_from_ambulance_m
            estimated_travel_seconds = max(
                junction.distance_from_ambulance_m / max(current_speed, 0.1),
                0.0,
            )

        features = build_traffic_features(
            junction,
            ETAInput(),
        )

        ml_eta = self.predict_eta(features)
        features.ambulance_eta_s = ml_eta
        return features

    # ------------------------------------------------------------------
    # SIGNAL PREEMPTION
    # ------------------------------------------------------------------

    def activate_preemption(
        self,
        features: TrafficFeatures,
        ambulance_id: str,
    ) -> bool:
        original_junction_id = features.junction_id
        tls_id, signal_indices = signal_mapping.get_tls_and_indices_for_movement(
            features.incoming_edge,
            features.outgoing_edge,
        )
        if not tls_id or not signal_indices:
            print(
                f"WARNING: No signal mapping for "
                f"{original_junction_id} | "
                f"{features.incoming_edge} -> "
                f"{features.outgoing_edge}"
            )
            return False

        if self.signal_controller.is_preempted(tls_id):
            # If already preempted by THIS ambulance, keep it. If by another, handled by priority manager.
            record = self.signal_controller.get_preemption_record(tls_id)
            if record and record.ambulance_id == ambulance_id:
                return True
            return False

        self.control_egress.emit_preempt(
            tls_id,
            features.incoming_edge,
            features.outgoing_edge,
            signal_indices
        )

        activated = self.signal_controller.preempt(
            junction_id=tls_id,
            signal_indices=signal_indices,
            hold_seconds=config.PREEMPTION_HOLD_SECONDS,
            ambulance_id=ambulance_id,
        )

        if activated:
            self.active_movements[tls_id] = (
                features.incoming_edge,
                features.outgoing_edge,
                ambulance_id,
            )
            print(
                f"[PREEMPTION_ACTIVATED] GREEN movement: {features.incoming_edge} -> {features.outgoing_edge} at {tls_id} for {ambulance_id}"
            )

        return activated

    # ------------------------------------------------------------------
    # RESTORATION
    # ------------------------------------------------------------------

    def restore_cleared_junctions(self, active_ambulances: list[str]) -> None:
        for tls_id, movement in list(self.active_movements.items()):
            incoming_edge, _, ambulance_id = movement
            
            # If the ambulance doesn't exist anymore, release the junction
            if ambulance_id not in active_ambulances:
                self.signal_controller.restore(tls_id)
                self.control_egress.emit_restore(tls_id)
                self.active_movements.pop(tls_id, None)
                continue

            restored = self.signal_controller.release_if_cleared(
                tls_id,
                incoming_edge,
                ambulance_id,
            )

            if restored:
                print(f"[AMBULANCE_PASSED] {ambulance_id} passed {tls_id}")
                print(f"[SIGNAL_RECOVERED] {tls_id} returned to normal signal program")
                self.state = "RESTORING"
                self.control_egress.emit_restore(tls_id)
                self.active_movements.pop(tls_id, None)


    # ------------------------------------------------------------------
    # RECALCULATION EXCEPTION
    # ------------------------------------------------------------------

    def route_is_impossible(self, ambulance_id: str) -> bool:
        try:
            if ambulance_id not in traci.vehicle.getIDList():
                return False
                
            route_edges = traci.vehicle.getRoute(ambulance_id)
            if not route_edges:
                print(f"[REROUTE_EXCEPTION] Route is empty/disconnected for {ambulance_id}.")
                return True
                
            current_speed = traci.vehicle.getSpeed(ambulance_id)
            current_time = traci.simulation.getTime()
            
            if not hasattr(self, "_stationary_start"):
                self._stationary_start = {}
                
            if current_speed < 0.1:
                if self._stationary_start.get(ambulance_id) is None:
                    self._stationary_start[ambulance_id] = current_time
                elif current_time - self._stationary_start[ambulance_id] > 30.0:
                    tls_info = traci.vehicle.getNextTLS(ambulance_id)
                    if tls_info and tls_info[0][2] < 20.0:
                        pass
                    else:
                        print(f"[REROUTE_EXCEPTION] {ambulance_id} stuck for >30s, not at a traffic signal. Recalculating.")
                        self._stationary_start[ambulance_id] = None
                        return True
            else:
                self._stationary_start[ambulance_id] = None
                
            return False
        except traci.TraCIException:
            print(f"[REROUTE_EXCEPTION] TraCI Exception evaluating route for {ambulance_id}.")
            return True

    # ------------------------------------------------------------------
    # MAIN CONTROL STEP
    # ------------------------------------------------------------------

    def process_step(self):
        vehicle_ids = traci.vehicle.getIDList()
        emergency_vehicles = []
        for vid in vehicle_ids:
            try:
                # Detect ambulance and its emergency state
                v_type = traci.vehicle.getTypeID(vid)
                v_class = traci.vehicle.getVehicleClass(vid)
                if v_type == "ambulance" or v_class == "emergency":
                    is_emergency = traci.vehicle.getParameter(vid, "emergency")
                    if is_emergency == "true":
                        emergency_vehicles.append(vid)
            except traci.TraCIException:
                pass

        self.restore_cleared_junctions(emergency_vehicles)
        self.signal_controller.process_step()
        
        if not emergency_vehicles:
            return []
            
        current_time = traci.simulation.getTime()
        
        preemption_requests = []

        for amb_id in emergency_vehicles:
            if amb_id not in self.route_logged or not self.route_logged[amb_id]:
                try:
                    route = traci.vehicle.getRoute(amb_id)
                    if len(route) > 0:
                        print(f"[AMBULANCE DETECTED]")
                        print(f"ID: {amb_id}")
                        print(f"Emergency: TRUE")
                        self.route_logged[amb_id] = True
                except traci.TraCIException:
                    pass

            # Rerouting exception check
            if self.route_is_impossible(amb_id):
                print(f"[ROUTE_EXCEPTION] Route is impossible for {amb_id}. Triggering one-time recalculation.")
                rc = self.get_rerouting_controller(amb_id)
                rc.evaluate_and_reroute(ambulance_id=amb_id, ml_etas=None)
                status = rc.get_status()
                self.control_egress.emit_reroute(amb_id, status.initial_route_id, status.current_route_id)

            # Evaluate upcoming junctions along route
            # Note: get_upcoming_junctions implicitly relies on AMBULANCE_ID in junction_detector.py right now.
            # We must override it if multiple ambulances. But for now, we'll patch junction_detector to accept ambulance_id.
            import junction_detector
            junctions = junction_detector.get_upcoming_junctions(config.MAX_JUNCTIONS, ambulance_id=amb_id)
            
            if not junctions:
                continue

            for next_junction in junctions:
                features = self.build_ml_features(next_junction, ambulance_id=amb_id)
                if features is not None:
                    # Predictive Logic
                    tls_id, _ = signal_mapping.get_tls_and_indices_for_movement(features.incoming_edge, features.outgoing_edge)
                    if tls_id:
                        snapshot = self.signal_controller.capture_snapshot(tls_id)
                        queue_len = features.halted_vehicle_count
                        
                        # Queue clearance estimate (approx 2.5 seconds per vehicle + start delay)
                        queue_clearance_time = queue_len * 2.5 + 2.0 if queue_len > 0 else 0.0
                        eta = features.ambulance_eta_s
                        
                        # ----------------------------------------------------
                        # QUEUE > 5 : Evaluate Rerouting
                        # ----------------------------------------------------
                        if queue_len > 5:
                            # Evaluate rerouting but do not necessarily preempt instantly if we reroute
                            print(f"[CONGESTION DETECTED] Queue = {queue_len} at {tls_id} for {amb_id}. Evaluating rerouting.")
                            rc = self.get_rerouting_controller(amb_id)
                            rerouted = rc.evaluate_and_reroute(ambulance_id=amb_id, ml_etas=None)
                            if rerouted:
                                status = rc.get_status()
                                self.control_egress.emit_reroute(amb_id, status.initial_route_id, status.current_route_id)
                                print(f"[DECISION] Preemption: FALSE, Rerouting: TRUE for {amb_id}. Severe congestion.")
                                # If rerouted, we shouldn't preempt this old junction, break out.
                                break 
                        
                        # ----------------------------------------------------
                        # PREEMPTION DECISION : Predict Future Conflict
                        # ----------------------------------------------------
                        # Determine if ambulance will hit a red light or queue
                        is_conflict = False
                        predicted_delay = 0.0
                        
                        if snapshot:
                            # Assuming state string index 0 represents our movement for simplicity of prediction, 
                            # though signal_indices is accurate. We just check phase_remaining.
                            # A real predictive check would simulate the phase cycle, but here we assume:
                            
                            # If signal is currently red for our movement:
                            # We don't have direct access to 'is_green_for_us' without parsing indices, let's assume worst case if not preempted
                            is_currently_green = self.signal_controller.is_preempted(tls_id) # if we preempted, it's green
                            
                            if not is_currently_green:
                                # We predict conflict if ETA < (Remaining Phase + Queue Clearance)
                                predicted_delay = snapshot.phase_remaining + queue_clearance_time
                                if eta < predicted_delay + 5.0: # 5s buffer
                                    is_conflict = True
                            else:
                                # Already preempted, but we should maintain it if needed
                                is_conflict = True
                        else:
                            # No snapshot, fallback to basic ETA vs queue clearance
                            if eta < queue_clearance_time + 10.0:
                                is_conflict = True
                                predicted_delay = queue_clearance_time
                                
                        if is_conflict:
                            # Log decision once in a while
                            last_logged = self.last_logged_eta_times.get((amb_id, tls_id), 0)
                            if current_time - last_logged >= 5.0:
                                print(f"\\n[JUNCTION PREDICTION]")
                                print(f"Junction: {tls_id}")
                                print(f"Queue: {queue_len} vehicles")
                                print(f"Queue clearance estimate: {queue_clearance_time:.1f}s")
                                print(f"Ambulance ETA: {eta:.1f}s")
                                print(f"Predicted delay without intervention: {predicted_delay:.1f}s")
                                print(f"\\n[DECISION]")
                                print(f"Preemption required: TRUE")
                                print(f"Reason: Predicted ambulance delay ({predicted_delay:.1f}s) conflicts with ETA ({eta:.1f}s) for {amb_id}.")
                                self.last_logged_eta_times[(amb_id, tls_id)] = current_time

                            preemption_requests.append({
                                'tls_id': tls_id,
                                'features': features,
                                'amb_id': amb_id,
                                'eta': eta
                            })

        # ------------------------------------------------------------------
        # PRIORITY MANAGER (Handle conflicting requests safely)
        # ------------------------------------------------------------------
        # Group requests by junction
        requests_by_junction = {}
        for req in preemption_requests:
            tls_id = req['tls_id']
            if tls_id not in requests_by_junction:
                requests_by_junction[tls_id] = []
            requests_by_junction[tls_id].append(req)
            
        for tls_id, reqs in requests_by_junction.items():
            # If multiple ambulances request the same junction
            # Prioritize by ETA (lowest first)
            reqs.sort(key=lambda x: x['eta'])
            
            # Select the most urgent request
            primary_req = reqs[0]
            
            # Check if this junction is already actively preempted by someone else
            current_record = self.signal_controller.get_preemption_record(tls_id)
            if current_record:
                if current_record.ambulance_id == primary_req['amb_id']:
                    # Already preempted for this ambulance, keep it
                    pass
                else:
                    # Preempted by another ambulance.
                    # We should NOT override immediately to prevent oscillation.
                    # Only override if the other ambulance has cleared (which release_if_cleared handles).
                    pass
            else:
                # Issue new preemption
                self.activate_preemption(primary_req['features'], primary_req['amb_id'])

        return []

    # ------------------------------------------------------------------
    # CLEANUP
    # ------------------------------------------------------------------

    def shutdown(self) -> None:
        self.signal_controller.restore_all()
        self.active_movements.clear()
        self._prediction_cache.clear()
        self._last_prediction_time = None
        for rc in self.rerouting_controllers.values():
            rc.reset()
"""

with open(file_path, "w", encoding="utf-8") as f:
    f.write(new_content)

print(f"Successfully rewritten {file_path}")
