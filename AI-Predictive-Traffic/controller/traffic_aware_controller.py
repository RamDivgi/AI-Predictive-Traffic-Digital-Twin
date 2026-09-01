from __future__ import annotations

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
    is_movement_signal_unfavorable,
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
    """
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
    """

    def __init__(
        self,
        model_path: Path = config.MODEL_FILE,
    ) -> None:

        if not model_path.exists():
            raise FileNotFoundError(
                f"ETA prediction model not found:\n{model_path}"
            )

        self.model = joblib.load(model_path)

        # --------------------------------------------------------------
        # PERFORMANCE FIX
        # --------------------------------------------------------------
        # The ETA model is evaluated repeatedly during a real-time
        # TraCI loop. If the underlying RandomForest uses multiple
        # workers, joblib creates parallel worker overhead for every
        # single-row prediction.
        #
        # For real-time single-row inference, one worker is faster and
        # avoids the joblib parallel-processing slowdown.
        # --------------------------------------------------------------

        self._configure_model_for_realtime_inference()

        self.signal_controller = SignalController()
        
        # Initialize hospital manager
        self.hospital_manager = HospitalManager(str(config.NET_FILE), str(config.HOSPITALS_FILE))
        self.destination_hospital = self.hospital_manager.get_default_hospital()
        
        self.control_egress = ControlEgress(use_mqtt=True)
        
        self.rerouting_controller = ReroutingController(
            min_improvement_s=config.REROUTE_MIN_IMPROVEMENT_S,
            min_improvement_percent=config.REROUTE_MIN_IMPROVEMENT_PERCENT,
            cooldown_s=config.REROUTE_COOLDOWN_S,
            min_distance_to_dest_m=config.REROUTE_MIN_DISTANCE_TO_DEST_M,
            ambulance_id=config.AMBULANCE_ID,
        )
        self.last_reroute_evaluation_time = -1.0
        self.reroute_evaluation_interval_s = config.REROUTE_EVALUATION_INTERVAL_S
        self.active_movements: dict[
            str,
            tuple[str, str],
        ] = {}

        # Cache predictions within the same SUMO simulation step.
        self._prediction_cache: dict[
            tuple,
            float,
        ] = {}

        self._last_prediction_time: float | None = None
        
        self.state = "NORMAL"
        self.current_junction_id = None
        self.route_logged = False

    # ------------------------------------------------------------------
    # MODEL CONFIGURATION
    # ------------------------------------------------------------------

    def set_hospital_destination(self, hospital_id: str):
        hospital = self.hospital_manager.get_hospital(hospital_id)
        if hospital and hospital.nearest_edge:
            self.destination_hospital = hospital
            try:
                # ---------------------------------------------------------
                # AMBULANCE ROUTING - CRITICAL
                # Calculate the route exactly ONCE and lock it.
                # ---------------------------------------------------------
                current_edge = traci.vehicle.getRoadID(config.AMBULANCE_ID)
                current_pos = traci.vehicle.getLanePosition(config.AMBULANCE_ID)
                current_speed = traci.vehicle.getSpeed(config.AMBULANCE_ID)
                
                # If inside junction, use the next edge (or just start from where we are)
                if current_edge.startswith(":"):
                    route = traci.vehicle.getRoute(config.AMBULANCE_ID)
                    idx = traci.vehicle.getRouteIndex(config.AMBULANCE_ID)
                    if idx + 1 < len(route):
                        current_edge = route[idx + 1]
                
                astar_route = self.rerouting_controller.astar_router.find_route(
                    start_edge=current_edge,
                    destination_edge=hospital.nearest_edge,
                    start_lane_position=current_pos,
                    ambulance_speed_mps=max(0.1, current_speed)
                )
                
                if astar_route is not None:
                    # Apply fixed route ONCE
                    unique_route_id = f"fixed_astar_{hospital_id}_{int(traci.simulation.getTime())}"
                    traci.route.add(unique_route_id, astar_route.edge_ids)
                    traci.vehicle.setRouteID(config.AMBULANCE_ID, unique_route_id)
                    print(f"[HOSPITAL_SELECTED] Route calculated ONCE to {hospital.name} and locked.")
                else:
                    print(f"[ERROR] A* could not find a path to the hospital.")
                    
                self.rerouting_controller.reset()
                self.last_reroute_evaluation_time = -1.0
                return True
            except traci.exceptions.TraCIException as e:
                print(f"[ERROR] Failed to update hospital destination: {e}")
        return False
    def _configure_model_for_realtime_inference(self) -> None:
        """
        Configure supported tree-based estimators for efficient
        single-row real-time inference.

        The saved model may be either a direct estimator or a sklearn
        Pipeline containing the estimator as its final step.
        """

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
        """
        Predict ambulance arrival time using the trained ML model.

        Prediction is cached for the current SUMO simulation step so
        that the same feature vector is not unnecessarily evaluated
        multiple times.
        """

        current_simulation_time = (
            traci.simulation.getTime()
        )

        # Clear the cache whenever SUMO advances to a new step.
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
            round(
                features.ambulance_distance_m,
                3,
            ),
            round(
                features.ambulance_speed_mps,
                3,
            ),
            features.vehicle_count,
            features.halted_vehicle_count,
            round(
                features.mean_speed_kmh,
                3,
            ),
            round(
                features.occupancy_percent,
                3,
            ),
            features.signal_phase,
            round(
                features.signal_time_to_switch_s,
                3,
            ),
        )

        cached_prediction = (
            self._prediction_cache.get(
                cache_key
            )
        )

        if cached_prediction is not None:
            return cached_prediction

        row = pd.DataFrame(
            [
                {
                    "ambulance_speed_mps": (
                        features.ambulance_speed_mps
                    ),
                    "ambulance_speed_kmh": (
                        features.ambulance_speed_mps
                        * 3.6
                    ),
                    "distance_to_junction_m": (
                        features.ambulance_distance_m
                    ),
                    "vehicle_count": (
                        features.vehicle_count
                    ),
                    "halted_vehicle_count": (
                        features.halted_vehicle_count
                    ),
                    "mean_speed_kmh": (
                        features.mean_speed_kmh
                    ),
                    "occupancy_percent": (
                        features.occupancy_percent
                    ),
                    "signal_phase": (
                        features.signal_phase
                    ),
                    "signal_time_to_switch_s": (
                        features.signal_time_to_switch_s
                    ),
                    "junction_id": (
                        features.junction_id
                    ),
                    "incoming_edge": (
                        features.incoming_edge
                    ),
                    "outgoing_edge": (
                        features.outgoing_edge
                    ),
                    "traffic_scenario": "normal",
                }
            ]
        )

        prediction = float(
            self.model.predict(row)[0]
        )

        prediction = max(
            0.0,
            prediction,
        )

        self._prediction_cache[
            cache_key
        ] = prediction

        return prediction

    # ------------------------------------------------------------------
    # Feature preparation with ML ETA
    # ------------------------------------------------------------------

    def build_ml_features(
        self,
        junction,
    ) -> TrafficFeatures | None:
        """
        Build real-time traffic features and replace the baseline
        ETA with the trained ML prediction.
        """

        try:
            current_speed = (
                traci.vehicle.getSpeed(
                    config.AMBULANCE_ID
                )
            )

        except traci.TraCIException:
            return None

        if current_speed < 0.0:
            current_speed = 0.0

        class ETAInput:
            distance_m = (
                junction.distance_from_ambulance_m
            )

            estimated_travel_seconds = (
                max(
                    junction.distance_from_ambulance_m
                    / max(
                        current_speed,
                        0.1,
                    ),
                    0.0,
                )
            )

        features = build_traffic_features(
            junction,
            ETAInput(),
        )

        ml_eta = self.predict_eta(
            features
        )

        features.ambulance_eta_s = ml_eta

        return features

    # ------------------------------------------------------------------
    # SIGNAL PREEMPTION
    # ------------------------------------------------------------------

    def activate_preemption(
        self,
        features: TrafficFeatures,
    ) -> bool:
        """
        Activate SUMO signal preemption for the ambulance movement.
        """

        original_junction_id = features.junction_id

        tls_id, signal_indices = (
            signal_mapping.get_tls_and_indices_for_movement(
                features.incoming_edge,
                features.outgoing_edge,
            )
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
            return False

        self.control_egress.emit_preempt(
            tls_id,
            features.incoming_edge,
            features.outgoing_edge,
            signal_indices
        )

        activated = (
            self.signal_controller.preempt(
                junction_id=tls_id,
                signal_indices=signal_indices,
                hold_seconds=config.PREEMPTION_HOLD_SECONDS,
            )
        )

        if activated:
            self.active_movements[tls_id] = (
                features.incoming_edge,
                features.outgoing_edge,
            )

            print(
                f"[PREEMPTION_ACTIVATED] GREEN movement: {features.incoming_edge} -> {features.outgoing_edge} at {tls_id}"
            )
            print(f"[QUEUE_CLEARING] Preparing to clear {features.halted_vehicle_count} vehicles")

        return activated

    # ------------------------------------------------------------------
    # RESTORATION
    # ------------------------------------------------------------------

    def restore_cleared_junctions(
        self,
    ) -> None:
        """
        Restore signals after the ambulance clears the junction.
        """

        for (
            tls_id,
            movement,
        ) in list(
            self.active_movements.items()
        ):

            incoming_edge, _ = movement

            restored = (
                self.signal_controller
                .release_if_cleared(
                    tls_id,
                    incoming_edge,
                )
            )

            if restored:

                print(
                    f"[AMBULANCE_PASSED] Passed {tls_id}"
                )
                print(
                    f"[SIGNAL_RECOVERED] {tls_id} returned to normal signal program"
                )
                
                self.state = "RESTORING"
                
                self.control_egress.emit_restore(tls_id)

                self.active_movements.pop(
                    tls_id,
                    None,
                )


    # ------------------------------------------------------------------
    # RECALCULATION EXCEPTION
    # ------------------------------------------------------------------

    def route_is_impossible(self) -> bool:
        """
        Check if the assigned route becomes genuinely unreachable.
        """
        try:
            if config.AMBULANCE_ID not in traci.vehicle.getIDList():
                return False
                
            route_edges = traci.vehicle.getRoute(config.AMBULANCE_ID)
            if not route_edges:
                print("[REROUTE_EXCEPTION] Route is empty/disconnected.")
                return True
                
            current_speed = traci.vehicle.getSpeed(config.AMBULANCE_ID)
            current_time = traci.simulation.getTime()
            
            if current_speed < 0.1:
                if getattr(self, "_stationary_start", None) is None:
                    self._stationary_start = current_time
                elif current_time - self._stationary_start > 30.0:
                    tls_info = traci.vehicle.getNextTLS(config.AMBULANCE_ID)
                    if tls_info and tls_info[0][2] < 20.0:
                        # Waiting at TLS, not an impossible route
                        pass
                    else:
                        print(f"[REROUTE_EXCEPTION] Ambulance stuck for >30s, not at a traffic signal. Recalculating.")
                        self._stationary_start = None
                        return True
            else:
                self._stationary_start = None
                
            return False
        except traci.TraCIException:
            print("[REROUTE_EXCEPTION] TraCI Exception evaluating route.")
            return True

    # ------------------------------------------------------------------
    # MAIN CONTROL STEP
    # ------------------------------------------------------------------

    def process_step(
        self,
    ) -> list[
        tuple[
            TrafficFeatures,
            TrafficAwareDecision,
        ]
    ]:
        """
        Process the current SUMO simulation step.
        """

        vehicle_ids = (
            traci.vehicle.getIDList()
        )

        if len(vehicle_ids) > 120:
            print(f"[WARNING] Global vehicle count ({len(vehicle_ids)}) exceeds the strict ceiling of 120 vehicles.")

        if (
            config.AMBULANCE_ID
            not in vehicle_ids
        ):

            self.restore_cleared_junctions()
            self.signal_controller.process_step()
            self.rerouting_controller.reset()
            self.last_reroute_evaluation_time = -1.0
            self.route_logged = False
            self.state = "NORMAL"
            self.current_junction_id = None

            return []

        if not self.route_logged:
            try:
                route = traci.vehicle.getRoute(config.AMBULANCE_ID)
                if len(route) > 0:
                    print(f"[ROUTE_SELECTED] Ambulance dispatched.")
                    self.route_logged = True
            except traci.TraCIException:
                pass

        self.restore_cleared_junctions()
        self.signal_controller.process_step()
        
        current_time = traci.simulation.getTime()
        
        # ------------------------------------------------------------------
        # MODE DISTINCTION
        # ------------------------------------------------------------------
        try:
            is_emergency = traci.vehicle.getParameter(config.AMBULANCE_ID, "emergency") == "true"
        except traci.TraCIException:
            is_emergency = True
            
        current_mode = "EMERGENCY" if is_emergency else "NON-EMERGENCY"
        if getattr(self, "_last_mode", None) != current_mode:
            print(f"[MODE_TRANSITION] Mode switched to {current_mode}")
            self._last_mode = current_mode

        # ------------------------------------------------------------------
        # REROUTING EXCEPTION CHECK
        # ------------------------------------------------------------------
        if self.route_is_impossible():
            print("[ROUTE_EXCEPTION] Route is impossible. Triggering one-time recalculation.")
            # Trigger rerouting only once because it's impossible
            self.rerouting_controller.evaluate_and_reroute(ml_etas=None)
            status = self.rerouting_controller.get_status()
            self.control_egress.emit_reroute(config.AMBULANCE_ID, status.initial_route_id, status.current_route_id)

        # ------------------------------------------------------------------
        # UPCOMING JUNCTIONS & PREEMPTION STATE MACHINE
        # ------------------------------------------------------------------
        # ALWAYS called after potential rerouting so it uses the updated route
        junctions = (
            get_upcoming_junctions(
                config.MAX_JUNCTIONS
            )
        )

        if not junctions:
            return []

        if not is_emergency:
            return [] # Non-Emergency Mode: passive transit only

        decisions = []
        
        # We only want ONE active preemption target at a time.
        # Find if we already have an active (PREEMPTING, PASSING, etc.) junction
        active_target = None
        for j_id in self.signal_controller.get_active_preemptions():
            active_target = j_id
            break

        for next_junction in junctions:
            features = self.build_ml_features(next_junction)
            if features is not None:
                decision_str = "NONE"
                should_preempt = False
                
                # Hybrid Preemption/Rerouting Decision Engine
                # 1. Spatial distance horizon filter (150m)
                if features.ambulance_distance_m <= 150.0:
                    import signal_mapping
                    tls_id, _ = signal_mapping.get_tls_and_indices_for_movement(features.incoming_edge, features.outgoing_edge)
                    
                    if tls_id:
                        queue_len = features.halted_vehicle_count
                        queue_clearance_time = queue_len * 2.5
                        is_red = is_movement_signal_unfavorable(features)
                        
                        # 2. Conflict Trigger
                        conflict = is_red and (features.ambulance_eta_s <= features.signal_time_to_switch_s + queue_clearance_time)
                        
                        if conflict:
                            # 3. Two-Tier Hierarchy
                            if queue_len <= 5:
                                # Rerouting forbidden. Proactive Signal Preemption.
                                decision_str = "PREEMPT"
                                should_preempt = True
                                if active_target is None or active_target == tls_id:
                                    if not self.signal_controller.is_preempted(tls_id):
                                        activated = self.activate_preemption(features)
                                        if activated:
                                            active_target = tls_id
                            else:
                                # Signal preemption bypassed. Trigger A* dynamic rerouting.
                                decision_str = "REROUTE"
                                did_reroute = self.rerouting_controller.evaluate_and_reroute(ml_etas=None)
                                if did_reroute:
                                    status = self.rerouting_controller.get_status()
                                    self.control_egress.emit_reroute(config.AMBULANCE_ID, status.initial_route_id, status.current_route_id)
                        
                        # Log approach transitions
                        if not hasattr(self, 'last_logged_eta_times'):
                            self.last_logged_eta_times = {}
                        last_logged = self.last_logged_eta_times.get(tls_id, 0)
                        
                        if current_time - last_logged >= 3.0:
                            print(f"[{current_mode}] Dist: {features.ambulance_distance_m:.1f}m | Q: {queue_len} | ML ETA: {features.ambulance_eta_s:.1f}s | Dec: {decision_str}")
                            self.last_logged_eta_times[tls_id] = current_time

                decision = TrafficAwareDecision(
                    should_preempt=should_preempt,
                    priority_score=100.0 if should_preempt else 0.0,
                    reason=f"Hybrid Engine: {decision_str}",
                    eta_s=getattr(features, 'ambulance_eta_s', None)
                )
                decisions.append((features, decision))

        return decisions

    # ------------------------------------------------------------------
    # CLEANUP
    # ------------------------------------------------------------------

    def shutdown(
        self,
    ) -> None:
        """
        Restore every signal controlled by this controller and reset routing state.
        """

        self.signal_controller.restore_all()

        self.active_movements.clear()

        self._prediction_cache.clear()
        self._last_prediction_time = None
        
        self.rerouting_controller.reset()
        self.last_reroute_evaluation_time = -1.0