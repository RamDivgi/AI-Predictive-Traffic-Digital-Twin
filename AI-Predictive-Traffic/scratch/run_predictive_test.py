import sys
import os
import subprocess

PROJECT_ROOT = "D:\\AIML\\Projects\\Major\\AI-Predictive-Traffic"
bridge_path = os.path.join(PROJECT_ROOT, "visualization", "unity_bridge.py")

with open(bridge_path, "r") as f:
    content = f.read()

# Remove the sleep to run fast
content = content.replace("time.sleep(sleep_time)", "pass # time.sleep(sleep_time)")
# Stop early
content = content.replace("traci.simulation.getTime() < 3600", "traci.simulation.getTime() < 120")

val_path = os.path.join(PROJECT_ROOT, "visualization", "unity_bridge_val_test.py")
with open(val_path, "w") as f:
    f.write(content)

print("Testing Execution of Predictive Preemption...")
proc = subprocess.run([sys.executable, val_path], capture_output=True, text=True)

print("Exit code:", proc.returncode)
print("--- STDOUT ---")
for line in proc.stdout.splitlines():
    if "[JUNCTION PREDICTION]" in line or "Preemption required" in line or "[AMBULANCE DETECTED]" in line or "Evaluating rerouting" in line or "Reroute decision" in line or "Reason:" in line:
        print(line)
        
print("--- STDERR ---")
print(proc.stderr)

if os.path.exists(val_path):
    os.remove(val_path)
