import sys
from pathlib import Path
import sumolib
import traci

PROJECT_ROOT = Path("D:/AIML/Projects/Major")
PY_ROOT = PROJECT_ROOT / "AI-Predictive-Traffic"
sys.path.append(str(PY_ROOT / "controller"))

import config
import astar_router
import junction_detector
import signal_mapping
from hospital_manager import HospitalManager

MANGALURU_NET = PY_ROOT / "simulation" / "mangaluru" / "mangaluru_ai.net.xml.gz"
HOSPITALS_FILE = PY_ROOT / "simulation" / "mangaluru" / "presentation_labels.add.xml"
SUMOCFG = PY_ROOT / "simulation" / "mangaluru" / "ambulance_test.sumocfg"

config.NET_FILE = MANGALURU_NET
_net = sumolib.net.readNet(str(MANGALURU_NET))
astar_router._SUMO_NETWORK = _net
junction_detector.SUMO_NETWORK = _net

hm = HospitalManager(str(MANGALURU_NET), str(HOSPITALS_FILE))
router = astar_router.AStarRouter(str(MANGALURU_NET))

hosp = hm.get_hospital("kmc_hospital")
dest_edge = hosp.nearest_edge
orig_edge = "321397980"
route_obj = router.find_route(orig_edge, dest_edge)

amb_id = "p3_amb_1"
route_id = "test_route_1"

traci.start([
    "sumo",
    "-c", str(SUMOCFG),
    "--step-length", "1.0",
    "--seed", "42",
    "--no-warnings",
])

# Rebuild TLS cache after TraCI start
signal_mapping._MOVEMENT_TO_TLS_CACHE = None
signal_mapping._build_tls_cache()

traci.route.add(route_id, route_obj.edge_ids)
traci.vehicle.add(
    vehID=amb_id,
    routeID=route_id,
    typeID="ambulance",
    depart="1.0",
    departLane="best",
)

junction_arrivals = {}
observations = []
active_approaches = {}  # junction_id -> {incoming, outgoing, last_dist, last_time}

for s in range(250):

    traci.simulationStep()
    sim_time = traci.simulation.getTime()
    
    if "ambulance" in traci.vehicle.getIDList():
        try:
            traci.vehicle.remove("ambulance")
        except Exception:
            pass
            
    if amb_id in traci.vehicle.getIDList():
        current_road = traci.vehicle.getRoadID(amb_id)
        current_spd = traci.vehicle.getSpeed(amb_id)
        
        # Check upcoming junctions
        upcoming = junction_detector.get_upcoming_junctions(max_junctions=3, ambulance_id=amb_id)
        upcoming_ids = set()
        
        for j in upcoming:
            upcoming_ids.add(j.junction_id)
            active_approaches[j.junction_id] = {
                "incoming": j.incoming_edge,
                "outgoing": j.outgoing_edge,
                "dist": j.distance_from_ambulance_m,
                "time": sim_time,
            }
            if j.distance_from_ambulance_m <= 5.0 and j.junction_id not in junction_arrivals:
                junction_arrivals[j.junction_id] = sim_time
                print(f"[{sim_time:.0f}s] APPROACH REACHED (dist <= 5m) junction {j.junction_id} (speed: {current_spd:.1f} m/s)")

            obs = {
                "step": s,
                "time": sim_time,
                "junction_id": j.junction_id,
                "dist": j.distance_from_ambulance_m,
                "spd": current_spd,
            }
            observations.append(obs)

        # Check any previously approaching junction that is now passed
        for j_id, info in list(active_approaches.items()):
            if j_id not in junction_arrivals:
                if current_road == info["outgoing"] or current_road.startswith(f":{j_id}"):
                    junction_arrivals[j_id] = sim_time
                    print(f"[{sim_time:.0f}s] CROSSED junction {j_id} into {current_road} (speed: {current_spd:.1f} m/s)")
                elif j_id not in upcoming_ids and info["dist"] < 30.0:
                    junction_arrivals[j_id] = sim_time
                    print(f"[{sim_time:.0f}s] PASSED junction {j_id} (last dist was {info['dist']:.1f}m)")

    else:
        if s > 10:
            print(f"[{sim_time:.0f}s] Ambulance finished trip!")
            break

traci.close()
print(f"Total observations recorded: {len(observations)}")
print(f"Junctions arrived at ({len(junction_arrivals)}): {junction_arrivals}")

