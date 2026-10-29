import json
import math
from pathlib import Path

net_path = Path(__file__).resolve().parent.parent / "visualization" / "RoadNetwork.json"
with open(net_path, "r") as f:
    data = json.load(f)

hospitals = data.get("hospitals", [])
buildings = data.get("buildings", [])

print(f"{'Hospital ID':<32} {'Name':<30} {'Matched OSM Building':<25} {'Dist(m)':<8} {'Footprint WxH(m)'}")
print("-" * 110)

matched_bldg_ids = set()

for h in hospitals:
    hid = h["id"]
    hname = h["name"]
    hx = h["x"]
    hy = h["y"]

    best_b = None
    best_dist = float("inf")

    for b in buildings:
        pts = [(p["x"], p["y"]) for p in b.get("shape", [])]
        if not pts:
            continue
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        d = math.hypot(hx - cx, hy - cy)
        if d < best_dist:
            best_dist = d
            best_b = b

    if best_b and best_dist < 35.0:
        pts = [(p["x"], p["y"]) for p in best_b["shape"]]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        w = max(xs) - min(xs)
        d = max(ys) - min(ys)
        b_name = best_b.get("name", "")
        matched_bldg_ids.add(best_b["id"])
        print(f"{hid:<32} {hname:<30} {best_b['id']:<25} {best_dist:<8.1f} {w:.1f} x {d:.1f} m ({b_name})")
    else:
        print(f"{hid:<32} {hname:<30} {'[POI only - no OSM poly]':<25} {best_dist:<8.1f}")

print(f"\nTotal matched OSM building polygons: {len(matched_bldg_ids)}")
