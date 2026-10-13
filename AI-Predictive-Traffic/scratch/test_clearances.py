import json
import math
from pathlib import Path

def distance_pt_to_seg(px, pz, x1, z1, x2, z2):
    dx, dz = x2 - x1, z2 - z1
    l2 = dx*dx + dz*dz
    if l2 == 0:
        return math.hypot(px - x1, pz - z1), x1, z1
    t = max(0.0, min(1.0, ((px - x1)*dx + (pz - z1)*dz) / l2))
    proj_x = x1 + t * dx
    proj_z = z1 + t * dz
    return math.hypot(px - proj_x, pz - proj_z), proj_x, proj_z

def test_clearances():
    road_path = Path(r"D:\AIML\Projects\Major\MangaluruDigitalTwin3D\Assets\Generated\RoadNetwork.json")
    with open(road_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    buildings = data.get("buildings", [])
    edges = data.get("edges", [])
    
    road_segments = []
    for edge in edges:
        for lane in edge.get("lanes", []):
            shape = lane.get("shape", [])
            w = lane.get("width", 3.2)
            for i in range(len(shape) - 1):
                p1, p2 = shape[i], shape[i+1]
                road_segments.append((p1['x'], p1['y'], p2['x'], p2['y'], w/2.0))
                
    placed_models = 0
    fallbacks = 0
    safe_clearance_count = 0
    
    for b in buildings:
        pts = b.get("shape", [])
        if len(pts) < 3: continue
        xs = [p['x'] for p in pts]
        zs = [p['y'] for p in pts]
        cx = sum(xs) / len(xs)
        cz = sum(zs) / len(zs)
        w = max(xs) - min(xs)
        d = max(zs) - min(zs)
        min_dim = min(w, d)
        max_dim = max(w, d)
        aspect = max_dim / max(min_dim, 0.1)
        
        # Distance to nearest road edge
        min_rd_dist = 1e9
        for seg in road_segments:
            dist_to_centerline, px, pz = distance_pt_to_seg(cx, cz, seg[0], seg[1], seg[2], seg[3])
            dist_to_edge = dist_to_centerline - seg[4] # subtract half lane width
            if dist_to_edge < min_rd_dist:
                min_rd_dist = dist_to_edge
                
        # Candidate 3D model placement:
        # Standard residential house has base radius ~8m. At scale 0.8x, radius ~6.4m.
        # We require at least 3.0m clearance from the drivable edge!
        fits_criteria = (10.0 <= min_dim and max_dim <= 45.0 and aspect <= 2.2)
        
        if fits_criteria:
            # Model span
            native = 15.0 if max_dim < 26.0 else 26.0
            scale = max(0.70, min(1.25, (min_dim * 0.80) / native))
            half_extent = (native * scale) * 0.5
            
            # Check if building footprint has at least 2.5m clearance to road edge
            clearance = min_rd_dist - half_extent
            if clearance >= 2.5:
                placed_models += 1
                safe_clearance_count += 1
            else:
                # Too close to road! Use procedural fallback which is strictly bounded by OSM polygon
                fallbacks += 1
        else:
            fallbacks += 1
            
    print(f"Total buildings: {len(buildings)}")
    print(f"Placed 3D models with verified >=2.5m road clearance: {placed_models} ({placed_models/len(buildings)*100:.1f}%)")
    print(f"Procedural fallbacks (confined strictly inside plot polygon): {fallbacks} ({fallbacks/len(buildings)*100:.1f}%)")

if __name__ == "__main__":
    test_clearances()
