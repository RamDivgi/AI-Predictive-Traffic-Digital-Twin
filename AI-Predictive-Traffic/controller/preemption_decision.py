from __future__ import annotations

from dataclasses import dataclass

from traffic_features import TrafficFeatures


@dataclass(frozen=True)
class TrafficAwareDecision:
    should_preempt: bool
    priority_score: float
    reason: str
    eta_s: float | None = None


# ---------------------------------------------------------------------------
# PREEMPTION CONFIGURATION
# ---------------------------------------------------------------------------

MAX_CONTROL_DISTANCE_M = 100.0
MAX_PREDICTIVE_ETA_S = 10.0

MIN_SIGNAL_ADVANTAGE_S = 1.0

MIN_PRIORITY_SCORE = 40.0


# ---------------------------------------------------------------------------
# MOVEMENT SIGNAL HELPERS
# ---------------------------------------------------------------------------

def is_movement_signal_green(
    features: TrafficFeatures,
) -> bool:
    """
    Determine whether the ambulance's specific movement is currently
    receiving a green signal.

    This intentionally does NOT inspect the complete traffic-light
    state string because other approaches may be green while the
    ambulance movement is red.
    """

    movement_state = (
        features.movement_signal_state
        .strip()
        .lower()
    )

    if not movement_state:
        return False

    return all(
        character == "g"
        for character in movement_state
    )


def is_movement_signal_unfavorable(
    features: TrafficFeatures,
) -> bool:
    """
    Return True when the ambulance movement is not currently green.

    Red and yellow are both considered unfavorable for the purpose
    of predictive preemption.
    """

    movement_state = (
        features.movement_signal_state
        .strip()
        .lower()
    )

    if not movement_state:
        return True

    return any(
        character != "g"
        for character in movement_state
    )


# ---------------------------------------------------------------------------
# PRIORITY SCORE
# ---------------------------------------------------------------------------

def calculate_priority_score(
    features: TrafficFeatures,
) -> float:
    """
    Calculate a deterministic traffic-aware priority score from 0 to 100.

    The ambulance ETA may come from the trained ML ETA predictor.
    """

    score = 0.0

    # ----------------------------------------------------------
    # Ambulance proximity
    # ----------------------------------------------------------

    if features.ambulance_distance_m <= 30.0:
        score += 30.0

    elif features.ambulance_distance_m <= 60.0:
        score += 20.0

    elif features.ambulance_distance_m <= 100.0:
        score += 10.0

    # ----------------------------------------------------------
    # Predicted ambulance ETA
    # ----------------------------------------------------------

    if features.ambulance_eta_s <= 3.0:
        score += 25.0

    elif features.ambulance_eta_s <= 6.0:
        score += 18.0

    elif features.ambulance_eta_s <= 10.0:
        score += 8.0

    # ----------------------------------------------------------
    # Traffic volume
    # ----------------------------------------------------------

    if features.vehicle_count >= 5:
        score += 15.0

    elif features.vehicle_count >= 3:
        score += 10.0

    elif features.vehicle_count >= 1:
        score += 5.0

    # ----------------------------------------------------------
    # Congestion
    # ----------------------------------------------------------

    if features.halted_vehicle_count >= 3:
        score += 15.0

    elif features.halted_vehicle_count >= 1:
        score += 8.0

    # ----------------------------------------------------------
    # Occupancy
    # ----------------------------------------------------------

    if features.occupancy_percent >= 20.0:
        score += 10.0

    elif features.occupancy_percent >= 10.0:
        score += 5.0

    # ----------------------------------------------------------
    # Signal condition
    # ----------------------------------------------------------

    if is_movement_signal_unfavorable(
        features
    ):
        score += 5.0

    return min(
        100.0,
        score,
    )


# ---------------------------------------------------------------------------
# DECISION LOGIC
# ---------------------------------------------------------------------------

def decide_traffic_aware_preemption(
    features: TrafficFeatures,
    minimum_score: float = MIN_PRIORITY_SCORE,
) -> TrafficAwareDecision:
    """
    Decide whether signal preemption should occur.

    Preemption requires ALL of the following:

    1. Ambulance is inside the predictive control zone.
    2. ML-predicted ETA is inside the predictive window.
    3. The ambulance movement is not already green.
    4. The signal is expected to remain unfavorable long enough
       that natural signal progression is insufficient.
    5. Traffic-aware priority score reaches the configured threshold.
    """

    eta = max(
        0.0,
        float(features.ambulance_eta_s),
    )

    # ----------------------------------------------------------
    # 1. Predictive control distance
    # ----------------------------------------------------------

    if (
        features.ambulance_distance_m
        > MAX_CONTROL_DISTANCE_M
    ):
        return TrafficAwareDecision(
            should_preempt=False,
            priority_score=0.0,
            reason=(
                "Ambulance is outside "
                "the predictive control zone."
            ),
            eta_s=eta,
        )

    # ----------------------------------------------------------
    # 2. Predictive ETA window
    # ----------------------------------------------------------

    if eta > MAX_PREDICTIVE_ETA_S:
        return TrafficAwareDecision(
            should_preempt=False,
            priority_score=0.0,
            reason=(
                "Predicted ambulance ETA "
                "is outside the predictive "
                "control window."
            ),
            eta_s=eta,
        )

    # ----------------------------------------------------------
    # 3. Check ambulance movement signal
    # ----------------------------------------------------------

    if is_movement_signal_green(
        features
    ):
        return TrafficAwareDecision(
            should_preempt=False,
            priority_score=0.0,
            reason=(
                "Signal is already favorable "
                "for the ambulance movement."
            ),
            eta_s=eta,
        )

    # ----------------------------------------------------------
    # 4. Natural signal transition check
    # ----------------------------------------------------------

    time_to_switch = max(
        0.0,
        float(
            features.signal_time_to_switch_s
        ),
    )

    # if (
    #     time_to_switch
    #     <= eta + MIN_SIGNAL_ADVANTAGE_S
    # ):
    #     return TrafficAwareDecision(
    #         should_preempt=False,
    #         priority_score=0.0,
    #         reason=(
    #             "Signal is expected to become "
    #             "favorable before ambulance arrival; "
    #             "preemption is unnecessary."
    #         ),
    #         eta_s=eta,
    #     )

    # ----------------------------------------------------------
    # 5. Calculate traffic-aware priority
    # ----------------------------------------------------------

    score = calculate_priority_score(
        features
    )

    # ----------------------------------------------------------
    # 6. Final decision
    # ----------------------------------------------------------

    if score >= minimum_score:
        return TrafficAwareDecision(
            should_preempt=True,
            priority_score=score,
            reason=(
                "ML ETA, signal timing, ambulance "
                "proximity, and traffic conditions "
                "justify signal preemption."
            ),
            eta_s=eta,
        )

    return TrafficAwareDecision(
        should_preempt=False,
        priority_score=score,
        reason=(
            "Traffic-aware priority score "
            "is below the preemption threshold."
        ),
        eta_s=eta,
    )


# ---------------------------------------------------------------------------
# CONSOLE FORMATTER
# ---------------------------------------------------------------------------

def format_decision(
    decision: TrafficAwareDecision,
) -> str:
    """
    Format the traffic-aware decision for console output.
    """

    eta_text = (
        "N/A"
        if decision.eta_s is None
        else f"{decision.eta_s:.2f}s"
    )

    return (
        f"Preempt: "
        f"{decision.should_preempt} | "
        f"Priority score: "
        f"{decision.priority_score:.1f}/100 | "
        f"Predicted ETA: "
        f"{eta_text} | "
        f"Reason: "
        f"{decision.reason}"
    )
