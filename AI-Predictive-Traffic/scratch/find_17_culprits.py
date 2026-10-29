import json
import math
from pathlib import Path
from shapely.geometry import Polygon, LineString, Point
from shapely.ops import unary_union

NET_PATH = Path(__file__).resolve().parent.parent.parent / "MangaluruDigitalTwin3D" / "Assets" / "Generated" / "RoadNetwork.json"
with open(NET_PATH, "r") as f:
    net_data = json.load(f)

buildings = net_data["buildings"]
print(f"Total buildings: {len(buildings)}")

# Check conflicts
conflicts = [b for b in buildings if "conflict" in b and b["conflict"].get("type") == "source_data_road_encroachment"]
print(f"Total documented source conflicts: {len(conflicts)}")

# Collect road segments
road_segments = []
for edge in net_data.get("edges", []):
    for lane in edge.get("lanes", []):
        shape = lane.get("shape", [])
        w = lane.get("width", 3.5)
        for i in range(len(shape) - 1):
            road_segments.append((
                (shape[i]["x"], shape[i]["y"]),
                (shape[i+1]["x"], shape[i+1]["y"]),
                w * 0.5
            ))

# Collect junctions
junc_polys = []
for junc in net_data.get("junctions", []):
    shape = junc.get("shape", [])
    if len(shape) >= 3:
        junc_polys.append(Polygon([(p["x"], p["y"]) for p in shape]))

print(f"Road segments: {len(road_segments)}, Junction polys: {len(junc_polys)}")

# Now simulate what VisualAcceptanceAgent does:
# For each building, test corners against segments and junctions
flagged = []
for b in buildings:
    is_conflict = "conflict" in b and b["conflict"].get("type") == "source_data_road_encroachment"
    bid = b["id"]
    pts = [(p["x"], p["y"]) for p in b.get("shape", [])]
    if len(pts) < 3:
        continue
    
    # Check if building penetrates
    penetrates = False
    pen_reason = ""
    for px, py in pts:
        for p1, p2, hw in road_segments:
            dx = p2[0] - p1[0]
            dy = p2[1] - p1[1]
            l2 = dx*dx + dy*dy
            t = max(0.0, min(1.0, ((px - p1[0])*dx + (py - p1[1])*dy) / l2)) if l2 > 0.0001 else 0.0
            proj_x = p1[0] + t * dx
            proj_y = p1[1] + t * dy
            dist = math.hypot(px - proj_x, py - proj_y) - hw
            if dist < 0.1:
                penetrates = True
                pen_reason = f"road dist={dist:.2f}"
                break
        if penetrates:
            break
        
        pt = Point(px, py)
        for jp in junc_polys:
            if jp.contains(pt):
                penetrates = True
                pen_reason = "inside junction"
                break
        if penetrates:
            break

    if penetrates:
        flagged.append((bid, is_conflict, pen_reason))

print(f"Total penetrating buildings: {len(flagged)}")
print(f"  Documented conflicts: {len([f for f in flagged if f[1]])}")
print(f"  Non-conflicts: {len([f for f in flagged if not f[1]])}")
for f in [f for f in flagged if not f[1]]:
    print(f"    Unexpected culprit: {f}")
