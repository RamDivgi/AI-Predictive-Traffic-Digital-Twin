import os
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.join(os.environ.get("SUMO_HOME", r"C:\Program Files (x86)\Eclipse\Sumo"), "tools"))
import sumolib

def validate():
    print("Starting validation...")
    net_file = r"d:\AIML\Projects\Major\AI-Predictive-Traffic\simulation\mangaluru\presentation_selection2.net.xml"
    route_file = r"d:\AIML\Projects\Major\AI-Predictive-Traffic\simulation\mangaluru\presentation_demo.rou.xml"
    
    try:
        net = sumolib.net.readNet(net_file)
        print(f"Loaded network with {len(net.getEdges())} edges.")
    except Exception as e:
        print(f"Error loading network: {e}")
        return False
        
    try:
        tree = ET.parse(route_file)
        root = tree.getroot()
    except Exception as e:
        print(f"Error parsing route file: {e}")
        return False

    vtypes = {vt.get('id') for vt in root.findall('vType')}
    print(f"Found vTypes: {vtypes}")
    if 'ambulance' not in vtypes:
        print("Error: 'ambulance' vType missing!")
        return False
        
    routes = {rt.get('id'): rt.get('edges').split() for rt in root.findall('route')}
    print(f"Found {len(routes)} standalone routes.")
    
    vehicles = root.findall('vehicle')
    print(f"Found {len(vehicles)} vehicles.")
    
    valid = True
    ambulance_found = False
    
    for v in vehicles:
        vid = v.get('id')
        vtype = v.get('type')
        if vtype not in vtypes:
            print(f"Error: Vehicle {vid} uses unknown type {vtype}")
            valid = False
            
        if vid == "ambulance":
            ambulance_found = True
            
        edges = []
        r_ref = v.get('route')
        r_elem = v.find('route')
        
        if r_ref:
            if r_ref not in routes:
                print(f"Error: Vehicle {vid} references unknown route {r_ref}")
                valid = False
                continue
            edges = routes[r_ref]
        elif r_elem is not None:
            edges = r_elem.get('edges').split()
        else:
            print(f"Error: Vehicle {vid} has no route!")
            valid = False
            continue
            
        for edge_id in edges:
            if not net.hasEdge(edge_id):
                print(f"Error: Vehicle {vid} references unknown edge {edge_id}")
                valid = False
                
    if not ambulance_found:
        print("Error: No vehicle with id 'ambulance' found!")
        valid = False
        
    if valid:
        print("Validation SUCCESS. All routes and references are valid.")
    else:
        print("Validation FAILED.")

if __name__ == "__main__":
    validate()
