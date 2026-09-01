import os
import re

tac_path = r"d:\AIML\Projects\Major\AI-Predictive-Traffic\controller\traffic_aware_controller.py"

with open(tac_path, "r", encoding="utf-8") as f:
    tac_code = f.read()

# 1. Update set_hospital_destination
new_set_hospital = """    def set_hospital_destination(self, hospital_id: str):
        hospital = self.hospital_manager.get_hospital(hospital_id)
        if hospital and hospital.nearest_edge:
            self.destination_hospital = hospital
            try:
                # ---------------------------------------------------------
                # AMBULANCE ROUTING - CRITICAL
                # Calculate the route exactly ONCE and lock it.
                # ---------------------------------------------------------
                current_edge = traci.vehicle.getRoadID(config.AMBULANCE_ID)
                current_pos = traci.vehicle.getLanePosition(config.AMBULANCE_ID)
                current_speed = traci.vehicle.getSpeed(config.AMBULANCE_ID)
                
                # If inside junction, use the next edge (or just start from where we are)
                if current_edge.startswith(":"):
                    route = traci.vehicle.getRoute(config.AMBULANCE_ID)
                    idx = traci.vehicle.getRouteIndex(config.AMBULANCE_ID)
                    if idx + 1 < len(route):
                        current_edge = route[idx + 1]
                
                astar_route = self.rerouting_controller.astar_router.find_route(
                    start_edge=current_edge,
                    destination_edge=hospital.nearest_edge,
                    start_lane_position=current_pos,
                    ambulance_speed_mps=max(0.1, current_speed)
                )
                
                if astar_route is not None:
                    # Apply fixed route ONCE
                    unique_route_id = f"fixed_astar_{hospital_id}_{int(traci.simulation.getTime())}"
                    traci.route.add(unique_route_id, astar_route.edge_ids)
                    traci.vehicle.setRouteID(config.AMBULANCE_ID, unique_route_id)
                    print(f"[HOSPITAL_SELECTED] Route calculated ONCE to {hospital.name} and locked.")
                else:
                    print(f"[ERROR] A* could not find a path to the hospital.")
                    
                self.rerouting_controller.reset()
                self.last_reroute_evaluation_time = -1.0
                return True
            except traci.exceptions.TraCIException as e:
                print(f"[ERROR] Failed to update hospital destination: {e}")
        return False
"""

# Replace set_hospital_destination
tac_code = re.sub(r'    def set_hospital_destination\(self, hospital_id: str\):.*?(?=    def _configure_model)', new_set_hospital, tac_code, flags=re.DOTALL)

# 2. Add route_is_impossible check
route_is_impossible_code = """
    # ------------------------------------------------------------------
    # RECALCULATION EXCEPTION
    # ------------------------------------------------------------------

    def route_is_impossible(self) -> bool:
        \"\"\"
        Check if the assigned route becomes genuinely unreachable.
        \"\"\"
        try:
            if config.AMBULANCE_ID not in traci.vehicle.getIDList():
                return False
                
            route_edges = traci.vehicle.getRoute(config.AMBULANCE_ID)
            if not route_edges:
                print("[REROUTE_EXCEPTION] Route is empty/disconnected.")
                return True
                
            current_speed = traci.vehicle.getSpeed(config.AMBULANCE_ID)
            current_time = traci.simulation.getTime()
            
            if current_speed < 0.1:
                if getattr(self, "_stationary_start", None) is None:
                    self._stationary_start = current_time
                elif current_time - self._stationary_start > 30.0:
                    tls_info = traci.vehicle.getNextTLS(config.AMBULANCE_ID)
                    if tls_info and tls_info[0][2] < 20.0:
                        # Waiting at TLS, not an impossible route
                        pass
                    else:
                        print(f"[REROUTE_EXCEPTION] Ambulance stuck for >30s, not at a traffic signal. Recalculating.")
                        self._stationary_start = None
                        return True
            else:
                self._stationary_start = None
                
            return False
        except traci.TraCIException:
            print("[REROUTE_EXCEPTION] TraCI Exception evaluating route.")
            return True

"""

# Insert it before process_step
tac_code = re.sub(r'    # ------------------------------------------------------------------\s*# MAIN CONTROL STEP', route_is_impossible_code + r'    # ------------------------------------------------------------------\n    # MAIN CONTROL STEP', tac_code)

# 3. Modify dynamic rerouting block
dynamic_rerouting_replacement = """        # ------------------------------------------------------------------
        # REROUTING EXCEPTION CHECK
        # ------------------------------------------------------------------
        if self.route_is_impossible():
            print("[ROUTE_EXCEPTION] Route is impossible. Triggering one-time recalculation.")
            # Trigger rerouting only once because it's impossible
            self.rerouting_controller.evaluate_and_reroute(ml_etas=None)
            status = self.rerouting_controller.get_status()
            self.control_egress.emit_reroute(config.AMBULANCE_ID, status.initial_route_id, status.current_route_id)"""

tac_code = re.sub(r'        # ------------------------------------------------------------------\s*# DYNAMIC REROUTING\s*# ------------------------------------------------------------------.*?# ------------------------------------------------------------------\s*# UPCOMING JUNCTIONS', dynamic_rerouting_replacement + '\n\n        # ------------------------------------------------------------------\n        # UPCOMING JUNCTIONS', tac_code, flags=re.DOTALL)


# 4. Modify process_step junction logic to handle 15-20s ETA trigger
# Find the UPCOMING JUNCTIONS block and rewrite the loop
junction_loop_replacement = """        # ------------------------------------------------------------------
        # UPCOMING JUNCTIONS & PREEMPTION STATE MACHINE
        # ------------------------------------------------------------------
        # ALWAYS called after potential rerouting so it uses the updated route
        junctions = (
            get_upcoming_junctions(
                config.MAX_JUNCTIONS
            )
        )

        if not junctions:
            return []

        decisions = []
        
        # We only want ONE active preemption target at a time.
        # Find if we already have an active (PREEMPTING, PASSING, etc.) junction
        active_target = None
        for j_id in self.signal_controller.get_active_preemptions():
            active_target = j_id
            break

        for next_junction in junctions:
            features = self.build_ml_features(next_junction)
            if features is not None:
                # Trigger when ETA < 20s
                if features.ambulance_eta_s <= 20.0:
                    import signal_mapping
                    tls_id, _ = signal_mapping.get_tls_and_indices_for_movement(features.incoming_edge, features.outgoing_edge)
                    
                    if tls_id:
                        # Log approach
                        if not hasattr(self, 'last_logged_eta_times'):
                            self.last_logged_eta_times = {}
                        last_logged = self.last_logged_eta_times.get(tls_id, 0)
                        if current_time - last_logged >= 5.0:
                            print(f"[APPROACHING] Ambulance ETA to {tls_id}: {features.ambulance_eta_s:.1f} s")
                            self.last_logged_eta_times[tls_id] = current_time

                        # If there is NO active target, or THIS is the active target
                        if active_target is None or active_target == tls_id:
                            if not self.signal_controller.is_preempted(tls_id):
                                print(f"[PREEMPTION_TRIGGERED] Commencing sequence for {tls_id}")
                                activated = self.activate_preemption(features)
                                if activated:
                                    active_target = tls_id # Now we have an active target
                
                decisions.append((features, None)) # We don't strictly need the decision object format anymore, but returning it

        return decisions"""

tac_code = re.sub(r'        # ------------------------------------------------------------------\s*# UPCOMING JUNCTIONS\s*# ------------------------------------------------------------------.*?return decisions', junction_loop_replacement, tac_code, flags=re.DOTALL)


with open(tac_path, "w", encoding="utf-8") as f:
    f.write(tac_code)
print("Updated traffic_aware_controller.py")
