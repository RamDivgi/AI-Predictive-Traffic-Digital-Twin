from __future__ import annotations

from dataclasses import dataclass

import traci


AMBULANCE_ID = "ambulance"


@dataclass
class SignalSnapshot:
    junction_id: str
    program_id: str
    phase_index: int
    phase_duration: float
    phase_elapsed: float
    phase_remaining: float
    state: str


@dataclass
class PreemptionRecord:
    junction_id: str
    activated_at: float
    restored_at: float | None = None


class SignalController:
    """
    Controls temporary SUMO traffic-signal preemption.

    The controller:
    1. Captures the original signal program and phase.
    2. Gives green only to the mapped ambulance movement.
    3. Holds that movement green temporarily.
    4. Restores the original signal program after the ambulance clears.
    """

    def __init__(self) -> None:
        self._snapshots: dict[str, SignalSnapshot] = {}
        self._active_preemptions: dict[str, PreemptionRecord] = {}

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    def capture_snapshot(
        self,
        junction_id: str,
    ) -> SignalSnapshot | None:
        """
        Capture the current signal configuration.
        """

        if junction_id not in traci.trafficlight.getIDList():
            return None

        program_id = traci.trafficlight.getProgram(
            junction_id
        )

        phase_index = traci.trafficlight.getPhase(
            junction_id
        )

        phase_duration = traci.trafficlight.getPhaseDuration(
            junction_id
        )

        phase_elapsed = traci.trafficlight.getSpentDuration(
            junction_id
        )

        state = traci.trafficlight.getRedYellowGreenState(
            junction_id
        )

        snapshot = SignalSnapshot(
            junction_id=junction_id,
            program_id=program_id,
            phase_index=phase_index,
            phase_duration=phase_duration,
            phase_elapsed=phase_elapsed,
            phase_remaining=max(
                0.0,
                phase_duration - phase_elapsed,
            ),
            state=state,
        )

        self._snapshots[junction_id] = snapshot

        return snapshot

    # ------------------------------------------------------------------
    # Preemption
    # ------------------------------------------------------------------

    def preempt(
        self,
        junction_id: str,
        signal_indices: list[int],
        hold_seconds: float = 8.0,
    ) -> bool:
        """
        Temporarily give green to the ambulance movement.

        Only the signal indices belonging to the ambulance movement
        are set to green. Every other controlled movement is red.

        The temporary state is maintained using SUMO's direct signal
        state API. The original program is restored later.
        """

        if junction_id not in traci.trafficlight.getIDList():
            return False

        if not signal_indices:
            return False

        if self.is_preempted(junction_id):
            return False

        snapshot = self.capture_snapshot(
            junction_id
        )

        if snapshot is None:
            return False

        current_state = snapshot.state

        if not current_state:
            return False

        # --------------------------------------------------------------
        # Build temporary preemption state
        # --------------------------------------------------------------

        preemption_state = [
            "r"
            for _ in current_state
        ]

        valid_indices = []

        for index in signal_indices:

            if (
                0 <= index < len(preemption_state)
            ):
                preemption_state[index] = "G"
                valid_indices.append(index)

        if not valid_indices:
            return False

        temporary_state = "".join(
            preemption_state
        )

        # --------------------------------------------------------------
        # Apply temporary state
        # --------------------------------------------------------------

        try:
            traci.trafficlight.setRedYellowGreenState(
                junction_id,
                temporary_state,
            )

        except traci.TraCIException:
            self._snapshots.pop(
                junction_id,
                None,
            )
            return False

        current_time = traci.simulation.getTime()

        self._active_preemptions[junction_id] = (
            PreemptionRecord(
                junction_id=junction_id,
                activated_at=current_time,
            )
        )

        print(
            f"*** SIGNAL PREEMPTION ACTIVE *** | "
            f"Junction {junction_id} | "
            f"Green indices: {valid_indices} | "
            f"State: {temporary_state} | "
            f"Hold: {hold_seconds:.1f}s"
        )

        return True

    # ------------------------------------------------------------------
    # Restoration
    # ------------------------------------------------------------------

    def restore(
        self,
        junction_id: str,
    ) -> bool:
        """
        Restore the original signal program and phase.
        """

        snapshot = self._snapshots.get(
            junction_id
        )

        if snapshot is None:
            return False

        if junction_id not in traci.trafficlight.getIDList():
            return False

        try:
            # Restore the original program first.
            traci.trafficlight.setProgram(
                junction_id,
                snapshot.program_id,
            )

            # Restore the original phase.
            traci.trafficlight.setPhase(
                junction_id,
                snapshot.phase_index,
            )

        except traci.TraCIException:
            return False

        record = self._active_preemptions.get(
            junction_id
        )

        if record is not None:
            record.restored_at = (
                traci.simulation.getTime()
            )

        self._active_preemptions.pop(
            junction_id,
            None,
        )

        self._snapshots.pop(
            junction_id,
            None,
        )

        print(
            f"*** SIGNAL RESTORED *** | "
            f"Junction {junction_id} | "
            f"Program: {snapshot.program_id} | "
            f"Phase: {snapshot.phase_index}"
        )

        return True

    # ------------------------------------------------------------------
    # Ambulance clearance
    # ------------------------------------------------------------------

    def release_if_cleared(
        self,
        junction_id: str,
        incoming_edge: str,
    ) -> bool:
        """
        Restore the signal after the ambulance has cleared
        the controlled junction.

        The ambulance is considered to have cleared the junction
        when it is no longer on the incoming approach and is no
        longer travelling on a SUMO internal junction edge.
        """

        if not self.is_preempted(
            junction_id
        ):
            return False

        if (
            AMBULANCE_ID
            not in traci.vehicle.getIDList()
        ):
            return False

        try:
            current_edge = traci.vehicle.getRoadID(
                AMBULANCE_ID
            )

        except traci.TraCIException:
            return False

        # Ambulance is physically inside the junction.
        if current_edge.startswith(":"):
            return False
            
        try:
            route = list(traci.vehicle.getRoute(AMBULANCE_ID))
            if current_edge in route and incoming_edge in route:
                if route.index(current_edge) < route.index(incoming_edge):
                    return False
        except traci.TraCIException:
            pass

        # Ambulance is still approaching the junction.
        if current_edge == incoming_edge:
            return False

        print(f'DEBUG: restoring {junction_id} because current={current_edge} incoming={incoming_edge} route={route}')
        return self.restore(
            junction_id
        )

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def is_preempted(
        self,
        junction_id: str,
    ) -> bool:
        """
        Return True when the junction has active preemption.
        """

        return (
            junction_id
            in self._active_preemptions
        )

    def get_active_preemptions(
        self,
    ) -> list[str]:
        """
        Return currently preempted junction IDs.
        """

        return list(
            self._active_preemptions.keys()
        )

    def get_preemption_record(
        self,
        junction_id: str,
    ) -> PreemptionRecord | None:
        """
        Return the activation/restoration record.
        """

        return self._active_preemptions.get(
            junction_id
        )

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def restore_all(self) -> None:
        """
        Restore every currently preempted junction.
        """

        for junction_id in list(
            self._active_preemptions.keys()
        ):
            self.restore(
                junction_id
            )