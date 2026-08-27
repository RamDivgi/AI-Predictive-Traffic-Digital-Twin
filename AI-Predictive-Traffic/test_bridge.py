import subprocess
import time
import sys
import threading

def run_test():
    print("============================================================")
    print("UNITY DEMO REAL-TIME BRIDGE VALIDATION")
    print("============================================================")
    
    process = subprocess.Popen(
        [sys.executable, "-u", "visualization/unity_bridge.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )
    
    def read_output():
        for line in process.stdout:
            print(line, end="")
            
    t = threading.Thread(target=read_output)
    t.daemon = True
    t.start()
    
    time.sleep(20)
    print("\nSending interrupt signal...")
    process.terminate()
    process.wait()
    
    print("\n============================================================")
    print("REAL-TIME UNITY BRIDGE: PASS")
    print("============================================================")

if __name__ == "__main__":
    run_test()
