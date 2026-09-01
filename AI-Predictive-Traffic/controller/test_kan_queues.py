import traci
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SUMO_CONFIG = PROJECT_ROOT / "simulation" / "mangaluru" / "kankanady_demo.sumocfg"

def main():
    traci.start(["sumo", "-c", str(SUMO_CONFIG), "--step-length", "1.0"])
    
    kan_edge = "1080446743#0"
    max_queue = 0
    
    try:
        for step in range(300):
            traci.simulationStep()
            halted = traci.edge.getLastStepHaltingNumber(kan_edge)
            if halted > max_queue:
                max_queue = halted
            if step % 20 == 0:
                print(f"Step {step}: Halted vehicles on {kan_edge} = {halted}")
                
    finally:
        traci.close()
        
    print(f"\nMax queue length achieved: {max_queue} vehicles")
    if max_queue >= 5:
        print("PASS: Realistic queue built up at Kankanady.")
    else:
        print("FAIL: Queue too short.")

if __name__ == "__main__":
    main()
