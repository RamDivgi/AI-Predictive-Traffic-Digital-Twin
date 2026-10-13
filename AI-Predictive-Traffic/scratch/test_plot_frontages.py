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

def analyze_plot_frontages():
    road_path = Path(r"D:\AIML\Projects\Major\MangaluruDigitalTwin3D\Assets\Generated\RoadNetwork.json")
    with open(road_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    buildings = data.get("buildings", [])
    edges = data.get("edges", [])
    
    road_segments = []
    for edge in edges:
        for lane in edge.get("lanes", []):
            shape = lane.get("shape", [])
            for i in range(len(shape) - 1):
                p1, p2 = shape[i], shape[i+1]
                road_segments.append((p1['x'], p1['y'], p2['x'], p2['y']))
                
    aligned_count = 0
    for b in buildings[:20]:
        pts = b.get("shape", [])
        if len(pts) < 3: continue
        xs = [p['x'] for p in pts]
        zs = [p['y'] for p in pts]
        cx = sum(xs) / len(xs)
        cz = sum(zs) / len(zs)
        
        # 1. Find nearest road point to plot centroid
        min_rd_d = 1e9
        nearest_rd_pt = None
        nearest_rd_dir = None
        for seg in road_segments:
            d, px, pz = distance_pt_to_seg(cx, cz, seg[0], seg[1], seg[2], seg[3])
            if d < min_rd_d:
                min_rd_d = d
                nearest_rd_pt = (px, pz)
                dx, dz = seg[2] - seg[0], seg[3] - seg[1]
                l = math.hypot(dx, dz)
                nearest_rd_dir = (dx/l, dz/l) if l > 0 else (1, 0)
                
        # 2. Vector from building centroid towards the road
        to_road_x = nearest_rd_pt[0] - cx
        to_road_z = nearest_rd_pt[1] - cz
        d_to_road = math.hypot(to_road_x, to_road_z)
        if d_to_road > 0:
            to_road_x /= d_to_road
            to_road_z /= d_to_road
            
        # Frontage angle facing towards the road
        angle_towards_road = math.degrees(math.atan2(to_road_x, to_road_z))
        
        # 3. Find plot's longest edge or edge most parallel to road
        best_dot = -1
        best_edge_angle = 0
        n = len(pts)
        for i in range(n):
            next_i = (i + 1) % n
            ex = pts[next_i]['x'] - pts[i]['x']
            ez = pts[next_i]['y'] - pts[i]['y']
            el = math.hypot(ex, ez)
            if el > 2.0:
                ex /= el
                ez /= el
                # Dot product with road tangent
                dot = abs(ex * nearest_rd_dir[0] + ez * nearest_rd_dir[1])
                if dot > best_dot:
                    best_dot = dot
                    best_edge_angle = math.degrees(math.atan2(ex, ez))
                    
        print(f"Building {b['id'][:10]}: road_dist={min_rd_d:4.1f}m, angle_towards_road={angle_towards_road:6.1f}°, best_edge_parallelism={best_dot:.2f}")

if __name__ == "__main__":
    analyze_plot_frontages()
