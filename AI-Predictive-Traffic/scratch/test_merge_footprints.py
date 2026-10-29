import json
import gzip
import xml.etree.ElementTree as ET
import sumolib
from pathlib import Path

PROJECT_ROOT = Path("d:/AIML/Projects/Major")
net_path = PROJECT_ROOT / "AI-Predictive-Traffic/simulation/mangaluru/presentation_selection2.net.xml"
net = sumolib.net.readNet(str(net_path))
(min_x, min_y), (max_x, max_y) = net.getBBoxXY()

# 1. Live OSM
with open("AI-Predictive-Traffic/simulation/mangaluru/osm_buildings_live.json") as f:
    osm_live = json.load(f)

nodes = {e['id']: (e['lon'], e['lat']) for e in osm_live.get('elements', []) if e.get('type') == 'node'}
ways = [e for e in osm_live.get('elements', []) if e.get('type') == 'way' and 'building' in e.get('tags', {})]

bldgs_by_id = {}
for w in ways:
    pts = [nodes[nid] for nid in w.get('nodes', []) if nid in nodes]
    if len(pts) >= 3:
        sumo_pts = [{'x': round(p[0], 2), 'y': round(p[1], 2)} for p in [net.convertLonLat2XY(lon, lat) for lon, lat in pts]]
        cx = sum(p['x'] for p in sumo_pts) / len(sumo_pts)
        cy = sum(p['y'] for p in sumo_pts) / len(sumo_pts)
        if min_x <= cx <= max_x and min_y <= cy <= max_y:
            wid = w['id']
            bid = f"osm_way_{wid}"
            tags = w.get('tags', {})
            bldgs_by_id[bid] = {
                'id': bid,
                'name': tags.get('name', ''),
                'building_type': tags.get('building', 'yes'),
                'shape': sumo_pts,
                'levels': int(tags['building:levels']) if tags.get('building:levels', '').isdigit() else None
            }

print(f"From live OSM: {len(bldgs_by_id)} buildings")

# 2. Existing osm.poly.xml.gz
with gzip.open("AI-Predictive-Traffic/simulation/mangaluru/osm.poly.xml.gz", "rt") as f:
    tree = ET.parse(f)
    root = tree.getroot()

parks = []
poly_bldgs = 0
for poly in root.findall('poly'):
    ptype = poly.get('type', '')
    shape_str = poly.get('shape', '')
    if not shape_str: continue
    pts = []
    for pt in shape_str.split():
        c = pt.split(',')
        if len(c) >= 2: pts.append({'x': round(float(c[0]), 2), 'y': round(float(c[1]), 2)})
    if len(pts) < 3: continue
    cx = sum(p['x'] for p in pts) / len(pts)
    cy = sum(p['y'] for p in pts) / len(pts)
    if not (min_x <= cx <= max_x and min_y <= cy <= max_y): continue

    if 'building' in ptype:
        pid = poly.get('id')
        # Check duplicate
        is_dup = any(abs(b['shape'][0]['x'] - pts[0]['x']) < 5.0 and abs(b['shape'][0]['y'] - pts[0]['y']) < 5.0 for b in bldgs_by_id.values())
        if not is_dup:
            poly_bldgs += 1
            bldgs_by_id[pid] = {
                'id': pid,
                'name': '',
                'building_type': ptype.replace('building.', ''),
                'shape': pts,
                'levels': None
            }
    elif any(k in ptype for k in ['park', 'garden', 'pitch', 'meadow', 'wood', 'grass']):
        parks.append({
            'id': poly.get('id'),
            'type': ptype,
            'shape': pts
        })

print(f"Additional non-overlapping from poly.xml: {poly_bldgs}")
print(f"Total combined authentic building footprints: {len(bldgs_by_id)}")
print(f"Total parks/green spaces: {len(parks)}")
