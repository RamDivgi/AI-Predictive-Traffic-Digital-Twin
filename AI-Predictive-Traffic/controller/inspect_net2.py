import os
import sumolib
import gzip
import xml.etree.ElementTree as ET
import math

NETWORK_PATH = "D:/AIML/Projects/Major/AI-Predictive-Traffic/simulation/mangaluru/mangaluru_ai.net.xml.gz"
OSM_PATH = "C:/Users/ram/Sumo/2026-08-20-22-55-58/osm_bbox.osm.xml.gz"

if not os.path.exists(NETWORK_PATH) or not os.path.exists(OSM_PATH):
    print("Files not found")
    exit(1)

net = sumolib.net.readNet(NETWORK_PATH)

def get_hospitals(net):
    hospitals = []
    needed_nodes = set()
    hospital_ways = []
    
    with gzip.open(OSM_PATH, 'rt', encoding='utf-8') as f:
        context = ET.iterparse(f, events=('end',))
        for event, elem in context:
            if elem.tag in ('node', 'way'):
                tags = {child.get('k'): child.get('v') for child in elem if child.tag == 'tag' and child.get('k')}
                if tags.get('amenity') == 'hospital' or tags.get('healthcare') in ['hospital', 'clinic', 'medical_centre']:
                    name = tags.get('name', 'Unknown')
                    osm_id = elem.attrib.get('id', 'N/A')
                    if elem.tag == 'node':
                        lat = float(elem.attrib['lat'])
                        lon = float(elem.attrib['lon'])
                        hospitals.append({'name': name, 'id': osm_id, 'lat': lat, 'lon': lon})
                    elif elem.tag == 'way':
                        nd = elem.find('nd')
                        if nd is not None and nd.attrib.get('ref'):
                            ref = nd.attrib.get('ref')
                            needed_nodes.add(ref)
                            hospital_ways.append({'name': name, 'id': osm_id, 'ref': ref})
            elem.clear()
            
    if needed_nodes:
        with gzip.open(OSM_PATH, 'rt', encoding='utf-8') as f:
            context = ET.iterparse(f, events=('end',))
            for event, elem in context:
                if elem.tag == 'node':
                    node_id = elem.attrib.get('id')
                    if node_id in needed_nodes:
                        lat = float(elem.attrib['lat'])
                        lon = float(elem.attrib['lon'])
                        for hw in hospital_ways:
                            if hw['ref'] == node_id:
                                hospitals.append({'name': hw['name'], 'id': hw['id'], 'lat': lat, 'lon': lon})
                        needed_nodes.remove(node_id)
                        if not needed_nodes:
                            break
                elem.clear()

    mapped = []
    for h in hospitals:
        lat = h.get('lat')
        lon = h.get('lon')
        if lat and lon:
            try:
                x, y = net.convertLonLat2XY(lon, lat)
                nearest_edges = net.getNeighboringEdges(x, y, r=500.0)
                suitable = [(edge, dist) for edge, dist in nearest_edges if edge.allows("passenger")]
                if suitable:
                    suitable.sort(key=lambda item: item[1])
                    best_edge = suitable[0][0]
                    mapped.append({'name': h['name'], 'coords': (lat, lon), 'edge': best_edge, 'xy': (x,y)})
            except Exception:
                pass
    return mapped

hospitals = get_hospitals(net)
tls_nodes = [n for n in net.getNodes() if n.getType() == "traffic_light"]

print(f"Found {len(hospitals)} hospitals")
for h in hospitals:
    print(f"\nHospital: {h['name']} at {h['xy']}")
    # Find closest TLS
    hx, hy = h['xy']
    closest_tls = None
    min_dist = float('inf')
    for n in tls_nodes:
        nx, ny = n.getCoord()
        dist = math.hypot(nx - hx, ny - hy)
        if dist < min_dist:
            min_dist = dist
            closest_tls = n
    if closest_tls:
        print(f"  Closest TLS: {closest_tls.getID()} at distance {min_dist:.2f}")

