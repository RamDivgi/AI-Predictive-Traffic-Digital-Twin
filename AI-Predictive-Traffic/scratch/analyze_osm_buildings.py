import json
import sumolib
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path("d:/AIML/Projects/Major")
json_path = PROJECT_ROOT / "AI-Predictive-Traffic/simulation/mangaluru/osm_buildings_live.json"
net_path = PROJECT_ROOT / "AI-Predictive-Traffic/simulation/mangaluru/presentation_selection2.net.xml"

with open(str(json_path), "r") as f:
    d = json.load(f)

nodes = {e["id"]: (e["lon"], e["lat"]) for e in d.get("elements", []) if e.get("type") == "node"}
ways = [e for e in d.get("elements", []) if e.get("type") == "way" and "building" in e.get("tags", {})]

net = sumolib.net.readNet(str(net_path))
(min_x, min_y), (max_x, max_y) = net.getBBoxXY()

valid_ways = 0
converted_buildings = []
for w in ways:
    node_refs = w.get("nodes", [])
    pts = [nodes[nid] for nid in node_refs if nid in nodes]
    if len(pts) >= 3:
        sumo_pts = [net.convertLonLat2XY(lon, lat) for lon, lat in pts]
        cx = sum(p[0] for p in sumo_pts) / len(sumo_pts)
        cy = sum(p[1] for p in sumo_pts) / len(sumo_pts)
        if min_x <= cx <= max_x and min_y <= cy <= max_y:
            valid_ways += 1
            converted_buildings.append({
                "id": f"osm_way_{w['id']}",
                "tags": w.get("tags", {}),
                "shape": sumo_pts,
                "cx": cx,
                "cy": cy
            })

print(f"Total valid OSM buildings in bbox: {valid_ways}")
print("\nBuilding types breakdown:")
b_types = Counter(b["tags"].get("building") for b in converted_buildings)
for k, v in b_types.most_common(20):
    print(f"  building={k}: {v}")

print("\nNames breakdown (sample):")
named = [b["tags"].get("name") for b in converted_buildings if "name" in b["tags"]]
print(f"Named buildings: {len(named)} / {len(converted_buildings)}")
for n in named[:15]:
    print(f"  - {n}")
