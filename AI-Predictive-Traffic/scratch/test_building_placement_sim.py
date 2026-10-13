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

def simulate_building_placement():
    road_path = Path(r"D:\AIML\Projects\Major\MangaluruDigitalTwin3D\Assets\Generated\RoadNetwork.json")
    with open(road_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    buildings = data.get("buildings", [])
    edges = data.get("edges", [])
    hospitals = data.get("hospitals", [])
    
    # Road segments
    road_segments = []
    for edge in edges:
        for lane in edge.get("lanes", []):
            shape = lane.get("shape", [])
            w = lane.get("width", 3.2)
            for i in range(len(shape) - 1):
                p1, p2 = shape[i], shape[i+1]
                road_segments.append((p1['x'], p1['y'], p2['x'], p2['y'], w/2.0))
                
    placed_models = []
    fallbacks = []
    
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
        
        # 1. Find nearest road point
        min_dist_to_center = 1e9
        nearest_proj = None
        half_lane_w = 1.6
        for seg in road_segments:
            dist, px, pz = distance_pt_to_seg(cx, cz, seg[0], seg[1], seg[2], seg[3])
            if dist < min_dist_to_center:
                min_dist_to_center = dist
                nearest_proj = (px, pz)
                half_lane_w = seg[4]
                
        dist_to_road_edge = min_dist_to_center - half_lane_w
        
        # 2. Check hospital proximity (keep hospital parcel clear)
        near_hosp = False
        for h in hospitals:
            if math.hypot(cx - h['x'], cz - h['y']) < 30.0:
                near_hosp = True
                break
                
        # 3. Model suitability
        fits = (10.0 <= min_dim and max_dim <= 45.0 and aspect <= 2.2 and not near_hosp)
        
        if fits:
            native = 15.0 if max_dim < 26.0 else 26.0
            scale = max(0.70, min(1.20, (min_dim * 0.80) / native))
            half_span = (native * scale) * 0.5
            clearance = dist_to_road_edge - half_span
            
            if clearance >= 2.5:
                # Calculate frontage angle facing road
                to_road_x = nearest_proj[0] - cx
                to_road_z = nearest_proj[1] - cz
                face_angle = math.degrees(math.atan2(to_road_x, to_road_z))
                placed_models.append({
                    "id": b['id'],
                    "cx": cx, "cz": cz,
                    "scale": scale,
                    "angle": face_angle,
                    "clearance": clearance
                })
            else:
                fallbacks.append(b['id'])
        else:
            fallbacks.append(b['id'])
            
    print(f"Total buildings: {len(buildings)}")
    print(f"Placed 3D models: {len(placed_models)} ({len(placed_models)/len(buildings)*100:.1f}%)")
    print(f"Procedural fallbacks: {len(fallbacks)} ({len(fallbacks)/len(buildings)*100:.1f}%)")
    clearances = [m['clearance'] for m in placed_models]
    print(f"Road clearances for placed models: min={min(clearances):.2f}m, max={max(clearances):.2f}m, avg={sum(clearances)/len(clearances):.2f}m")
    print(f"Violations (<2.5m road clearance): {sum(1 for c in clearances if c < 2.5)}")

if __name__ == "__main__":
    simulate_building_placement()
