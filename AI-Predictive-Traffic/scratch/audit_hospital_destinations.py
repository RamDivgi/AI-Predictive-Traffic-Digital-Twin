import json
from pathlib import Path
import sys

PROJECT_ROOT = Path("D:/AIML/Projects/Major")
PY_ROOT = PROJECT_ROOT / "AI-Predictive-Traffic"
sys.path.append(str(PY_ROOT / "controller"))

import config
import sumolib
import astar_router
from hospital_manager import HospitalManager, AUTHORITATIVE_REGISTRY, EXCLUDED_POIS

MANGALURU_NET = PY_ROOT / "simulation" / "mangaluru" / "mangaluru_ai.net.xml.gz"
HOSPITALS_ADD = PY_ROOT / "simulation" / "mangaluru" / "presentation_labels.add.xml"
ROAD_NETWORK_JSON = PROJECT_ROOT / "MangaluruDigitalTwin3D" / "Assets" / "Generated" / "RoadNetwork.json"

config.NET_FILE = MANGALURU_NET
net = sumolib.net.readNet(str(MANGALURU_NET))
astar_router._SUMO_NETWORK = net

# 1. Load RoadNetwork.json visual landmarks
with open(ROAD_NETWORK_JSON, "r") as f:
    rn_data = json.load(f)

visual_hospitals = rn_data.get("hospitals", [])
print(f"Visual Landmarks in Unity RoadNetwork.json: {len(visual_hospitals)}")

# 2. Load HospitalManager
hm = HospitalManager(str(MANGALURU_NET), str(HOSPITALS_ADD))
print(f"Authoritative Routing Hospitals loaded in Python: {len(hm.hospitals)}")

start_edge = "1096889856" # Standard ambulance spawn edge in Mangaluru simulation
router = astar_router.AStarRouter()

results = []

print("\n--- AUDITING ALL 15 VISUAL LANDMARKS VS AUTHORITATIVE REGISTRY ---")
for vh in visual_hospitals:
    hid = vh["id"]
    hname = vh["name"]
    is_authoritative = hid in hm.hospitals
    is_excluded = hid in EXCLUDED_POIS
    
    # Get nearest edge from HospitalManager if authoritative
    h_obj = hm.get_hospital(hid) if is_authoritative else None
    vh_edge = h_obj.nearest_edge if h_obj else None
    edge_in_net = net.hasEdge(vh_edge) if vh_edge else False
    
    routable = False
    route_len = 0
    if is_authoritative and edge_in_net:
        route = router.find_route(start_edge, vh_edge)
        if route and route.edge_ids:
            routable = True
            route_len = len(route.edge_ids)
            
    status = "AUTHORITATIVE ROUTING TARGET" if is_authoritative else "VISUAL POI ONLY (EXCLUDED FROM AMBULANCE)"
    route_status = f"ROUTABLE ({route_len} edges)" if routable else ("EXCLUDED" if not is_authoritative else "UNROUTABLE")
    
    print(f"[{'PASS' if (is_authoritative == routable or is_excluded) else 'WARN'}] ID: {hid:<30} Name: {hname:<30} Edge: {str(vh_edge):<20} InNet: {edge_in_net} | {status} | {route_status}")
    results.append({
        "id": hid,
        "name": hname,
        "is_authoritative": is_authoritative,
        "is_excluded": is_excluded,
        "edge": vh_edge,
        "edge_in_net": edge_in_net,
        "routable": routable,
        "route_len": route_len
    })

auth_count = sum(1 for r in results if r["is_authoritative"])
auth_routable = sum(1 for r in results if r["is_authoritative"] and r["routable"])
poi_count = sum(1 for r in results if not r["is_authoritative"])

print(f"\nSummary:")
print(f"Total Visual Landmarks: {len(results)}")
print(f"Authoritative Routing Targets: {auth_count} / {len(AUTHORITATIVE_REGISTRY)}")
print(f"Authoritative Targets Routable from {start_edge}: {auth_routable} / {auth_count}")
print(f"Visual-Only POIs (Clinics/Campus): {poi_count}")
