import traci
import sumolib
import os
import sys

# Ensure SUMO_HOME is set
if 'SUMO_HOME' in os.environ:
    tools = os.path.join(os.environ['SUMO_HOME'], 'tools')
    sys.path.append(tools)
else:
    sys.exit("please declare environment variable 'SUMO_HOME'")

sumocfg = r"d:\AIML\Projects\AI-Predictive-Traffic\simulation\mangaluru\ambulance_test.sumocfg"

try:
    traci.start(["sumo", "-c", sumocfg, "--no-step-log", "true", "--no-warnings", "true"])
    poi_ids = traci.poi.getIDList()
    
    if "highland_hospital" in poi_ids:
        print("POI loaded: PASS")
        x, y = traci.poi.getPosition("highland_hospital")
        print(f"SUMO X: {x}")
        print(f"SUMO Y: {y}")
        
        net_file = r"d:\AIML\Projects\AI-Predictive-Traffic\simulation\mangaluru\mangaluru_ai.net.xml.gz"
        net = sumolib.net.readNet(net_file)
        bbox = net.getBBoxXY()
        
        if bbox[0][0] <= x <= bbox[1][0] and bbox[0][1] <= y <= bbox[1][1]:
            print("Bounds check: PASS")
            print("SUMO-GUI: PASS")
        else:
            print(f"Bounds check: FAIL. Bounds: {bbox}")
    else:
        print("POI loaded: FAIL")
        print(f"Loaded POIs: {poi_ids[:10]}...") # show some to debug
        
except Exception as e:
    print(f"Error: {e}")
finally:
    try:
        traci.close()
    except Exception:
        pass
