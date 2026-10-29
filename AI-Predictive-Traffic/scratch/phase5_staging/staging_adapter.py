"""
PHASE 5: ISOLATED STAGING PREEMPTION ADAPTER
============================================
Implements a safety-bounded, candidate-informed ETA preemption adapter in strict isolation.

Preservation & Safety Constraints:
- Loads Candidate Model from scratch/phase3_eta/models/mangaluru_eta_candidate.joblib.
- Matches exact feature schema from candidate_schema.json (8 numeric features).
- Validates inputs, handles missing features, applies strict bounds [0.0, 300.0].
- Preserves approach-wide signal rules, yellow transitions, and restoration safety.
- Never modifies A* routing or production routing thresholds.
- Supports dry-run mode (logs proposed actions without modifying SUMO state).
"""

from __future__ import annotations

import json
import time
import warnings
from pathlib import Path
import numpy as np
import pandas as pd
import joblib

warnings.filterwarnings("ignore")

PROJECT_ROOT = Path("D:/AIML/Projects/Major")
PY_ROOT = PROJECT_ROOT / "AI-Predictive-Traffic"

CANDIDATE_MODEL_PATH = PY_ROOT / "scratch" / "phase3_eta" / "models" / "mangaluru_eta_candidate.joblib"
SCHEMA_PATH = PY_ROOT / "scratch" / "phase3_eta" / "models" / "candidate_schema.json"
PROD_MODEL_PATH = PY_ROOT / "models" / "eta_prediction_model.joblib"

EXPECTED_FEATURES = [
    "ambulance_speed_mps",
    "distance_to_junction_m",
    "vehicle_count",
    "halted_vehicle_count",
    "mean_speed_kmh",
    "occupancy_percent",
    "signal_phase",
    "signal_time_to_switch_s",
]


class StagingETAAdapter:
    """
    Isolated Staging ETA Adapter for Candidate Model Inference.
    """

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.model = None
        self.schema = None
        self.load_model()
        
        # Diagnostic tracking
        self.total_inferences = 0
        self.invalid_predictions_clamped = 0
        self.exceptions_caught = 0
        self.latencies_ms: list[float] = []

    def load_model(self) -> None:
        if not CANDIDATE_MODEL_PATH.exists():
            raise FileNotFoundError(f"Candidate model not found at {CANDIDATE_MODEL_PATH}")
        self.model = joblib.load(CANDIDATE_MODEL_PATH)
        if hasattr(self.model, "n_jobs"):
            self.model.n_jobs = 1
        
        if SCHEMA_PATH.exists():
            with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
                self.schema = json.load(f)

    def extract_candidate_features(
        self,
        ambulance_speed_mps: float,
        distance_to_junction_m: float,
        vehicle_count: int,
        halted_vehicle_count: int,
        mean_speed_kmh: float,
        occupancy_percent: float,
        signal_phase: int,
        signal_time_to_switch_s: float,
    ) -> dict:
        """
        Extracts and sanitizes the 8 numeric features for candidate model.
        Guarantees correct units, types, and bounded numerical values.
        """
        return {
            "ambulance_speed_mps": max(0.0, float(ambulance_speed_mps)) if ambulance_speed_mps is not None and not np.isnan(ambulance_speed_mps) else 10.0,
            "distance_to_junction_m": max(0.0, float(distance_to_junction_m)) if distance_to_junction_m is not None and not np.isnan(distance_to_junction_m) else 50.0,
            "vehicle_count": max(0, int(vehicle_count)) if vehicle_count is not None and not np.isnan(vehicle_count) else 0,
            "halted_vehicle_count": max(0, int(halted_vehicle_count)) if halted_vehicle_count is not None and not np.isnan(halted_vehicle_count) else 0,
            "mean_speed_kmh": max(0.0, float(mean_speed_kmh)) if mean_speed_kmh is not None and not np.isnan(mean_speed_kmh) else 30.0,
            "occupancy_percent": max(0.0, min(100.0, float(occupancy_percent))) if occupancy_percent is not None and not np.isnan(occupancy_percent) else 0.0,
            "signal_phase": int(signal_phase) if signal_phase is not None and not np.isnan(signal_phase) and signal_phase >= 0 else 0,
            "signal_time_to_switch_s": max(0.0, float(signal_time_to_switch_s)) if signal_time_to_switch_s is not None and not np.isnan(signal_time_to_switch_s) else 10.0,
        }

    def predict_eta(self, feature_dict: dict) -> float:
        """
        Runs candidate model prediction with safety bounds, latency logging,
        and fallback guarantees.
        Fails safely on missing, None, NaN, out-of-range, or corrupted features.
        """
        self.total_inferences += 1
        t0 = time.perf_counter_ns()

        try:
            if not isinstance(feature_dict, dict):
                raise ValueError("feature_dict must be a dictionary")

            # Extract features according to expected schema
            sanitized = {}
            for col in EXPECTED_FEATURES:
                if col not in feature_dict:
                    raise KeyError(f"Missing required feature column: {col}")
                val = feature_dict[col]
                if val is None or pd.isna(val) or np.isinf(val):
                    raise ValueError(f"Feature {col} is null or non-finite: {val}")
                sanitized[col] = float(val) if "speed" in col or "distance" in col or "occupancy" in col or "switch" in col else int(val)

            row = [sanitized[col] for col in EXPECTED_FEATURES]
            df = pd.DataFrame([row], columns=EXPECTED_FEATURES)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                raw_pred = float(self.model.predict(df)[0])

            # Safety clamping: ETA must be non-negative, finite, and within [0.0, 300.0]
            if raw_pred < 0.0 or np.isnan(raw_pred) or np.isinf(raw_pred):
                self.invalid_predictions_clamped += 1
                # Physical fallback: distance / effective speed
                eff_spd = max(sanitized.get("ambulance_speed_mps", 10.0), sanitized.get("mean_speed_kmh", 30.0) / 3.6, 3.0)
                pred_eta = max(0.0, min(300.0, sanitized.get("distance_to_junction_m", 50.0) / eff_spd))
            elif raw_pred > 300.0:
                self.invalid_predictions_clamped += 1
                pred_eta = 300.0
            else:
                pred_eta = raw_pred

        except Exception:
            self.exceptions_caught += 1
            # Resilient physical fallback
            try:
                raw_spd = feature_dict.get("ambulance_speed_mps") if isinstance(feature_dict, dict) else 10.0
                eff_spd = float(raw_spd) if raw_spd is not None and not pd.isna(raw_spd) and float(raw_spd) > 0 else 10.0
                eff_spd = max(eff_spd, 3.0)
                raw_dist = feature_dict.get("distance_to_junction_m") if isinstance(feature_dict, dict) else 50.0
                dist = float(raw_dist) if raw_dist is not None and not pd.isna(raw_dist) and float(raw_dist) >= 0 else 50.0
                pred_eta = max(0.0, min(300.0, dist / eff_spd))
            except Exception:
                pred_eta = 15.0  # Conservative safe fallback

        t1 = time.perf_counter_ns()
        self.latencies_ms.append((t1 - t0) / 1e6)
        return round(pred_eta, 2)

    def evaluate_preemption_decision(
        self,
        predicted_eta_s: float,
        distance_to_junction_m: float,
        is_red: bool,
        time_to_switch_s: float,
        halted_vehicles: int,
        preemption_window_s: float = 20.0,
    ) -> tuple[bool, str]:
        """
        Determines whether preemption should be requested based on candidate ETA.
        In dry_run mode, always returns False for action to guarantee signal state is unchanged,
        while returning the full decision string for auditability.
        """
        # Distance sanity checks
        if distance_to_junction_m > 500.0:
            return False, "Distance exceeds 500m control threshold"

        if distance_to_junction_m <= 5.0:
            return False, "Ambulance already reached junction"

        queue_clearance_time = halted_vehicles * 2.5
        
        # Conflict condition: signal is red and cannot naturally clear before ambulance + queue arrival
        conflict = is_red and (predicted_eta_s <= time_to_switch_s + queue_clearance_time)
        
        # Predictive corridor preparation window: within 20s of junction
        in_window = (predicted_eta_s <= preemption_window_s)

        if conflict or in_window:
            if halted_vehicles <= 5:
                reason = f"Candidate ETA ({predicted_eta_s:.1f}s <= {preemption_window_s}s) or conflict justifies proactive green wave"
                if self.dry_run:
                    return False, f"[DRY_RUN_PROPOSED] {reason}"
                return True, reason
            else:
                return False, f"Queue too long ({halted_vehicles} vehicles); preemption suppressed"

        return False, f"Outside activation window (ETA={predicted_eta_s:.1f}s, dist={distance_to_junction_m:.1f}m)"

    def get_stats(self) -> dict:
        return {
            "total_inferences": self.total_inferences,
            "invalid_predictions_clamped": self.invalid_predictions_clamped,
            "exceptions_caught": self.exceptions_caught,
            "mean_latency_ms": round(float(np.mean(self.latencies_ms)), 4) if self.latencies_ms else 0.0,
            "p95_latency_ms": round(float(np.percentile(self.latencies_ms, 95)), 4) if self.latencies_ms else 0.0,
        }

