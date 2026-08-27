from dataclasses import dataclass

import traci


@dataclass
class SignalState:
    junction_id: str
    signal_id: str
    phase_index: int
    state: str
    next_switch_time: float
    time_to_next_switch: float


def get_signal_state(junction_id: str) -> SignalState | None:
    """
    Read the current traffic-signal state for a junction.

    SUMO normally uses the traffic-light junction ID as the
    traffic-light ID. If no matching signal exists, None is returned.
    """

    traffic_light_ids = set(traci.trafficlight.getIDList())

    if junction_id not in traffic_light_ids:
        return None

    current_time = traci.simulation.getTime()

    phase_index = traci.trafficlight.getPhase(junction_id)
    state = traci.trafficlight.getRedYellowGreenState(junction_id)
    next_switch_time = traci.trafficlight.getNextSwitch(junction_id)

    return SignalState(
        junction_id=junction_id,
        signal_id=junction_id,
        phase_index=phase_index,
        state=state,
        next_switch_time=next_switch_time,
        time_to_next_switch=max(
            0.0,
            next_switch_time - current_time,
        ),
    )


def get_signal_states(
    junction_ids: list[str],
) -> list[SignalState]:
    """
    Read signal information for multiple junctions.
    """

    states = []

    for junction_id in junction_ids:
        signal_state = get_signal_state(junction_id)

        if signal_state is not None:
            states.append(signal_state)

    return states


def format_signal_states(
    states: list[SignalState],
) -> str:
    """
    Format signal information for console output.
    """

    if not states:
        return "No traffic-signal data."

    lines = []

    for index, signal in enumerate(states, start=1):
        lines.append(
            f"{index}. Junction {signal.junction_id} | "
            f"Phase: {signal.phase_index} | "
            f"State: {signal.state} | "
            f"Next switch: {signal.time_to_next_switch:.1f}s"
        )

    return "\n".join(lines)