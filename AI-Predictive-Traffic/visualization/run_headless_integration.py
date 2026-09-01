import sys
from pathlib import Path
import traci
import traci.constants as tc
import subprocess

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "controller"))
sys.path.insert(0, str(PROJECT_ROOT / "visualization"))

import config
from traffic_aware_controller import TrafficAwareController
from hospital_manager import HospitalManager

def run_integration():
    sumo_cmd = "sumo"
    traci.start([
        sumo_cmd,
        "-c", str(config.SIMULATION_DIR / "ambulance_test.sumocfg"),
        "--step-length", "0.2",
        "--random"
    ])
    
    hm = HospitalManager(str(config.NET_FILE), str(config.HOSPITALS_FILE))
    ai_controller = TrafficAwareController()
    
    # Force a destination
    ai_controller.set_hospital_destination("scs_hospital", "1096889856")
    
    # Let's add the jam vehicles manually like unity_bridge does so we guarantee traffic
    jam_departs = [115.0, 117.0, 119.0, 121.0]
    for i, d in enumerate(jam_departs):
        try:
            traci.route.add("jam_route", ["1189020226#3", "-132363066#1", "-132363066#0", "903009071#1"])
        except:
            pass # route might already exist
        traci.vehicle.add(f"jam_car_{i}", "jam_route", depart=str(d))
        
    # Step until 120s
    while traci.simulation.getTime() < 120.0:
        traci.simulationStep()
    
    # Turn on emergency
    try:
        traci.vehicle.setParameter("ambulance", "emergency", "true")
        current_edge = traci.vehicle.getRoadID("ambulance")
        ai_controller.set_hospital_destination("scs_hospital", current_edge)
    except Exception as e:
        print(f"Failed to setup ambulance: {e}")
    
    step = 0
    demo_triggered = False
    
    while step < 1000:
        traci.simulationStep()
        ai_controller.process_step()
        
        if "ambulance" in ai_controller.demo_event_state:
            state = ai_controller.demo_event_state["ambulance"]
            if state in ["REQUESTED", "ACTIVE", "COMPLETED"]:
                demo_triggered = True
                if state == "COMPLETED":
                    print("[INTEGRATION TEST] Demo successfully completed the lifecycle!")
                    break
        
        step += 1
        
    traci.close()
    
    if demo_triggered:
        print("[INTEGRATION TEST] SUCCESS: The predictive demonstration occurred naturally.")
    else:
        print("[INTEGRATION TEST] FAILED: No predictive demonstration occurred.")

if __name__ == "__main__":
    run_integration()
