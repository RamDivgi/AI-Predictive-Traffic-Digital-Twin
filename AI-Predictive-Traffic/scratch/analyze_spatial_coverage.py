import json
import sumolib
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path("d:/AIML/Projects/Major")
net_path = PROJECT_ROOT / "AI-Predictive-Traffic/simulation/mangaluru/presentation_selection2.net.xml"
net = sumolib.net.readNet(str(net_path))
(min_x, min_y), (max_x, max_y) = net.getBBoxXY()

# Load live OSM buildings
with open("AI-Predictive-Traffic/simulation/mangaluru/osm_buildings_live.json") as f:
    d = json.load(f)

nodes = {e["id"]: (e["lon"], e["lat"]) for e in d.get("elements", []) if e.get("type") == "node"}
ways = [e for e in d.get("elements", []) if e.get("type") == "way" and "building" in e.get("tags", {})]

osm_buildings = []
for w in ways:
    pts = [nodes[nid] for nid in w.get("nodes", []) if nid in nodes]
    if len(pts) >= 3:
        sumo_pts = [net.convertLonLat2XY(lon, lat) for lon, lat in pts]
        cx = sum(p[0] for p in sumo_pts) / len(sumo_pts)
        cy = sum(p[1] for p in sumo_pts) / len(sumo_pts)
        if min_x <= cx <= max_x and min_y <= cy <= max_y:
            osm_buildings.append({"id": w["id"], "cx": cx, "cy": cy, "tags": w.get("tags", {})})

# Load existing RoadNetwork.json buildings
with open("MangaluruDigitalTwin3D/Assets/Generated/RoadNetwork.json") as f:
    rn = json.load(f)
rn_buildings = rn.get("buildings", [])

print("=" * 80)
print("SPATIAL DISTRIBUTION ANALYSIS")
print("=" * 80)
print(f"Network Bounding Box: X=[{min_x:.1f}, {max_x:.1f}] (width={max_x-min_x:.1f}m)")
print(f"                      Y=[{min_y:.1f}, {max_y:.1f}] (height={max_y-min_y:.1f}m)")
print(f"Total Roads (Edges):  {len(net.getEdges())}")
print(f"Existing RoadNetwork.json Buildings: {len(rn_buildings)}")
print(f"Live OSM Buildings Available:        {len(osm_buildings)}")

# Grid partition 4x4 (approx 520m x 400m per cell)
grid_w = (max_x - min_x) / 4.0
grid_h = (max_y - min_y) / 4.0

grid_roads = defaultdict(float)
for e in net.getEdges():
    if e.getFunction() == "internal": continue
    shape = e.getLanes()[0].getShape()
    cx = sum(p[0] for p in shape) / len(shape)
    cy = sum(p[1] for p in shape) / len(shape)
    gx = min(3, int((cx - min_x) / grid_w))
    gy = min(3, int((cy - min_y) / grid_h))
    grid_roads[(gx, gy)] += e.getLength()

grid_rn_bldg = defaultdict(int)
for b in rn_buildings:
    cx = sum(p['x'] for p in b['shape']) / len(b['shape'])
    cy = sum(p['y'] for p in b['shape']) / len(b['shape'])
    gx = min(3, int((cx - min_x) / grid_w))
    gy = min(3, int((cy - min_y) / grid_h))
    grid_rn_bldg[(gx, gy)] += 1

grid_osm_bldg = defaultdict(int)
for b in osm_buildings:
    gx = min(3, int((b["cx"] - min_x) / grid_w))
    gy = min(3, int((b["cy"] - min_y) / grid_h))
    grid_osm_bldg[(gx, gy)] += 1

print("\nGrid Matrix (4x4, row 3=North, row 0=South; col 0=West, col 3=East):")
print("Format: [Road Length (m) | Existing Bldgs | Live OSM Bldgs]")
print("-" * 75)
for gy in range(3, -1, -1):
    row_str = []
    for gx in range(4):
        rl = grid_roads[(gx, gy)]
        eb = grid_rn_bldg[(gx, gy)]
        ob = grid_osm_bldg[(gx, gy)]
        row_str.append(f"({gx},{gy}): {rl:5.0f}m | {eb:3d} | {ob:3d}")
    print("  " + "  ||  ".join(row_str[:2]))
    print("  " + "  ||  ".join(row_str[2:]))
    print("-" * 75)

