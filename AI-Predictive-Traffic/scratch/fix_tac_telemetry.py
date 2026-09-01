import os

file_path = "D:\\AIML\\Projects\\Major\\AI-Predictive-Traffic\\controller\\traffic_aware_controller.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# Add a decisions list
content = content.replace("preemption_requests = []", "preemption_requests = []\n        decisions_for_telemetry = []")

# Inside the preemption logic, append to decisions_for_telemetry
append_str = """
                                self.last_logged_eta_times[(amb_id, tls_id)] = current_time

                            from preemption_decision import TrafficAwareDecision
                            decision = TrafficAwareDecision(
                                should_preempt=True,
                                priority_score=100.0,
                                reason=f"Predicted ambulance delay ({predicted_delay:.1f}s) conflicts with ETA ({eta:.1f}s)",
                                eta_s=eta
                            )
                            decisions_for_telemetry.append((features, decision))"""

content = content.replace("self.last_logged_eta_times[(amb_id, tls_id)] = current_time", append_str)

# Return decisions_for_telemetry
content = content.replace("return []", "return decisions_for_telemetry")

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Updated traffic_aware_controller.py")
