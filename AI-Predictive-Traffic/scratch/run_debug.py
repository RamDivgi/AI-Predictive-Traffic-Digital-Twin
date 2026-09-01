import sys
import os
import subprocess

PROJECT_ROOT = "D:\\AIML\\Projects\\Major\\AI-Predictive-Traffic"
bridge_path = os.path.join(PROJECT_ROOT, "visualization", "unity_bridge.py")

with open(bridge_path, "r") as f:
    content = f.read()

# Remove the sleep to run fast
content = content.replace("time.sleep(sleep_time)", "pass # time.sleep(sleep_time)")

# Inject debug statements
debug_code = """
        current_time = traci.simulation.getTime()
        if step % 50 == 0:
            jam_count = 0
            for vid in ["jam_car_0", "jam_car_1", "jam_car_2", "jam_car_3"]:
                if vid in current_vehicles:
                    jam_count += 1
            if jam_count > 0:
                print(f"[DEBUG] t={current_time} Jam cars present: {jam_count}, Queue length: {queue_len}, light: {light_color}")
                if "ambulance" in current_vehicles:
                    dist = traci.vehicle.getDistance("ambulance")
                    print(f"       Ambulance dist: {dist}")
"""
content = content.replace("time.sleep(sleep_time)", debug_code + "\n        pass # time.sleep(sleep_time)")

val_path = os.path.join(PROJECT_ROOT, "visualization", "unity_bridge_val_debug.py")
with open(val_path, "w") as f:
    f.write(content)

print("Starting debug run...")
proc = subprocess.run([sys.executable, val_path], capture_output=True, text=True)

for line in proc.stdout.split('\n'):
    if "[DEBUG]" in line or "PREEMPTING" in line or "ambulance" in line:
        print(line)

if os.path.exists(val_path):
    os.remove(val_path)
