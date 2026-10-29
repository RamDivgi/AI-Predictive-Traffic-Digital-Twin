import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import traci
from visualization.unity_bridge import generate_dynamic_traffic, generate_round_traffic, cleanup_simulation_traffic

CFG_FILE = str(PROJECT_ROOT / "simulation" / "mangaluru" / "presentation_demo.sumocfg")

def test_corridor_traffic():
    print("Testing corridor traffic generation...")
    generate_dynamic_traffic()
    
    traci.start([
        "sumo",
        "-c", CFG_FILE,
        "--step-length", "0.1",
        "--random",
        "--ignore-route-errors",
        "--quit-on-end",
        "--start"
    ])
    
    try:
        cur_t = traci.simulation.getTime()
        sched = generate_round_traffic(round_id=1, current_time=cur_t, scenario="medium")
        print(f"Scheduled total: {len(sched)}")
        
        # Check jam / corridor vehicles
        jam_ids = [vid for vid in sched if "_jam_" in vid]
        print(f"Corridor jam vehicles scheduled: {len(jam_ids)}: {jam_ids}")
        assert len(jam_ids) == 10, f"Expected 10 corridor vehicles, got {len(jam_ids)}"
        
        # Run simulation for 25 seconds (250 steps)
        collisions = 0
        teleports = 0
        inserted_corridor = set()
        
        for step in range(250):
            traci.simulationStep()
            active = traci.vehicle.getIDList()
            for jid in jam_ids:
                if jid in active:
                    inserted_corridor.add(jid)
            coll = traci.simulation.getCollidingVehiclesNumber()
            if coll > 0:
                collisions += coll
            telep = traci.simulation.getStartingTeleportNumber()
            if telep > 0:
                teleports += telep
                
        print(f"Inserted corridor vehicles: {len(inserted_corridor)} / {len(jam_ids)}")
        print(f"Collisions: {collisions}, Teleports: {teleports}")
        assert collisions == 0, f"Detected {collisions} collisions!"
        assert teleports == 0, f"Detected {teleports} teleports!"
        assert len(inserted_corridor) >= 8, f"Too few corridor vehicles inserted: {len(inserted_corridor)}"
        
        print("\nSUCCESS: All 10 corridor vehicles generated cleanly with 0 collisions and 0 teleports!")
    finally:
        try:
            traci.close()
        except Exception:
            pass

if __name__ == "__main__":
    test_corridor_traffic()
