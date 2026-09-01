import unittest

class DemoRulesTests(unittest.TestCase):
    def evaluate_decision(self, queue_len, eta, remaining_phase, movement_state):
        queue_clearance = (queue_len * 2.5 + 2.0) if queue_len > 0 else 0.0
        
        preempt = False
        reroute = False
        predicted_conflict = False
        
        is_red = any(c in 'rR' for c in movement_state)
        is_yellow = any(c in 'yY' for c in movement_state)
        is_green = any(c in 'gG' for c in movement_state)
        
        if is_red or is_yellow:
            predicted_delay = max(0.0, remaining_phase + queue_clearance - eta)
            if predicted_delay > 5.0:
                predicted_conflict = True
        else:
            if (eta + queue_clearance) < remaining_phase:
                predicted_conflict = False
            else:
                predicted_conflict = True
                
        if queue_len <= 5:
            if predicted_conflict:
                preempt = True
        else:
            reroute = True
            preempt = False
            
        return preempt, reroute, predicted_conflict
        
    def test_1_queue_4_movement_red_conflict(self):
        # Queue = 4, movement RED, ETA conflicts -> PREEMPT
        preempt, reroute, conflict = self.evaluate_decision(queue_len=4, eta=15, remaining_phase=25, movement_state="rrr")
        self.assertTrue(preempt)
        self.assertFalse(reroute)
        self.assertTrue(conflict)
        
    def test_2_queue_4_another_approach_red_ambulance_green(self):
        # Queue = 4, another approach RED but ambulance GREEN (and sufficient time) -> NO ACTION
        preempt, reroute, conflict = self.evaluate_decision(queue_len=4, eta=15, remaining_phase=40, movement_state="GGG")
        self.assertFalse(preempt)
        self.assertFalse(reroute)
        self.assertFalse(conflict)
        
    def test_3_queue_4_ambulance_green_insufficient_time(self):
        # Queue = 4, ambulance GREEN but will run out before arriving -> CONFLICT, PREEMPT
        preempt, reroute, conflict = self.evaluate_decision(queue_len=4, eta=25, remaining_phase=10, movement_state="GGG")
        self.assertTrue(preempt)
        self.assertFalse(reroute)
        self.assertTrue(conflict)
        
    def test_4_queue_6_better_route(self):
        # Queue = 6 -> REROUTE
        preempt, reroute, conflict = self.evaluate_decision(queue_len=6, eta=15, remaining_phase=25, movement_state="rrr")
        self.assertFalse(preempt)
        self.assertTrue(reroute)

if __name__ == '__main__':
    unittest.main()
