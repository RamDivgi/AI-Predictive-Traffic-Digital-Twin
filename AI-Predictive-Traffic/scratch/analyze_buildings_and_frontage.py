import json
import math
import struct
import zlib
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

def analyze():
    road_path = Path(r"D:\AIML\Projects\Major\MangaluruDigitalTwin3D\Assets\Generated\RoadNetwork.json")
    with open(road_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    buildings = data.get("buildings", [])
    edges = data.get("edges", [])
    
    # Collect road segments
    road_segments = []
    for edge in edges:
        for lane in edge.get("lanes", []):
            shape = lane.get("shape", [])
            for i in range(len(shape) - 1):
                p1, p2 = shape[i], shape[i+1]
                road_segments.append((p1['x'], p1['y'], p2['x'], p2['y'], edge['id']))
                
    print(f"Total road segments: {len(road_segments)}")
    print(f"Total buildings: {len(buildings)}")
    
    # Analyze nearest road frontage for first 10 buildings
    for b in buildings[:10]:
        pts = b.get("shape", [])
        if len(pts) < 3: continue
        xs = [p['x'] for p in pts]
        zs = [p['y'] for p in pts]
        cx = sum(xs) / len(xs)
        cz = sum(zs) / len(zs)
        
        # Find nearest road segment
        min_d = 1e9
        best_seg = None
        best_proj = None
        for seg in road_segments:
            d, px, pz = distance_pt_to_seg(cx, cz, seg[0], seg[1], seg[2], seg[3])
            if d < min_d:
                min_d = d
                best_seg = seg
                best_proj = (px, pz)
                
        # Vector from road to building centroid
        to_bldg_x = cx - best_proj[0]
        to_bldg_z = cz - best_proj[1]
        
        # Road tangent vector
        rd_dx = best_seg[2] - best_seg[0]
        rd_dz = best_seg[3] - best_seg[1]
        rd_len = math.hypot(rd_dx, rd_dz)
        if rd_len > 0:
            rd_dx /= rd_len
            rd_dz /= rd_len
            
        # Road normal pointing towards building
        norm_x = -rd_dz
        norm_z = rd_dx
        dot = norm_x * to_bldg_x + norm_z * to_bldg_z
        if dot < 0:
            norm_x = -norm_x
            norm_z = -norm_z
            
        road_angle_deg = math.degrees(math.atan2(rd_dx, rd_dz))
        face_road_angle = math.degrees(math.atan2(-to_bldg_x, -to_bldg_z)) # facing road
        
        print(f"Building {b['id'][:12]}: dist to road={min_d:.1f}m, road angle={road_angle_deg:.1f}°, face road angle={face_road_angle:.1f}°")

if __name__ == "__main__":
    analyze()
