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
)
import signal_mapping
from signal_controller import SignalController
from rerouting_controller import ReroutingController

import sys
import os
PROJECT_ROOT = Path(__file__).resolve().parent.parent
twin_path = str(PROJECT_ROOT / "twin")
if twin_path not in sys.path:
    sys.path.append(twin_path)
from control_egress import ControlEgress


MODEL_FILE = (
    PROJECT_ROOT
    / "models"
    / "eta_prediction_model.joblib"
)

AMBULANCE_ID = "ambulance"

MAX_JUNCTIONS = 3
PREEMPTION_THRESHOLD = 40.0
PREEMPTION_HOLD_SECONDS = 8.0


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
        model_path: Path = MODEL_FILE,
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
        
        self.control_egress = ControlEgress(use_mqtt=True)
        
        self.rerouting_controller = ReroutingController(
            min_improvement_s=10.0,
            min_improvement_percent=5.0,
            cooldown_s=30.0,
            min_distance_to_dest_m=150.0,
            ambulance_id=AMBULANCE_ID,
        )
        self.last_reroute_evaluation_time = -1.0
        self.reroute_evaluation_interval_s = 5.0

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

    # ------------------------------------------------------------------
    # MODEL CONFIGURATION
    # ------------------------------------------------------------------

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
                    AMBULANCE_ID
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
                hold_seconds=PREEMPTION_HOLD_SECONDS,
            )
        )

        if activated:
            self.active_movements[tls_id] = (
                features.incoming_edge,
                features.outgoing_edge,
            )

            print(
                f"*** PREEMPTION ACTIVATED *** | "
                f"Junction {original_junction_id} (TLS: {tls_id}) | "
                f"Movement "
                f"{features.incoming_edge} -> "
                f"{features.outgoing_edge} | "
                f"Signal indices: "
                f"{signal_indices}"
            )

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
                    f"*** PREEMPTION RESTORED *** | "
                    f"Junction/TLS {tls_id}"
                )
                
                self.control_egress.emit_restore(tls_id)

                self.active_movements.pop(
                    tls_id,
                    None,
                )

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

        if (
            AMBULANCE_ID
            not in vehicle_ids
        ):

            self.restore_cleared_junctions()
            self.rerouting_controller.reset()
            self.last_reroute_evaluation_time = -1.0

            return []

        self.restore_cleared_junctions()
        
        current_time = traci.simulation.getTime()
        
        # ------------------------------------------------------------------
        # DYNAMIC REROUTING
        # ------------------------------------------------------------------
        if (
            current_time - self.last_reroute_evaluation_time 
            >= self.reroute_evaluation_interval_s
        ):
            self.last_reroute_evaluation_time = current_time
            
            # The rerouting controller evaluates candidate routes and 
            # injects the best route directly into TraCI if justified.
            pre_count = self.rerouting_controller.get_status().reroute_count
            self.rerouting_controller.evaluate_and_reroute(ml_etas=None)
            status = self.rerouting_controller.get_status()
            if status.reroute_count > pre_count:
                self.control_egress.emit_reroute(AMBULANCE_ID, status.initial_route_id, status.current_route_id)

        # ------------------------------------------------------------------
        # UPCOMING JUNCTIONS
        # ------------------------------------------------------------------
        # ALWAYS called after potential rerouting so it uses the updated route
        junctions = (
            get_upcoming_junctions(
                MAX_JUNCTIONS
            )
        )

        if not junctions:
            return []

        decisions = []

        for junction in junctions:

            features = (
                self.build_ml_features(
                    junction
                )
            )

            if features is None:
                continue

            decision = (
                decide_traffic_aware_preemption(
                    features,
                    minimum_score=(
                        PREEMPTION_THRESHOLD
                    ),
                )
            )

            print(
                format_traffic_features(
                    features
                )
            )

            print(
                format_decision(
                    decision
                )
            )

            if decision.should_preempt:

                self.activate_preemption(
                    features
                )

            decisions.append(
                (
                    features,
                    decision,
                )
            )

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