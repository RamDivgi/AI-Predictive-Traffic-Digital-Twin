from __future__ import annotations

from dataclasses import dataclass

import traci

from signal_mapping import get_signal_indices_for_movement


@dataclass
class PreemptionPlan:
    junction_id: str
    incoming_edge: str
    outgoing_edge: str
    signal_indices: list[int]
    current_state: str
    current_phase: int
    time_to_next_switch: float


@dataclass
class ActivePreemption:
    junction_id: str
    original_state: str
    original_phase: int


# Active preemptions are tracked explicitly.
# This is more reliable than trying to infer preemption
# from the current SUMO signal state.
_ACTIVE_PREEMPTIONS: dict[str, ActivePreemption] = {}


def create_preemption_plan(
    junction_id: str,
    incoming_edge: str,
    outgoing_edge: str,
) -> PreemptionPlan | None:
    """
    Create a signal preemption plan.

    This function only reads SUMO state.
    It does not modify the traffic signal.
    """

    if junction_id not in traci.trafficlight.getIDList():
        return None

    signal_indices = get_signal_indices_for_movement(
        junction_id,
        incoming_edge,
        outgoing_edge,
    )

    current_time = traci.simulation.getTime()

    current_phase = traci.trafficlight.getPhase(
        junction_id
    )

    current_state = (
        traci.trafficlight.getRedYellowGreenState(
            junction_id
        )
    )

    next_switch_time = traci.trafficlight.getNextSwitch(
        junction_id
    )

    return PreemptionPlan(
        junction_id=junction_id,
        incoming_edge=incoming_edge,
        outgoing_edge=outgoing_edge,
        signal_indices=signal_indices,
        current_state=current_state,
        current_phase=current_phase,
        time_to_next_switch=max(
            0.0,
            next_switch_time - current_time,
        ),
    )


def apply_preemption(
    plan: PreemptionPlan,
) -> ActivePreemption | None:
    """
    Apply emergency green for the ambulance movement.

    The original signal state and phase are saved so the
    traffic signal can be restored correctly later.

    If the junction is already under preemption, no second
    preemption is applied.
    """

    junction_id = plan.junction_id

    if junction_id not in traci.trafficlight.getIDList():
        return None

    if is_preemption_active(junction_id):
        return None

    if not plan.signal_indices:
        return None

    current_state = (
        traci.trafficlight.getRedYellowGreenState(
            junction_id
        )
    )

    signal_length = len(current_state)

    if signal_length == 0:
        return None

    valid_indices = [
        index
        for index in plan.signal_indices
        if 0 <= index < signal_length
    ]

    if not valid_indices:
        return None

    original_phase = traci.trafficlight.getPhase(
        junction_id
    )

    emergency_state = [
        "r"
        for _ in range(signal_length)
    ]

    for index in valid_indices:
        emergency_state[index] = "G"

    emergency_state_string = "".join(
        emergency_state
    )

    traci.trafficlight.setRedYellowGreenState(
        junction_id,
        emergency_state_string,
    )

    active_preemption = ActivePreemption(
        junction_id=junction_id,
        original_state=current_state,
        original_phase=original_phase,
    )

    _ACTIVE_PREEMPTIONS[
        junction_id
    ] = active_preemption

    return active_preemption


def release_preemption(
    active_preemption: ActivePreemption | None,
) -> bool:
    """
    Restore the signal state and phase saved before preemption.
    """

    if active_preemption is None:
        return False

    junction_id = active_preemption.junction_id

    if junction_id not in traci.trafficlight.getIDList():
        _ACTIVE_PREEMPTIONS.pop(
            junction_id,
            None,
        )
        return False

    try:
        # Restore the original signal state first.
        traci.trafficlight.setRedYellowGreenState(
            junction_id,
            active_preemption.original_state,
        )

        # Restore the original phase as well.
        traci.trafficlight.setPhase(
            junction_id,
            active_preemption.original_phase,
        )

    except traci.TraCIException:
        return False

    _ACTIVE_PREEMPTIONS.pop(
        junction_id,
        None,
    )

    return True


def is_preemption_active(
    junction_id: str,
) -> bool:
    """
    Return whether this controller currently has an active
    preemption at the specified junction.
    """

    return junction_id in _ACTIVE_PREEMPTIONS


def get_active_preemption(
    junction_id: str,
) -> ActivePreemption | None:
    """
    Return the active preemption record for a junction.
    """

    return _ACTIVE_PREEMPTIONS.get(
        junction_id
    )


def clear_all_preemptions() -> None:
    """
    Clear controller-side preemption tracking.

    This should be used during shutdown after signals have
    been restored.
    """

    _ACTIVE_PREEMPTIONS.clear()


def format_preemption_plan(
    plan: PreemptionPlan | None,
) -> str:
    """
    Format a preemption plan for readable console output.
    """

    if plan is None:
        return "No preemption plan available."

    indices = (
        ", ".join(
            str(index)
            for index in plan.signal_indices
        )
        if plan.signal_indices
        else "None"
    )

    return (
        f"Junction: {plan.junction_id} | "
        f"Movement: "
        f"{plan.incoming_edge} -> "
        f"{plan.outgoing_edge} | "
        f"Signal indices: [{indices}] | "
        f"Phase: {plan.current_phase} | "
        f"State: {plan.current_state} | "
        f"Next switch in: "
        f"{plan.time_to_next_switch:.1f}s"
    )