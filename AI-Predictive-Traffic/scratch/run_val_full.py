import sys
import os
import subprocess

PROJECT_ROOT = "D:\\AIML\\Projects\\Major\\AI-Predictive-Traffic"
bridge_path = os.path.join(PROJECT_ROOT, "visualization", "unity_bridge.py")

with open(bridge_path, "r") as f:
    content = f.read()

# Remove the sleep to run fast
content = content.replace("time.sleep(sleep_time)", "pass # time.sleep(sleep_time)")

val_path = os.path.join(PROJECT_ROOT, "visualization", "unity_bridge_val_full.py")
with open(val_path, "w") as f:
    f.write(content)

print("Starting 1 full validation run...")
proc = subprocess.run([sys.executable, val_path], capture_output=True, text=True)

for line in proc.stdout.split('\n'):
    if "BACKGROUND TRAFFIC" in line:
        print("---")
    if "PREEMPTING" in line:
        print(line)

print("Done")
if os.path.exists(val_path):
    os.remove(val_path)
