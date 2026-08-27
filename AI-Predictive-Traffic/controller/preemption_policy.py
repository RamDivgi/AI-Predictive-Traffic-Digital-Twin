from dataclasses import dataclass


@dataclass(frozen=True)
class PreemptionDecision:
    should_preempt: bool
    reason: str


def decide_preemption(
    distance_m: float,
    eta_seconds: float,
    current_signal_state: str,
    required_signal_indices: list[int],
    activation_distance_m: float = 60.0,
    activation_eta_seconds: float = 6.0,
) -> PreemptionDecision:
    """
    Decide whether ambulance signal preemption should be activated.

    The first controller uses distance and ETA thresholds rather than
    machine learning. This is the deterministic baseline controller.
    """

    if not required_signal_indices:
        return PreemptionDecision(
            should_preempt=False,
            reason="No signal mapping available.",
        )

    if distance_m <= 0:
        return PreemptionDecision(
            should_preempt=False,
            reason="Ambulance has already reached the junction.",
        )

    if distance_m > activation_distance_m:
        return PreemptionDecision(
            should_preempt=False,
            reason="Ambulance is outside the preemption zone.",
        )

    if eta_seconds > activation_eta_seconds:
        return PreemptionDecision(
            should_preempt=False,
            reason="Ambulance ETA is outside the activation window.",
        )

    return PreemptionDecision(
        should_preempt=True,
        reason="Ambulance is inside the predictive preemption window.",
    )