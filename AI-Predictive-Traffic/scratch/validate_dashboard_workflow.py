import os
import sys
import time
import requests
import subprocess
from pathlib import Path
import json

PROJECT_ROOT = Path(__file__).resolve().parent.parent

def run_dashboard_validation():
    print("--- VALIDATING DASHBOARD WORKFLOW ---")
    
    # Start unity_bridge.py headless
    bridge_path = PROJECT_ROOT / "visualization" / "unity_bridge.py"
    
    # We patch it for testing
    with open(bridge_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Disable GUI and webbrowser opening for test
    content = content.replace('webbrowser.open("http://localhost:8000/dashboard")', 'pass')
    # Run faster
    content = content.replace("time.sleep(sleep_time)", "pass")
    content = content.replace("traci.simulation.getTime() < 3600", "traci.simulation.getTime() < 120")
    
    test_path = PROJECT_ROOT / "visualization" / "unity_bridge_dashboard_test.py"
    with open(test_path, 'w', encoding='utf-8') as f:
        f.write(content)
        
    out_path = PROJECT_ROOT / "scratch" / "test_out.log"
    with open(out_path, "w") as out_f:
        proc = subprocess.Popen([sys.executable, str(test_path)], stdout=out_f, stderr=subprocess.STDOUT)
    
    print("Waiting for API to boot (port 8000)...")
    
    # Wait for API to boot
    for _ in range(15):
        try:
            res = requests.get("http://localhost:8000/health")
            if res.status_code == 200:
                break
        except:
            time.sleep(1)
            
    try:
        res = requests.get("http://localhost:8000/hospitals")
        hospitals = res.json()
        print(f"[TEST] Hospitals fetched: {len(hospitals)}")
        assert len(hospitals) > 0
    except Exception as e:
        print(f"[FAIL] Hospital API error: {e}")
        proc.terminate()
        return

    # 2. Wait 5s of background traffic (no ambulance)
    time.sleep(5)
    
    # 3. Post Trip Command
    print("[TEST] Triggering START TRIP from dashboard API...")
    payload = {
        "emergency": True,
        "hospital_id": hospitals[0]['id']
    }
    requests.post("http://localhost:8000/trip/start", json=payload)
    
    # 4. Read simulation output to verify ambulance started and preemption occurred
    time.sleep(15) # Wait for simulation to run to 120s
    proc.terminate()
    
    with open(out_path, "r") as out_f:
        out = out_f.read()
    
    if "EMERGENCY TRIP STARTED" in out:
        print("[PASS] Dashboard trigger successfully spawned ambulance.")
    else:
        print("[FAIL] Ambulance did not spawn via Dashboard API.")
        
    if "PREEMPTING" in out or "Reason: Predicted ambulance delay" in out:
        print("[PASS] AI successfully monitored dynamically spawned ambulance.")
    else:
        print("[FAIL] Preemption not logged. Output excerpt:")
        print(out[-1000:])
        
    if os.path.exists(test_path):
        os.remove(test_path)
        
    print("--- VALIDATION COMPLETE ---")

if __name__ == "__main__":
    run_dashboard_validation()
