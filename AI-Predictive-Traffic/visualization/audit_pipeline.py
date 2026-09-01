import sys
import math
import os
from pathlib import Path
import traci

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "controller"))

import sumolib
from traffic_aware_controller import TrafficAwareController
import junction_detector

SUMO_CONFIG = PROJECT_ROOT / "simulation" / "mangaluru" / "presentation_demo.sumocfg"
MANGALURU_NET = PROJECT_ROOT / "simulation" / "mangaluru" / "presentation_selection2.net.xml"

import astar_router
import route_evaluator
astar_router.NETWORK_FILE = MANGALURU_NET
route_evaluator.NETWORK_FILE = MANGALURU_NET
junction_detector.NETWORK_FILE = MANGALURU_NET
route_evaluator._SUMO_NETWORK = None
astar_router._SUMO_NETWORK = None
junction_detector.SUMO_NETWORK = sumolib.net.readNet(str(MANGALURU_NET))

def audit():
    print("="*80)
    print("PHASE 2, 3, 6, 8, 12: PIPELINE AUDIT")
    print("="*80)
    
    traci.start(["sumo", "-c", str(SUMO_CONFIG), "--step-length", "0.1"])
    
    controller = TrafficAwareController()
    
    table = []
    
    for step in range(500):
        traci.simulationStep()
        
        sim_time = traci.simulation.getTime()
        vehicles = traci.vehicle.getIDList()
        
        if step == 0:
            print(f"Network offset: {junction_detector.SUMO_NETWORK.getLocationOffset()}")
            
        for v in ["car_0", "ambulance"]:
            if v in vehicles:
                x, y = traci.vehicle.getPosition(v)
                angle = traci.vehicle.getAngle(v)
                lane = traci.vehicle.getLaneID(v)
                
                # Verify lane matching
                if lane and not lane.startswith(":"):
                    lane_obj = junction_detector.SUMO_NETWORK.getLane(lane)
                    shape = lane_obj.getShape()
                    if shape:
                        lane_start = shape[0]
                        unity_road_start_x = lane_start[0]
                        unity_road_start_z = lane_start[1]
                    else:
                        unity_road_start_x = 0
                        unity_road_start_z = 0
                else:
                    unity_road_start_x = 0
                    unity_road_start_z = 0
                
                if step % 50 == 0:
                    table.append({
                        "Time": sim_time,
                        "Veh": v,
                        "SUMO_X": x,
                        "SUMO_Y": y,
                        "SUMO_Angle": angle,
                        "Lane": lane,
                        "Unity_X": x,
                        "Unity_Z": y,
                        "Unity_RotY": angle,
                        "Road_X": unity_road_start_x,
                        "Road_Z": unity_road_start_z
                    })
                    
    traci.close()
    
    print(f"{'Time':<6} | {'Veh':<9} | {'SUMO (X, Y)':<18} | {'SUMO Ang':<8} | {'Lane':<20} | {'Unity (X, Z)':<18} | {'Unity RotY':<10} | {'Road (X, Z)':<18}")
    print("-" * 120)
    for r in table:
        sumo_pos = f"{r['SUMO_X']:.1f}, {r['SUMO_Y']:.1f}"
        unity_pos = f"{r['Unity_X']:.1f}, {r['Unity_Z']:.1f}"
        road_pos = f"{r['Road_X']:.1f}, {r['Road_Z']:.1f}"
        print(f"{r['Time']:<6.1f} | {r['Veh']:<9} | {sumo_pos:<18} | {r['SUMO_Angle']:<8.1f} | {r['Lane']:<20} | {unity_pos:<18} | {r['Unity_RotY']:<10.1f} | {road_pos:<18}")

if __name__ == "__main__":
    audit()
