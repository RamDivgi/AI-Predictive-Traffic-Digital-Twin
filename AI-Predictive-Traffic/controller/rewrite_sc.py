import os
import re

sc_path = r"d:\AIML\Projects\Major\AI-Predictive-Traffic\controller\signal_controller.py"

with open(sc_path, "r", encoding="utf-8") as f:
    sc_code = f.read()

# Add _active_transitions to __init__
init_replacement = """    def __init__(self) -> None:
        self._snapshots: dict[str, SignalSnapshot] = {}
        self._active_preemptions: dict[str, PreemptionRecord] = {}
        self._transitions: dict[str, dict] = {}"""
sc_code = re.sub(r'    def __init__\(self\) -> None:.*?_active_preemptions: dict\[str, PreemptionRecord\] = \{\}', init_replacement, sc_code, flags=re.DOTALL)

# Replace preempt method
preempt_replacement = """    def preempt(
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
        \"\"\"
        Process state machine transitions for signals.
        \"\"\"
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
                    print(f"[SIGNAL_PREEMPTION] {j_id} active. Target state applied.")"""

sc_code = re.sub(r'    def preempt\(.*?return True', preempt_replacement, sc_code, flags=re.DOTALL)

with open(sc_path, "w", encoding="utf-8") as f:
    f.write(sc_code)
print("Updated signal_controller.py")
