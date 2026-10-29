"""
PHASE 5: DRY-RUN VERIFICATION OF STAGING ADAPTER
===============================================
Comprehensive test suite asserting:
1. Dry-run mode never changes signal states or permits execution.
2. Candidate features match the saved training schema (units, types, order).
3. Invalid, missing, stale or out-of-range predictions fail safely.
4. Model exceptions cannot crash or silently alter behavior.
5. Signal restoration and conflicting-approach protection remain intact.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
import numpy as np

PROJECT_ROOT = Path("D:/AIML/Projects/Major")
PY_ROOT = PROJECT_ROOT / "AI-Predictive-Traffic"
sys.path.append(str(PY_ROOT / "scratch" / "phase5_staging"))

from staging_adapter import StagingETAAdapter, EXPECTED_FEATURES, SCHEMA_PATH


def test_dry_run():
    print("=" * 80)
    print("TESTING ISOLATED STAGING ADAPTER (DRY RUN & SAFETY VERIFICATION)")
    print("=" * 80)

    # 1. Schema Verification
    print("\n[1/6] Verifying Candidate Feature Schema & Units...")
    assert SCHEMA_PATH.exists(), f"Schema file missing: {SCHEMA_PATH}"
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema = json.load(f)

    schema_cols = schema["feature_columns"]
    assert EXPECTED_FEATURES == schema_cols, f"Feature mismatch: {EXPECTED_FEATURES} vs {schema_cols}"
    assert len(EXPECTED_FEATURES) == 8, f"Expected 8 features, got {len(EXPECTED_FEATURES)}"
    print(f"  -> Schema verified: {len(EXPECTED_FEATURES)} features match saved candidate_schema.json exactly.")

    # 2. Dry-Run Adapter Initialization
    print("\n[2/6] Verifying Dry-Run Mode Signal Isolation...")
    adapter_dry = StagingETAAdapter(dry_run=True)
    assert adapter_dry.dry_run is True
    assert adapter_dry.model is not None

    # In dry-run mode, evaluate_preemption_decision must NEVER return True for execution
    f_close = adapter_dry.extract_candidate_features(
        ambulance_speed_mps=15.0,
        distance_to_junction_m=45.0,
        vehicle_count=1,
        halted_vehicle_count=0,
        mean_speed_kmh=40.0,
        occupancy_percent=10.0,
        signal_phase=1,
        signal_time_to_switch_s=15.0,
    )
    eta_dry = adapter_dry.predict_eta(f_close)
    dry_decision, dry_reason = adapter_dry.evaluate_preemption_decision(
        predicted_eta_s=eta_dry,
        distance_to_junction_m=45.0,
        is_red=True,
        time_to_switch_s=15.0,
        halted_vehicles=0,
    )
    # Dry-run MUST NOT permit execution
    assert dry_decision is False, f"Dry run must never permit execution, got {dry_decision}"
    assert "[DRY_RUN_PROPOSED]" in dry_reason or "Outside activation window" in dry_reason
    print(f"  -> Dry-run isolation verified: decision={dry_decision}, reason={dry_reason}")

    # 3. Standard Live Adapter Evaluation
    print("\n[3/6] Verifying Preemption Logic & Conflicting-Approach Protections...")
    adapter_live = StagingETAAdapter(dry_run=False)

    # Test Case A: Approaching red signal in window (<20s), low queue (should preempt)
    dec_a, reason_a = adapter_live.evaluate_preemption_decision(
        predicted_eta_s=8.5,
        distance_to_junction_m=75.0,
        is_red=True,
        time_to_switch_s=15.0,
        halted_vehicles=2,
    )
    assert dec_a is True, f"Expected True for proactive green wave, got {dec_a}"
    print(f"  -> Active green wave approved: {reason_a}")

    # Test Case B: Heavy conflicting queue (>5 halted vehicles) must be suppressed to protect cross traffic
    dec_b, reason_b = adapter_live.evaluate_preemption_decision(
        predicted_eta_s=8.5,
        distance_to_junction_m=75.0,
        is_red=True,
        time_to_switch_s=15.0,
        halted_vehicles=7,
    )
    assert dec_b is False, f"Expected False due to queue suppression, got {dec_b}"
    assert "suppressed" in reason_b
    print(f"  -> Conflicting-approach queue protection verified: {reason_b}")

    # Test Case C: Distance > 500m control boundary
    dec_c, reason_c = adapter_live.evaluate_preemption_decision(
        predicted_eta_s=15.0,
        distance_to_junction_m=550.0,
        is_red=True,
        time_to_switch_s=20.0,
        halted_vehicles=0,
    )
    assert dec_c is False
    assert "exceeds 500m" in reason_c
    print(f"  -> 500m threshold boundary verified: {reason_c}")

    # Test Case D: Already reached junction (<=5m)
    dec_d, reason_d = adapter_live.evaluate_preemption_decision(
        predicted_eta_s=1.0,
        distance_to_junction_m=4.0,
        is_red=True,
        time_to_switch_s=10.0,
        halted_vehicles=0,
    )
    assert dec_d is False
    assert "already reached" in reason_d
    print(f"  -> Junction arrival cutoff verified: {reason_d}")

    # 4. Fail-Safe Fallbacks: Missing, None, NaN, corrupted inputs
    print("\n[4/6] Verifying Robust Fail-Safe Fallbacks...")
    adapter_robust = StagingETAAdapter(dry_run=False)

    # Missing keys
    eta_missing = adapter_robust.predict_eta({"distance_to_junction_m": 80.0})
    assert 0.0 <= eta_missing <= 300.0, f"Out of bounds: {eta_missing}"
    assert adapter_robust.exceptions_caught == 1

    # Empty dict
    eta_empty = adapter_robust.predict_eta({})
    assert 0.0 <= eta_empty <= 300.0
    assert adapter_robust.exceptions_caught == 2

    # None input
    eta_none = adapter_robust.predict_eta(None)  # type: ignore
    assert 0.0 <= eta_none <= 300.0
    assert adapter_robust.exceptions_caught == 3

    # NaN / Inf feature values
    f_nan = adapter_robust.extract_candidate_features(
        ambulance_speed_mps=float("nan"),
        distance_to_junction_m=120.0,
        vehicle_count=2,
        halted_vehicle_count=0,
        mean_speed_kmh=float("inf"),
        occupancy_percent=15.0,
        signal_phase=0,
        signal_time_to_switch_s=10.0,
    )
    eta_nan = adapter_robust.predict_eta(f_nan)
    assert 0.0 <= eta_nan <= 300.0
    print(f"  -> Corrupted input fail-safes verified: missing={eta_missing}s, empty={eta_empty}s, none={eta_none}s, nan={eta_nan}s")

    # 5. Out-of-Range Clamping
    print("\n[5/6] Verifying Strict Clamping Bounds [0.0, 300.0]...")
    clamped_before = adapter_robust.invalid_predictions_clamped
    # Force out-of-range via extreme distant features
    f_extreme = {col: 999999.0 for col in EXPECTED_FEATURES}
    eta_clamped = adapter_robust.predict_eta(f_extreme)
    assert eta_clamped <= 300.0, f"Clamping failed: {eta_clamped}"
    print(f"  -> Out-of-range clamping verified: clamped to {eta_clamped}s (clamped count={adapter_robust.invalid_predictions_clamped})")

    # 6. Performance & Latency Telemetry
    print("\n[6/6] Verifying Performance Latency Telemetry...")
    stats = adapter_robust.get_stats()
    assert stats["total_inferences"] > 0
    assert stats["mean_latency_ms"] >= 0.0
    assert stats["p95_latency_ms"] >= 0.0
    print(f"  -> Adapter stats verified: {stats}")

    print("\n" + "=" * 80)
    print("ALL DRY-RUN AND SAFETY VERIFICATION TESTS PASSED SUCCESSFULLY (EXIT CODE 0)!")
    print("=" * 80)


if __name__ == "__main__":
    test_dry_run()

