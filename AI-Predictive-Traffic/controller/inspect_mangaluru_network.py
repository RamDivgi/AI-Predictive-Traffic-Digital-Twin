import gzip
import xml.etree.ElementTree as ET
import sumolib
import math

NETWORK_PATH = "D:/AIML/Projects/Major/AI-Predictive-Traffic/simulation/mangaluru/osm.net.xml.gz"
OSM_PATH = "C:/Users/ram/Sumo/2026-08-20-22-55-58/osm_bbox.osm.xml.gz"

def distance(x1, y1, x2, y2):
    return math.hypot(x2 - x1, y2 - y1)

def inspect_network():
    print("============================================================")
    print("MANGALURU SUMO NETWORK INSPECTION")
    print("============================================================")
    
    # 1. NETWORK INFORMATION
    try:
        net = sumolib.net.readNet(NETWORK_PATH)
    except Exception as e:
        print(f"Error reading network: {e}")
        return

    edges = net.getEdges()
    drivable_edges = [e for e in edges if e.allows("passenger")]
    nodes = net.getNodes()
    tl_nodes = [n for n in nodes if n.getType() == "traffic_light"]
    
    # Signals/Connections
    connections = 0
    for e in edges:
        for conn in e.getOutgoing():
            connections += 1
            
    bbox = net.getBBoxXY()

    print("\nNETWORK")
    print(f"Edges: {len(edges)}")
    print(f"Drivable edges: {len(drivable_edges)}")
    print(f"Junctions: {len(nodes)}")
    print(f"Traffic lights: {len(tl_nodes)}")
    print(f"Total connections: {connections}")
    print(f"Boundary (X,Y): {bbox}")
    
    # 2. TRAFFIC LIGHTS
    print("\n------------------------------------------------------------")
    print("TRAFFIC LIGHTS (First 30)")
    print("------------------------------------------------------------")
    print(f"{'Junction ID':<25} | {'X/Y':<20} | {'Incoming':<10} | {'Outgoing':<10}")
    print("-" * 75)
    for i, tl in enumerate(tl_nodes[:30]):
        x, y = tl.getCoord()
        inc = len(tl.getIncoming())
        outg = len(tl.getOutgoing())
        print(f"{tl.getID():<25} | {f'{x:.1f},{y:.1f}':<20} | {inc:<10} | {outg:<10}")

    # 3. HOSPITALS / MEDICAL FACILITIES
    print("\n------------------------------------------------------------")
    print("HOSPITALS / MEDICAL FACILITIES")
    print("------------------------------------------------------------")
    
    hospitals = []
    needed_nodes = set()
    hospital_ways = []
    
    # Pass 1: Find hospitals (nodes and ways)
    with gzip.open(OSM_PATH, 'rt', encoding='utf-8') as f:
        context = ET.iterparse(f, events=('end',))
        for event, elem in context:
            if elem.tag in ('node', 'way', 'relation'):
                if elem.tag in ('node', 'way'):
                    tags = {child.get('k'): child.get('v') for child in elem if child.tag == 'tag' and child.get('k')}
                    
                    is_medical = False
                    med_type = ""
                    if tags.get('amenity') == 'hospital':
                        is_medical = True
                        med_type = "amenity=hospital"
                    elif tags.get('healthcare') in ['hospital', 'clinic', 'medical_centre']:
                        is_medical = True
                        med_type = f"healthcare={tags.get('healthcare')}"
                        
                    if is_medical:
                        name = tags.get('name', 'Unknown Medical Facility')
                        osm_id = elem.attrib.get('id', 'N/A')
                        
                        if elem.tag == 'node':
                            lat = float(elem.attrib['lat'])
                            lon = float(elem.attrib['lon'])
                            hospitals.append({'name': name, 'id': osm_id, 'lat': lat, 'lon': lon, 'type': med_type})
                        elif elem.tag == 'way':
                            # Get the first node for approximate location
                            nd = elem.find('nd')
                            if nd is not None:
                                ref = nd.attrib.get('ref')
                                if ref:
                                    needed_nodes.add(ref)
                                    hospital_ways.append({'name': name, 'id': osm_id, 'ref': ref, 'type': med_type})
                
                # free memory (clears children like tags too)
                elem.clear()
            
    # Pass 2: Resolve way coordinates
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
                                    hospitals.append({'name': hw['name'], 'id': hw['id'], 'lat': lat, 'lon': lon, 'type': hw['type']})
                            needed_nodes.remove(node_id)
                            if not needed_nodes:
                                break
                    elem.clear()

    print(f"{'Name':<40} | {'OSM ID':<15} | {'Lat, Lon':<25} | {'Type':<25}")
    print("-" * 110)
    for h in hospitals:
        coord_str = f"{h.get('lat', 0.0):.5f}, {h.get('lon', 0.0):.5f}"
        print(f"{h['name'][:38]:<40} | {h['id']:<15} | {coord_str:<25} | {h['type']:<25}")

    # 4. MAP HOSPITALS TO SUMO
    print("\n------------------------------------------------------------")
    print("HOSPITAL -> SUMO EDGE MAPPING")
    print("------------------------------------------------------------")
    
    hospital_edges = []
    print(f"{'Name':<40} | {'Nearest SUMO Edge':<20} | {'Distance (m)':<15}")
    print("-" * 80)
    for h in hospitals:
        lat = h.get('lat')
        lon = h.get('lon')
        if lat and lon:
            try:
                x, y = net.convertLonLat2XY(lon, lat)
                nearest_edges = net.getNeighboringEdges(x, y, r=500.0)
                
                # Filter drivable
                suitable = [(edge, dist) for edge, dist in nearest_edges if edge.allows("passenger")]
                
                if suitable:
                    # sort by distance
                    suitable.sort(key=lambda item: item[1])
                    best_edge, dist = suitable[0]
                    hospital_edges.append({'hospital': h, 'edge': best_edge, 'dist': dist})
                    print(f"{h['name'][:38]:<40} | {best_edge.getID():<20} | {dist:.1f}")
                else:
                    print(f"{h['name'][:38]:<40} | {'None found':<20} | {'N/A':<15}")
            except Exception as e:
                print(f"Error mapping {h['name']}: {e}")

    # 5. SUITABLE AMBULANCE START POINTS
    print("\n------------------------------------------------------------")
    print("AMBULANCE START CANDIDATES")
    print("------------------------------------------------------------")
    
    candidates = []
    for edge in drivable_edges:
        if edge.getFunction() == "internal":
            continue
            
        edge_len = edge.getLength()
        if edge_len < 50.0:
            continue
            
        # Ensure it's not immediately next to a hospital
        is_near_hospital = False
        edge_x, edge_y = edge.getFromNode().getCoord()
        for he in hospital_edges:
            hx, hy = he['edge'].getFromNode().getCoord()
            if distance(edge_x, edge_y, hx, hy) < 500:
                is_near_hospital = True
                break
                
        if not is_near_hospital:
            candidates.append(edge)
            
        if len(candidates) >= 10:
            break
            
    print(f"{'Edge ID':<20} | {'From':<15} | {'To':<15} | {'Length (m)':<12} | {'Speed':<8} | {'Coordinates'}")
    print("-" * 100)
    for c in candidates:
        coord = c.getFromNode().getCoord()
        print(f"{c.getID():<20} | {c.getFromNode().getID():<15} | {c.getToNode().getID():<15} | {c.getLength():<12.1f} | {c.getSpeed():<8.1f} | {f'{coord[0]:.1f},{coord[1]:.1f}'}")

    # 6 & 7. ROUTE CONNECTIVITY & TRAFFIC-LIGHT ROUTE POTENTIAL
    print("\n------------------------------------------------------------")
    print("CONNECTIVITY TEST")
    print("------------------------------------------------------------")
    
    if candidates and hospital_edges:
        start_edge = candidates[0]
        hospital_info = hospital_edges[0]
        dest_edge = hospital_info['edge']
        
        print(f"Start: {start_edge.getID()} (Near {start_edge.getFromNode().getCoord()})")
        print(f"Destination: {dest_edge.getID()} ({hospital_info['hospital']['name']})")
        
        try:
            route = net.getShortestPath(start_edge, dest_edge, vClass="passenger")
            if route and route[0]:
                edges_in_route = route[0]
                total_length = sum(e.getLength() for e in edges_in_route)
                
                # count signalized junctions
                signals = 0
                for e in edges_in_route:
                    to_node = e.getToNode()
                    if to_node.getType() == "traffic_light":
                        signals += 1
                        
                print(f"Route exists: YES")
                print(f"Route length: {total_length:.1f} meters")
                print(f"Edges: {len(edges_in_route)}")
                print(f"Signalized junctions: {signals}")
            else:
                print(f"Route exists: NO")
                print("Route length: N/A")
                print("Signalized junctions: N/A")
        except Exception as e:
            print(f"Error calculating route: {e}")
    else:
        print("Not enough candidates or hospitals to test connectivity.")

    print("\n============================================================")
    print("NETWORK INSPECTION COMPLETED")
    print("============================================================")

if __name__ == "__main__":
    inspect_network()
