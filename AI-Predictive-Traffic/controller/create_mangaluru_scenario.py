import gzip
import xml.etree.ElementTree as ET
import sumolib
import math
import random
import os

NETWORK_PATH = "D:/AIML/Projects/Major/AI-Predictive-Traffic/simulation/mangaluru/osm.net.xml.gz"
OSM_PATH = "C:/Users/ram/Sumo/2026-08-20-22-55-58/osm_bbox.osm.xml.gz"
ROUTEOUT = "D:/AIML/Projects/AI-Predictive-Traffic/simulation/mangaluru/ambulance_test.rou.xml"
SUMOCFGOUT = "D:/AIML/Projects/AI-Predictive-Traffic/simulation/mangaluru/ambulance_test.sumocfg"

def distance(x1, y1, x2, y2):
    return math.hypot(x2 - x1, y2 - y1)

def get_hospitals(net):
    hospitals = []
    needed_nodes = set()
    hospital_ways = []
    
    with gzip.open(OSM_PATH, 'rt', encoding='utf-8') as f:
        context = ET.iterparse(f, events=('end',))
        for event, elem in context:
            if elem.tag in ('node', 'way', 'relation'):
                if elem.tag in ('node', 'way'):
                    tags = {child.get('k'): child.get('v') for child in elem if child.tag == 'tag' and child.get('k')}
                    is_medical = False
                    if tags.get('amenity') == 'hospital' or tags.get('healthcare') in ['hospital', 'clinic', 'medical_centre']:
                        is_medical = True
                        
                    if is_medical:
                        name = tags.get('name', 'Unknown Medical Facility')
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
                if elem.tag in ('node', 'way', 'relation'):
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

    # Map to SUMO
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

def create_scenario():
    print("============================================================")
    print("MANGALURU AMBULANCE SCENARIO")
    print("============================================================")

    print("Loading SUMO network...")
    net = sumolib.net.readNet(NETWORK_PATH)
    drivable_edges = [e for e in net.getEdges() if e.allows("passenger") and e.getFunction() != "internal"]
    
    # Check total traffic lights in the network
    all_nodes = net.getNodes()
    tls_nodes = [n for n in all_nodes if n.getType() == "traffic_light"]
    print(f"Total traffic light junctions in network: {len(tls_nodes)}")
    
    if len(tls_nodes) < 3:
        print("\nERROR: The network does not contain enough traffic lights to satisfy the requirement.")
        print(f"The network only has {len(tls_nodes)} traffic lights, but we need a route with >= 3.")
        print("CLEARLY REPORTING: The network cannot provide a valid route with >= 3 signalized junctions.")
        return
        
    print("Detecting hospitals...")
    hospitals = get_hospitals(net)
    if not hospitals:
        print("No hospitals found!")
        return
        
    random.seed(42)
    random.shuffle(drivable_edges)
    
    best_candidate = None
    best_score = -1000000
    
    print("Searching for routes with >= 3 signalized junctions...")
    attempts = 0
    for h in hospitals:
        dest_edge_obj = h['edge']
        hx, hy = h['xy']
        
        # shuffle edges per hospital to get variety
        cands = list(drivable_edges)
        random.shuffle(cands)
        
        for cand_edge in cands[:200]: # check a subset to be fast
            cand_x, cand_y = cand_edge.getFromNode().getCoord()
            dist = distance(cand_x, cand_y, hx, hy)
            if 2000 < dist < 6000:
                attempts += 1
                try:
                    route = net.getShortestPath(cand_edge, dest_edge_obj, vClass="passenger")
                except Exception:
                    continue
                    
                if route and route[0]:
                    edges = route[0]
                    total_length = sum(e.getLength() for e in edges)
                    
                    if 2000 <= total_length <= 8000:
                        # Count signals
                        signal_nodes = []
                        for e in edges:
                            to_node = e.getToNode()
                            if to_node.getType() == "traffic_light":
                                if to_node.getID() not in signal_nodes:
                                    signal_nodes.append(to_node.getID())
                        
                        sig_count = len(signal_nodes)
                        score = sig_count * 10000 - abs(total_length - 4000)
                        
                        if score > best_score:
                            best_score = score
                            best_candidate = {
                                'start_edge': cand_edge,
                                'dest_edge': dest_edge_obj,
                                'hospital': h,
                                'route': edges,
                                'length': total_length,
                                'signals': signal_nodes
                            }
                            
                        # Fast exit if we found a very good one (>= 3 signals is required)
                        if sig_count >= 3 and 2500 <= total_length <= 6000:
                            break
        if best_candidate and len(best_candidate['signals']) >= 3:
            break

    if not best_candidate or len(best_candidate['signals']) < 3:
        print("Could not find a valid route with at least 3 signalized junctions!")
        if best_candidate:
            print(f"Best found only had {len(best_candidate['signals'])} signals.")
        return
        
    route_edges = best_candidate['route']
    hospital_name = best_candidate['hospital']['name']
    hospital_coords = f"{best_candidate['hospital']['coords'][0]:.5f}, {best_candidate['hospital']['coords'][1]:.5f}"
    start_edge = best_candidate['start_edge']
    dest_edge = best_candidate['dest_edge']
    total_length = best_candidate['length']
    signals = best_candidate['signals']
    
    print(f"\nSelected hospital:")
    print(f"Hospital name: {hospital_name}")
    print(f"Hospital coordinates: {hospital_coords}")
    print(f"Destination SUMO edge: {dest_edge.getID()}")
    
    print(f"\nAmbulance start:")
    print(f"Start edge: {start_edge.getID()}")
    
    print(f"\nGenerated route:")
    edge_ids = [e.getID() for e in route_edges]
    out_edges = " -> ".join(edge_ids)
    if len(out_edges) > 100:
        out_edges = out_edges[:97] + "..."
    print(out_edges)
    
    print(f"\nRoute length: {total_length:.1f} meters")
    print(f"Number of edges: {len(route_edges)}")
    print(f"Number of signalized junctions: {len(signals)}")
    print(f"Signal IDs: {', '.join(signals)}")

    # Generate Background Traffic
    num_bg_vehicles = 300
    vehicles = []
    bg_count = 0
    
    print("Generating background traffic...")
    while bg_count < num_bg_vehicles:
        src = random.choice(drivable_edges)
        dst = random.choice(drivable_edges)
        if src != dst:
            try:
                bg_route = net.getShortestPath(src, dst, vClass="passenger")
                if bg_route and bg_route[0] and len(bg_route[0]) > 2:
                    depart = random.uniform(0.0, 100.0)
                    bg_edges = " ".join([e.getID() for e in bg_route[0]])
                    vehicles.append((depart, f"bg_{bg_count}", "passenger", bg_edges))
                    bg_count += 1
            except Exception:
                pass
            
    # Add ambulance at t=10.0
    vehicles.append((10.0, "ambulance", "ambulance", " ".join(edge_ids)))
    
    vehicles.sort(key=lambda x: x[0])
    
    print(f"\nBackground vehicles: {num_bg_vehicles}")

    # Write rou.xml
    with open(ROUTEOUT, "w") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write('<routes>\n')
        f.write('    <vType id="passenger" vClass="passenger" guiShape="passenger" maxSpeed="15.0"/>\n')
        f.write('    <vType id="ambulance" vClass="emergency" guiShape="emergency" speedFactor="1.5" accel="2.5" decel="3.5" color="red" emissionClass="HBEFA3/PC_G_EU4"/>\n')
        
        for depart, vid, vtype, route_str in vehicles:
            f.write(f'    <vehicle id="{vid}" type="{vtype}" depart="{depart:.1f}">\n')
            f.write(f'        <route edges="{route_str}"/>\n')
            f.write(f'    </vehicle>\n')
            
        f.write('</routes>\n')

    # Write sumocfg
    with open(SUMOCFGOUT, "w") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write('<configuration>\n')
        f.write('    <input>\n')
        f.write('        <net-file value="mangaluru_ai.net.xml.gz"/>\n')
        f.write('        <route-files value="ambulance_test.rou.xml"/>\n')
        poly_file = "D:/AIML/Projects/AI-Predictive-Traffic/simulation/mangaluru/osm.poly.xml.gz"
        if os.path.exists(poly_file):
            f.write('        <additional-files value="osm.poly.xml.gz"/>\n')
        f.write('    </input>\n')
        f.write('    <time>\n')
        f.write('        <begin value="0"/>\n')
        f.write('        <end value="3600"/>\n')
        f.write('    </time>\n')
        f.write('</configuration>\n')

    print("\nFiles created:")
    print(ROUTEOUT)
    print(SUMOCFGOUT)
    print("\n============================================================")

if __name__ == "__main__":
    create_scenario()
