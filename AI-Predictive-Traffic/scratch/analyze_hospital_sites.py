import json
import math
from pathlib import Path
from shapely.geometry import Polygon, LineString, Point

net_path = Path(__file__).resolve().parent.parent / "visualization" / "RoadNetwork.json"
with open(net_path, "r") as f:
    data = json.load(f)

hospitals = data.get("hospitals", [])
edges = data.get("edges", [])
junctions = data.get("junctions", [])
buildings = data.get("buildings", [])

print(f"Total Hospitals in RoadNetwork.json: {len(hospitals)}")

# Build road segments
road_segments = []
for edge in edges:
    for lane in edge.get("lanes", []):
        shape = lane.get("shape", [])
        w = lane.get("width", 3.5)
        for i in range(len(shape) - 1):
            p1 = (shape[i]["x"], shape[i]["y"])
            p2 = (shape[i+1]["x"], shape[i+1]["y"])
            road_segments.append((p1, p2, w * 0.5, edge.get("id")))

# Analyze each hospital
for h in hospitals:
    hid = h.get("id")
    name = h.get("name")
    hx = h.get("x")
    hy = h.get("y")
    
    # Distance to nearest road
    min_dist = float("inf")
    nearest_edge = None
    nearest_pt = None
    for p1, p2, hw, eid in road_segments:
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        l2 = dx*dx + dy*dy
        t = max(0.0, min(1.0, ((hx - p1[0])*dx + (hy - p1[1])*dy) / l2)) if l2 > 0.0001 else 0.0
        proj_x = p1[0] + t * dx
        proj_y = p1[1] + t * dy
        dist = math.hypot(hx - proj_x, hy - proj_y) - hw
        if dist < min_dist:
            min_dist = dist
            nearest_edge = eid
            nearest_pt = (proj_x, proj_y)

    # Facing angle to nearest road
    to_x = nearest_pt[0] - hx
    to_y = nearest_pt[1] - hy
    facing = math.degrees(math.atan2(to_x, to_y))

    # Nearby buildings within 50m
    nearby_bldgs = []
    for b in buildings:
        pts = [(p["x"], p["y"]) for p in b.get("shape", [])]
        if not pts:
            continue
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        d = math.hypot(hx - cx, hy - cy)
        if d < 45.0:
            nearby_bldgs.append((b["id"], d, b.get("is_infill", False)))

    print(f"[{hid}] {name}")
    print(f"  Pos: ({hx:.1f}, {hy:.1f}) | Road Dist: {min_dist:.1f}m | Nearest Edge: {nearest_edge} | Facing: {facing:.1f}°")
    print(f"  Nearby Buildings (<45m): {len(nearby_bldgs)}")
    for nb in nearby_bldgs[:3]:
        print(f"    - {nb[0]} (dist={nb[1]:.1f}m, infill={nb[2]})")
