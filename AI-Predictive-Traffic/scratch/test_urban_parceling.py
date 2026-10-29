import json
import math
import sumolib
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path("d:/AIML/Projects/Major")
net_path = PROJECT_ROOT / "AI-Predictive-Traffic/simulation/mangaluru/presentation_selection2.net.xml"
net = sumolib.net.readNet(str(net_path))
(min_x, min_y), (max_x, max_y) = net.getBBoxXY()

# 1. Load authentic OSM buildings from test_merge_footprints
with open("AI-Predictive-Traffic/simulation/mangaluru/osm_buildings_live.json") as f:
    osm_live = json.load(f)

nodes = {e['id']: (e['lon'], e['lat']) for e in osm_live.get('elements', []) if e.get('type') == 'node'}
ways = [e for e in osm_live.get('elements', []) if e.get('type') == 'way' and 'building' in e.get('tags', {})]

auth_bldgs = []
for w in ways:
    pts = [nodes[nid] for nid in w.get('nodes', []) if nid in nodes]
    if len(pts) >= 3:
        sumo_pts = [net.convertLonLat2XY(lon, lat) for lon, lat in pts]
        cx = sum(p[0] for p in sumo_pts) / len(sumo_pts)
        cy = sum(p[1] for p in sumo_pts) / len(sumo_pts)
        if min_x <= cx <= max_x and min_y <= cy <= max_y:
            auth_bldgs.append({
                'id': f"osm_{w['id']}",
                'cx': cx,
                'cy': cy,
                'shape': sumo_pts,
                'type': w.get('tags', {}).get('building', 'yes'),
                'name': w.get('tags', {}).get('name', '')
            })

# Load hospitals
hosp_file = PROJECT_ROOT / "AI-Predictive-Traffic/simulation/mangaluru/presentation_labels.add.xml"
import xml.etree.ElementTree as ET
tree = ET.parse(str(hosp_file))
hospitals = []
for poi in tree.getroot().findall('poi'):
    if poi.get('type') == 'hospital':
        hospitals.append((float(poi.get('x')), float(poi.get('y'))))

print(f"Loaded {len(auth_bldgs)} authentic OSM buildings.")
print(f"Loaded {len(hospitals)} hospital landmarks.")

# Collect road lane segments
road_segments = []
for e in net.getEdges():
    if e.getFunction() == "internal": continue
    for lane in e.getLanes():
        shape = lane.getShape()
        w = lane.getWidth()
        for i in range(len(shape) - 1):
            p1 = shape[i]
            p2 = shape[i+1]
            road_segments.append((p1, p2, w, e.getID()))

def dist_to_roads(px, py):
    min_dist = float('inf')
    for p1, p2, w, _ in road_segments:
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        l2 = dx*dx + dy*dy
        if l2 < 0.0001:
            t = 0.0
        else:
            t = max(0.0, min(1.0, ((px - p1[0])*dx + (py - p1[1])*dy) / l2))
        proj_x = p1[0] + t * dx
        proj_y = p1[1] + t * dy
        d = math.hypot(px - proj_x, py - proj_y) - (w * 0.5)
        if d < min_dist:
            min_dist = d
            if min_dist < 2.5: break # early exit
    return min_dist

# Spatial index of placed buildings
placed_centers = [(b['cx'], b['cy']) for b in auth_bldgs]

infill_bldgs = []
parcel_step = 22.0  # Frontage spacing along road

# Arterial road IDs (Balmatta, Mother Teresa, Father Muller, Falnir)
arterials = set()
for e in net.getEdges():
    name = e.getName() or ""
    eid = e.getID()
    if any(k in name.lower() for k in ['balmatta', 'teresa', 'muller', 'falnir', 'jyothi', 'bendoor']) or e.getSpeed() > 11.0:
        arterials.add(eid)

print(f"Identified {len(arterials)} arterial edges.")

# Generate frontage parcels along edges
for e in net.getEdges():
    if e.getFunction() == "internal": continue
    eid = e.getID()
    lanes = e.getLanes()
    if not lanes: continue
    shape = lanes[0].getShape()
    total_w = sum(l.getWidth() for l in lanes)
    is_arterial = eid in arterials
    
    # Compute cumulative length along shape
    for i in range(len(shape) - 1):
        p1 = shape[i]
        p2 = shape[i+1]
        seg_dx = p2[0] - p1[0]
        seg_dy = p2[1] - p1[1]
        seg_len = math.hypot(seg_dx, seg_dy)
        if seg_len < 15.0: continue
        
        ux = seg_dx / seg_len
        uy = seg_dy / seg_len
        # Normals
        nlx, nly = -uy, ux
        nrx, nry = uy, -ux
        
        # Test steps along segment
        num_slots = int(seg_len / parcel_step)
        for s in range(num_slots):
            dist_along = (s + 0.5) * parcel_step
            base_x = p1[0] + ux * dist_along
            base_y = p1[1] + uy * dist_along
            
            # Try both Left and Right side of road
            for side, (nx, ny) in [('L', (nlx, nly)), ('R', (nrx, nry))]:
                # Setback from road centerline: half road width + sidewalk (1.5) + setback (3.5 to 6.0) + half bldg depth (6.5)
                setback = (total_w * 0.5) + 1.5 + (4.0 if not is_arterial else 5.5) + 6.5
                bx = base_x + nx * setback
                by = base_y + ny * setback
                
                # 1. Bounds check
                if not (min_x + 10 <= bx <= max_x - 10 and min_y + 10 <= by <= max_y - 10):
                    continue
                
                # 2. Hospital clearance (keep >= 35m from all hospitals)
                if any(math.hypot(bx - hx, by - hy) < 35.0 for hx, hy in hospitals):
                    continue
                
                # 3. Clearance to existing placed buildings (>= 13.5m)
                if any(math.hypot(bx - px, by - py) < 13.5 for px, py in placed_centers):
                    continue
                
                # 4. Strict clearance to road surfaces (>= 2.5m)
                clearance = dist_to_roads(bx, by)
                if clearance < 2.5:
                    continue
                
                # Valid parcel! Determine dimensions and typology
                facing_deg = math.degrees(math.atan2(-nx, -ny))
                b_width = 14.0 if not is_arterial else 18.0
                b_depth = 12.0 if not is_arterial else 15.0
                
                # Create rectangular footprint
                hw = b_width * 0.5
                hd = b_depth * 0.5
                rad = math.radians(facing_deg)
                cos_a = math.cos(rad)
                sin_a = math.sin(rad)
                
                # Corners relative to center
                corners = [(-hw, -hd), (hw, -hd), (hw, hd), (-hw, hd)]
                footprint = []
                for cx_loc, cy_loc in corners:
                    gx = bx + (cx_loc * cos_a - cy_loc * sin_a)
                    gy = by + (cx_loc * sin_a + cy_loc * cos_a)
                    footprint.append({'x': round(gx, 2), 'y': round(gy, 2)})
                
                typology = 'commercial' if is_arterial else ('house' if (len(infill_bldgs) % 3 != 0) else 'apartments')
                
                infill_bldgs.append({
                    'id': f"infill_{eid}_{s}_{side}",
                    'cx': bx,
                    'cy': by,
                    'shape': footprint,
                    'type': typology,
                    'facing': facing_deg,
                    'is_infill': True
                })
                placed_centers.append((bx, by))

print(f"\nGenerated {len(infill_bldgs)} high-quality street-frontage infill parcels!")
print(f"Total city buildings (Authentic {len(auth_bldgs)} + Infill {len(infill_bldgs)}): {len(auth_bldgs) + len(infill_bldgs)}")

# Grid coverage after infill
grid_w = (max_x - min_x) / 4.0
grid_h = (max_y - min_y) / 4.0
grid_total = defaultdict(int)
for b in auth_bldgs:
    gx = min(3, int((b['cx'] - min_x) / grid_w))
    gy = min(3, int((b['cy'] - min_y) / grid_h))
    grid_total[(gx, gy)] += 1
for b in infill_bldgs:
    gx = min(3, int((b['cx'] - min_x) / grid_w))
    gy = min(3, int((b['cy'] - min_y) / grid_h))
    grid_total[(gx, gy)] += 1

print("\nGrid Matrix Coverage After Infill (Total Buildings per 520m x 400m cell):")
print("-" * 65)
for gy in range(3, -1, -1):
    row_str = [f"({gx},{gy}): {grid_total[(gx, gy)]:3d}" for gx in range(4)]
    print("  " + "  ||  ".join(row_str[:2]) + "  ||  " + "  ||  ".join(row_str[2:]))
print("-" * 65)
