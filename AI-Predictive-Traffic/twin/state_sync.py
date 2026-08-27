import os
import sys

# Ensure SUMO_HOME is set
if 'SUMO_HOME' in os.environ:
    tools = os.path.join(os.environ['SUMO_HOME'], 'tools')
    sys.path.append(tools)

import traci
from traci.exceptions import TraCIException

from telemetry_ingest import TelemetryIngestor

class StateSynchronizer:
    def __init__(self, ingestor=None):
        self.ingestor = ingestor if ingestor else TelemetryIngestor()

    def sync_ambulance(self):
        telemetry = self.ingestor.get_latest_ambulance_telemetry("ambulance")
        
        try:
            if telemetry.vehicle_id in traci.vehicle.getIDList():
                speed_before_mps = traci.vehicle.getSpeed(telemetry.vehicle_id)
                speed_before_kmh = speed_before_mps * 3.6
                edge_before = traci.vehicle.getRoadID(telemetry.vehicle_id)
                
                # Apply speed sync
                traci.vehicle.setSpeed(telemetry.vehicle_id, telemetry.speed)
                
                # Attempt to apply position sync (convert geo to XY)
                # using TraCI's coordinate conversion function
                x, y = traci.simulation.convertGeo(telemetry.longitude, telemetry.latitude, True)
                
                # keepRoute=2 keeps the route and maps to closest edge
                traci.vehicle.moveToXY(telemetry.vehicle_id, "", 0, x, y, angle=telemetry.heading, keepRoute=2)
                
                speed_after_mps = traci.vehicle.getSpeed(telemetry.vehicle_id)
                speed_after_kmh = speed_after_mps * 3.6
                
                return {
                    "received": True,
                    "vehicle": telemetry.vehicle_id,
                    "speed_before": speed_before_kmh,
                    "speed_after": speed_after_kmh,
                    "edge": edge_before,
                    "error": None
                }
            else:
                return {
                    "received": True,
                    "vehicle": None,
                    "speed_before": None,
                    "speed_after": None,
                    "edge": None,
                    "error": None
                }
        except TraCIException as e:
            return {
                "received": True,
                "vehicle": telemetry.vehicle_id,
                "speed_before": None,
                "speed_after": None,
                "edge": None,
                "error": str(e)
            }
        except Exception as e:
             return {
                "received": True,
                "vehicle": telemetry.vehicle_id,
                "speed_before": None,
                "speed_after": None,
                "edge": None,
                "error": str(e)
            }


if __name__ == "__main__":
    sumocfg = os.path.abspath(os.path.join(
        os.path.dirname(__file__), 
        "..", 
        "simulation", 
        "mangaluru", 
        "ambulance_test.sumocfg"
    ))
    
    traci.start(["sumo", "-c", sumocfg, "--no-step-log", "true", "--no-warnings", "true"])
    
    try:
        # Advance simulation to ensure ambulance spawns
        while "ambulance" not in traci.vehicle.getIDList():
            traci.simulationStep()
            if traci.simulation.getTime() > 60:
                break
            
        sync = StateSynchronizer()
        result = sync.sync_ambulance()
        
        print("\n============================================================")
        print("DIGITAL TWIN STATE SYNC")
        print("============================================================")
        print()
        print(f"Telemetry received : {'PASS' if result.get('received') else 'FAIL'}")
        print()
        
        vehicle = result.get('vehicle')
        print(f"Vehicle found      : {vehicle if vehicle else 'NONE'}")
        print()
        
        speed_b = result.get('speed_before')
        print(f"Speed before       : {f'{speed_b:.1f}' if speed_b is not None else 'N/A'} km/h")
        print()
        
        speed_a = result.get('speed_after')
        print(f"Speed after        : {f'{speed_a:.1f}' if speed_a is not None else 'N/A'} km/h")
        print()
        
        print(f"Edge               : {result.get('edge') if result.get('edge') else 'N/A'}")
        print()
        
        sync_pass = vehicle is not None and result.get('error') is None
        print(f"Synchronization    : {'PASS' if sync_pass else 'FAIL'}")
        print()
        
        print(f"TraCI errors       : {result.get('error') if result.get('error') else 'NONE'}")
        print()
        print("============================================================")
        print(f"STATE SYNC VALIDATION: {'PASS' if sync_pass else 'FAIL'}")
        print("============================================================")
        
    finally:
        traci.close()
