import xml.etree.ElementTree as ET
import sumolib
import gzip
import math

net_path = 'd:/AIML/Projects/Major/AI-Predictive-Traffic/simulation/mangaluru/presentation_selection2.net.xml'
net = sumolib.net.readNet(net_path)
(min_x, min_y), (max_x, max_y) = net.getBBoxXY()

# Define specific points for major roads to avoid clutter
road_labels = [
    ("Balmatta Road", "1189020226#1", 0.5), # middle of the edge
    ("Mother Teresa Road", "1055574152#2", 0.5),
    ("Falnir-Jyothi Road", "-28069086#0", 0.5),
    ("Father Muller Road", "27191039#0", 0.5)
]

found_hospitals = []

# 1. First get known names from hospitals.add.xml (Highest priority)
try:
    tree = ET.parse('d:/AIML/Projects/Major/AI-Predictive-Traffic/simulation/mangaluru/hospitals.add.xml')
    for poi in tree.getroot().findall('poi'):
        hx = float(poi.get('x', 0))
        hy = float(poi.get('y', 0))
        if min_x <= hx <= max_x and min_y <= hy <= max_y:
            found_hospitals.append({
                'id': poi.get('id'), 
                'name': poi.get('name'), 
                'x': hx, 
                'y': hy
            })
except Exception as e:
    print(f"Warning reading hospitals.add.xml: {e}")

# 2. Extract remaining hospitals/clinics from osm.poly.xml.gz
def add_hospital(hid, ptype, x, y):
    # Check if too close to existing (100m cluster radius to prevent overlap)
    for h in found_hospitals:
        if math.hypot(h['x'] - x, h['y'] - y) < 100:
            return
    # Since real names were stripped by polyconvert, use generic but correct labels
    name = 'Clinic' if 'clinic' in ptype.lower() else 'Hospital'
    found_hospitals.append({'id': hid, 'name': name, 'x': x, 'y': y})

poly_path = 'd:/AIML/Projects/Major/AI-Predictive-Traffic/simulation/mangaluru/osm.poly.xml.gz'
try:
    with gzip.open(poly_path, 'rt') as f:
        tree = ET.parse(f)
        root = tree.getroot()
        
        # Check Polygons
        for poly in root.findall('poly'):
            ptype = poly.get('type', '')
            if 'hospital' in ptype.lower() or 'clinic' in ptype.lower():
                shape_str = poly.get('shape')
                if shape_str:
                    points = []
                    for pt in shape_str.split():
                        coords = pt.split(',')
                        if len(coords) >= 2:
                            points.append({'x': float(coords[0]), 'y': float(coords[1])})
                    if points:
                        cx = sum(p['x'] for p in points) / len(points)
                        cy = sum(p['y'] for p in points) / len(points)
                        if min_x <= cx <= max_x and min_y <= cy <= max_y:
                            add_hospital(poly.get('id'), ptype, cx, cy)

        # Check POIs
        for poi in root.findall('poi'):
            ptype = poi.get('type', '')
            if 'hospital' in ptype.lower() or 'clinic' in ptype.lower():
                hx = float(poi.get('x', 0))
                hy = float(poi.get('y', 0))
                if min_x <= hx <= max_x and min_y <= hy <= max_y:
                    add_hospital(poi.get('id'), ptype, hx, hy)
except Exception as e:
    print(f"Warning reading osm.poly.xml.gz: {e}")

# 3. Generate XML
root = ET.Element("additional")

for i, h in enumerate(found_hospitals):
    h_id = h['id']
    h_name = h['name']
    x = h['x']
    y = h['y']
    
    # Generate Red Cross shape (radius 5, width 2)
    shape_str = f"{x-1.5},{y-5} {x+1.5},{y-5} {x+1.5},{y-1.5} {x+5},{y-1.5} {x+5},{y+1.5} {x+1.5},{y+1.5} {x+1.5},{y+5} {x-1.5},{y+5} {x-1.5},{y+1.5} {x-5},{y+1.5} {x-5},{y-1.5} {x-1.5},{y-1.5}"
    
    poly = ET.SubElement(root, "poly", {
        "id": f"{h_id}_cross",
        "color": "red",
        "fill": "1",
        "layer": "100",
        "shape": shape_str
    })
    
    poi = ET.SubElement(root, "poi", {
        "id": h_id,
        "type": "hospital",
        "color": "0,0,0,0",
        "layer": "100",
        "x": str(x + 6), # Shifted slightly right to not overlap the cross
        "y": str(y),
        "name": h_name
    })

# Roads
for i, (name, edge_id, pos) in enumerate(road_labels):
    try:
        edge = net.getEdge(edge_id)
        lane = edge.getLanes()[0]
        # Get point at 50% along the lane
        length = lane.getLength()
        rx, ry = sumolib.geomhelper.positionAtShapeOffset(lane.getShape(), length * pos)
        
        # Ensure road labels don't collide with hospitals
        too_close = False
        for h in found_hospitals:
            if math.hypot(h['x'] - rx, h['y'] - ry) < 50:
                too_close = True
                break
        
        if not too_close:
            poi = ET.SubElement(root, "poi", {
                "id": f"label_{i}",
                "type": "road_label",
                "color": "0,0,0,0", # Transparent marker
                "layer": "100",
                "x": str(rx),
                "y": str(ry),
                "name": name
            })
    except Exception as e:
        print(f"Skipping {name}: {e}")

tree = ET.ElementTree(root)
out_path = "d:/AIML/Projects/Major/AI-Predictive-Traffic/simulation/mangaluru/presentation_labels.add.xml"
tree.write(out_path, encoding="utf-8", xml_declaration=True)
print(f"Labels generated to {out_path}.")
print(f"Total Hospitals/Clinics discovered: {len(found_hospitals)}")
for h in found_hospitals:
    print(f"- {h['name']} ({h['id']})")
