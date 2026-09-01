from __future__ import annotations

from dataclasses import dataclass

import traci
import config


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
        self._transitions: dict[str, dict] = {}

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
        if junction_id not in traci.trafficlight.getIDList():
            return False

        if not signal_indices:
            return False

        if self.is_preempted(junction_id):
            return False

        snapshot = self.capture_snapshot(junction_id)
        if snapshot is None or not snapshot.state:
            return False

        current_state = snapshot.state

        # Build target preemption state
        preemption_state = ["r" for _ in current_state]
        valid_indices = []
        for index in signal_indices:
            if 0 <= index < len(preemption_state):
                preemption_state[index] = "G"
                valid_indices.append(index)

        if not valid_indices:
            return False

        target_state = "".join(preemption_state)
        
        # Build yellow transition state
        transition_state_list = list(current_state)
        needs_transition = False
        
        for i, (curr_char, target_char) in enumerate(zip(current_state, target_state)):
            if (curr_char == 'G' or curr_char == 'g') and (target_char == 'r' or target_char == 'y'):
                transition_state_list[i] = 'y'
                needs_transition = True
                
        transition_state = "".join(transition_state_list)
        
        current_time = traci.simulation.getTime()
        
        if needs_transition:
            # Check minimum phase duration. If elapsed < 5.0, wait.
            min_duration = 5.0
            wait_time = max(0.0, min_duration - snapshot.phase_elapsed)
            transition_time = current_time + wait_time
            activation_time = transition_time + 3.0 # 3 seconds of yellow
            
            self._transitions[junction_id] = {
                "step": "WAITING_MIN_DUR" if wait_time > 0 else "YELLOW",
                "transition_state": transition_state,
                "target_state": target_state,
                "transition_time": transition_time,
                "activation_time": activation_time,
                "hold_seconds": hold_seconds
            }
            if wait_time == 0:
                traci.trafficlight.setRedYellowGreenState(junction_id, transition_state)
                print(f"[SIGNAL_TRANSITION] {junction_id} entering YELLOW phase for 3s.")
            else:
                print(f"[SIGNAL_TRANSITION] {junction_id} waiting {wait_time:.1f}s for min phase duration.")
        else:
            # Apply immediately
            traci.trafficlight.setRedYellowGreenState(junction_id, target_state)
            self._active_preemptions[junction_id] = PreemptionRecord(junction_id=junction_id, activated_at=current_time)
            print(f"[SIGNAL_PREEMPTION] {junction_id} active. Green indices: {valid_indices}")

        return True

    def process_step(self):
        """
        Process state machine transitions for signals.
        """
        current_time = traci.simulation.getTime()
        for j_id, trans in list(self._transitions.items()):
            step = trans["step"]
            if step == "WAITING_MIN_DUR":
                if current_time >= trans["transition_time"]:
                    traci.trafficlight.setRedYellowGreenState(j_id, trans["transition_state"])
                    trans["step"] = "YELLOW"
                    print(f"[SIGNAL_TRANSITION] {j_id} minimum duration met, entering YELLOW phase.")
            elif step == "YELLOW":
                if current_time >= trans["activation_time"]:
                    traci.trafficlight.setRedYellowGreenState(j_id, trans["target_state"])
                    self._transitions.pop(j_id, None)
                    self._active_preemptions[j_id] = PreemptionRecord(junction_id=j_id, activated_at=current_time)
                    print(f"[SIGNAL_PREEMPTION] {j_id} active. Target state applied.")

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
            # Restore the original program to resume the normal cycle.
            traci.trafficlight.setProgram(
                junction_id,
                snapshot.program_id,
            )
            # We do NOT use setPhase() here because that resets the phase 
            # timer to 0, which breaks network-wide signal coordination.
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
            config.AMBULANCE_ID
            not in traci.vehicle.getIDList()
        ):
            return False

        try:
            current_edge = traci.vehicle.getRoadID(
                config.AMBULANCE_ID
            )

        except traci.TraCIException:
            return False

        # Ambulance is physically inside the junction.
        if current_edge.startswith(":"):
            return False
            
        try:
            route = list(traci.vehicle.getRoute(config.AMBULANCE_ID))
            if current_edge in route and incoming_edge in route:
                if route.index(current_edge) < route.index(incoming_edge):
                    return False
        except traci.TraCIException:
            pass

        # Ambulance is still approaching the junction.
        if current_edge == incoming_edge:
            return False

        # print(f'DEBUG: restoring {junction_id} because current={current_edge} incoming={incoming_edge} route={route}')
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