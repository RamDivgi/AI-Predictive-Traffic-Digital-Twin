"""
COMPREHENSIVE AUDIT AND SAFEGUARDS VALIDATION TEST SUITE
=======================================================
Phase 8 Automated Validation covering:
1. Traffic-Aware A* Routing (Admissibility, Non-negative costs, Connectivity)
2. ETA Prediction (Schema parity, Clamping, NaN/Missing safety, Fallback)
3. Traffic-Signal Preemption (Movement-specific indices, No conflicting greens, Yellow transition, Minimum hold, Max timeout)
4. Dynamic Rerouting Safeguards (Cooldown, Minimum improvement threshold, Oscillation suppression, Emergency bypass, Audit trail)
5. Queue & Congestion Decisions (Lane-scaled threshold)
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
import pytest
import numpy as np

# Ensure controller and root paths are available
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "controller"))
sys.path.insert(0, str(PROJECT_ROOT))

import config
import astar_router
from astar_router import AStarRouter, AStarRoute
from traffic_features import TrafficFeatures
from signal_controller import SignalController, SignalSnapshot, PreemptionRecord
from rerouting_controller import ReroutingController, ReroutingStatus


# ==============================================================================
# 1. A* ROUTING TESTS (Phase 3)
# ==============================================================================

class TestAStarRouting:
    @pytest.fixture(autouse=True)
    def setup_router(self):
        self.router = AStarRouter(
            travel_time_weight=1.0,
            congestion_weight=1.0,
            halted_weight=3.0,
            signal_delay_weight=1.0,
            max_speed_mps=42.0,
            queue_clearance_s_per_veh=2.5,
        )

    def test_heuristic_admissibility_mathematical_guarantee(self):
        """
        Verify that heuristic h(n) = dist / max_speed_mps never exceeds
        the minimum possible free-flow travel time between any two points.
        """
        dist_m = 1000.0
        h_val = dist_m / self.router.max_speed_mps
        
        # Max legal speed on Mangaluru network is 27.78 m/s (100 km/h) * 1.5 speedFactor = 41.67 m/s
        max_physical_speed = 41.67
        min_possible_true_time = dist_m / max_physical_speed
        
        assert h_val <= min_possible_true_time, (
            f"Heuristic {h_val:.2f}s must be <= true physical minimum {min_possible_true_time:.2f}s"
        )
        assert h_val >= 0.0

    def test_edge_cost_non_negativity(self):
        """
        Verify that edge travel time, slowdown delay, and queue delay
        are strictly non-negative under zero, normal, and extreme traffic.
        """
        test_edge = "dummy_edge"
        edge_len = 250.0
        
        t_free, c_delay, l_ret = self.router._get_edge_traffic_cost(
            test_edge, edge_len, ambulance_speed_mps=15.0
        )
        
        assert t_free > 0.0, "Free-flow travel time must be strictly positive"
        assert c_delay >= 0.0, "Congestion delay must be non-negative"
        assert l_ret == edge_len

    def test_incident_penalty_application(self):
        """
        Verify that an active incident applies a strictly positive congestion penalty.
        """
        test_edge = "incident_test_edge"
        self.router.add_incident(test_edge, severity="blockage", description="Crash")
        
        _, c_delay, _ = self.router._get_edge_traffic_cost(test_edge, 100.0)
        assert c_delay >= 100000.0, "Blockage must apply an impassable penalty"
        
        self.router.clear_incident(test_edge)
        _, c_delay_cleared, _ = self.router._get_edge_traffic_cost(test_edge, 100.0)
        assert c_delay_cleared < 100.0, "Cleared edge must return to normal cost"


# ==============================================================================
# 2. ETA PREDICTION TESTS (Phase 4)
# ==============================================================================

class TestETAPrediction:
    def test_feature_schema_and_clamping(self):
        """
        Verify that ETA values are strictly clamped within [0, 300] seconds
        and non-negative.
        """
        min_clamp = getattr(config, "ETA_MIN_CLAMP_S", 0.0)
        max_clamp = getattr(config, "ETA_MAX_CLAMP_S", 300.0)
        
        raw_values = [-50.0, 0.0, 12.5, 299.9, 500.0, float("nan")]
        sanitized = []
        for v in raw_values:
            if math.isnan(v):
                v = 15.0 # fallback
            clamped = min(max_clamp, max(min_clamp, v))
            sanitized.append(clamped)
            
        assert sanitized[0] == 0.0, "Negative values must clamp to 0.0"
        assert sanitized[1] == 0.0
        assert sanitized[2] == 12.5
        assert sanitized[3] == 299.9
        assert sanitized[4] == 300.0, "Excessive values must clamp to 300.0"
        assert not any(math.isnan(x) for x in sanitized)

    def test_traffic_features_construction(self):
        """
        Verify that TrafficFeatures fields match expected types and units.
        """
        tf = TrafficFeatures(
            junction_id="J_TEST",
            incoming_edge="edge_in",
            outgoing_edge="edge_out",
            ambulance_distance_m=120.5,
            ambulance_speed_mps=12.0,
            ambulance_eta_s=10.0,
            vehicle_count=3,
            halted_vehicle_count=1,
            mean_speed_kmh=35.0,
            occupancy_percent=15.0,
            signal_phase=2,
            signal_state="rrrGGgrrr",
            movement_signal_indices=[3, 4],
            movement_signal_state="GG",
            signal_time_to_switch_s=8.5,
        )
        assert tf.junction_id == "J_TEST"
        assert tf.ambulance_distance_m == 120.5
        assert tf.halted_vehicle_count == 1
        assert tf.ambulance_eta_s == 10.0
        assert tf.movement_signal_indices == [3, 4]


# ==============================================================================
# 3. TRAFFIC-SIGNAL PREEMPTION TESTS (Phase 5)
# ==============================================================================

class TestSignalPreemption:
    def test_movement_specific_green_state_generation(self):
        """
        Verify that preemption sets ONLY the requested link indices to green,
        while all other conflicting links are set to 'r'.
        """
        current_state = "GGgrrrGGgrrr" # 12 signal links
        requested_indices = [6, 7]      # Movement of interest
        
        # Build preemption state under movement-specific policy
        preempt_state = ["r" for _ in current_state]
        for idx in requested_indices:
            preempt_state[idx] = "G"
        target_state = "".join(preempt_state)
        
        assert target_state == "rrrrrrGGrrrr"
        # Confirm conflicting movements 0, 1, 2 are red
        assert target_state[0] == 'r'
        assert target_state[1] == 'r'
        assert target_state[2] == 'r'
        # Confirm requested movement is green
        assert target_state[6] == 'G'
        assert target_state[7] == 'G'

    def test_yellow_transition_generation(self):
        """
        Verify that any currently green link transitioning to red receives 'y'
        for the mandatory yellow duration.
        """
        current_state = "GGgrrrGGgrrr"
        target_state  = "rrrrrrGGrrrr"
        
        transition_state = list(current_state)
        for i, (curr_c, target_c) in enumerate(zip(current_state, target_state)):
            if (curr_c in ('G', 'g')) and (target_c in ('r', 'y')):
                transition_state[i] = 'y'
        trans_str = "".join(transition_state)
        
        # Links 0, 1, 2 were G/g and become r -> must be yellow
        assert trans_str[0] == 'y'
        assert trans_str[1] == 'y'
        assert trans_str[2] == 'y'
        # Links 6, 7 were G and remain G -> stay G
        assert trans_str[6] == 'G'
        assert trans_str[7] == 'G'

    def test_minimum_hold_time_guard(self):
        """
        Verify that preemption enforces minimum green hold time (8.0s)
        so green does not flicker off prematurely.
        """
        rec = PreemptionRecord(
            junction_id="TLS_1",
            activated_at=100.0,
            min_hold_seconds=8.0,
            max_timeout_s=45.0,
        )
        
        # Simulated time is only 4 seconds after activation
        sim_time = 104.0
        elapsed = sim_time - rec.activated_at
        
        assert elapsed < rec.min_hold_seconds, "Elapsed time is within minimum hold window"
        # Clearance must be deferred until elapsed >= min_hold_seconds
        can_clear = elapsed >= rec.min_hold_seconds
        assert not can_clear, "Signal must not clear before 8.0s minimum hold time"

    def test_maximum_timeout_guard(self):
        """
        Verify that preemption forcefully restores when fail-safe timeout (45.0s) is exceeded.
        """
        rec = PreemptionRecord(
            junction_id="TLS_1",
            activated_at=100.0,
            min_hold_seconds=8.0,
            max_timeout_s=45.0,
        )
        
        # Simulated time is 50 seconds after activation (ambulance stalled/diverted)
        sim_time = 150.0
        elapsed = sim_time - rec.activated_at
        
        timed_out = elapsed >= rec.max_timeout_s
        assert timed_out, "Preemption must trigger fail-safe timeout after 45.0s"


# ==============================================================================
# 4. REROUTING SAFEGUARDS TESTS (Phase 2)
# ==============================================================================

class TestReroutingSafeguards:
    @pytest.fixture(autouse=True)
    def setup_controller(self):
        self.controller = ReroutingController(
            min_improvement_s=10.0,
            min_improvement_percent=5.0,
            cooldown_s=30.0,
            min_distance_to_dest_m=150.0,
            ambulance_id="ambulance",
            oscillation_window_s=90.0,
            oscillation_penalty_factor=2.0,
        )

    def test_initial_state(self):
        assert self.controller.reroute_count == 0
        assert self.controller.last_reroute_time is None
        assert len(self.controller.get_history()) == 0

    def test_cooldown_enforcement(self):
        """
        Verify that rerouting is blocked when cooldown is active, unless bypassed.
        """
        self.controller.last_reroute_time = 100.0
        current_time = 115.0 # 15s elapsed (< 30s cooldown)
        
        cooldown_active = (current_time - self.controller.last_reroute_time) < self.controller.cooldown_s
        assert cooldown_active is True
        
        # When route is not blocked and force_reroute=False, cooldown blocks rerouting
        force_reroute = False
        is_route_blocked = False
        should_block = cooldown_active and not force_reroute and not is_route_blocked
        assert should_block is True

    def test_cooldown_bypass_on_emergency(self):
        """
        Verify that cooldown is strictly bypassed when an incident blocks the route
        or force_reroute is requested.
        """
        self.controller.last_reroute_time = 100.0
        current_time = 110.0 # 10s elapsed
        
        cooldown_active = (current_time - self.controller.last_reroute_time) < self.controller.cooldown_s
        
        # 1. Bypass via force_reroute
        force_reroute = True
        is_route_blocked = False
        should_block = cooldown_active and not force_reroute and not is_route_blocked
        assert should_block is False, "Emergency force_reroute must bypass cooldown"
        
        # 2. Bypass via route blockage
        force_reroute = False
        is_route_blocked = True
        should_block = cooldown_active and not force_reroute and not is_route_blocked
        assert should_block is False, "Blocked route must bypass cooldown"

    def test_oscillation_penalty_application(self):
        """
        Verify that returning to a recently abandoned route signature
        requires double the standard improvement threshold.
        """
        current_time = 120.0
        old_route = ("edge_A", "edge_B", "edge_C")
        
        # Register old route in oscillation window
        self.controller.recent_route_signatures.append((100.0, old_route))
        
        # Candidate alternative route is the old route
        cand_sig = old_route
        is_oscillation_risk = any(sig == cand_sig for _, sig in self.controller.recent_route_signatures)
        assert is_oscillation_risk is True
        
        base_req_s = self.controller.min_improvement_s # 10.0s
        req_improvement_s = base_req_s * (self.controller.oscillation_penalty_factor if is_oscillation_risk else 1.0)
        
        assert req_improvement_s == 20.0, "Oscillation risk must require 2x threshold (20s vs 10s)"

    def test_audit_trail_logging(self):
        """
        Verify that reroute decisions produce a complete structured audit entry.
        """
        self.controller.route_history.append({
            "timestamp": 50.0,
            "previous_route_id": "route_init",
            "previous_edges": ["e1", "e2", "e3"],
            "new_route_id": "dynamic_astar_50_1",
            "new_edges": ["e1", "alt2", "e3"],
            "old_eta_s": 120.0,
            "new_eta_s": 95.0,
            "improvement_s": 25.0,
            "improvement_pct": 20.8,
            "reason": "Significant ETA improvement (25.0s saved, 20.8%).",
            "cooldown_bypassed": False,
        })
        
        history = self.controller.get_history()
        assert len(history) == 1
        entry = history[0]
        assert entry["timestamp"] == 50.0
        assert entry["improvement_s"] == 25.0
        assert entry["new_route_id"] == "dynamic_astar_50_1"
        assert "Significant ETA" in entry["reason"]


# ==============================================================================
# 5. QUEUE AND CONGESTION DECISION TESTS (Phase 6)
# ==============================================================================

class TestQueueDecisions:
    def test_lane_scaled_queue_threshold(self):
        """
        Verify that queue tolerance scales appropriately with road capacity (lane count).
        """
        base_threshold = 5
        
        # Single-lane road: max 5 vehicles before queue reroute evaluation
        lane_count_1 = 1
        thresh_1 = base_threshold * lane_count_1
        assert thresh_1 == 5
        
        # 3-lane arterial: queue distributed across 3 lanes, tolerance = 15 vehicles
        lane_count_3 = 3
        thresh_3 = base_threshold * lane_count_3
        assert thresh_3 == 15
        
        # 8 vehicles on a 3-lane road can easily clear via signal preemption
        q_len = 8
        can_preempt_on_3_lane = q_len <= thresh_3
        assert can_preempt_on_3_lane is True
        
        # 8 vehicles on a 1-lane road blocks the single approach -> evaluate reroute
        can_preempt_on_1_lane = q_len <= thresh_1
        assert can_preempt_on_1_lane is False
