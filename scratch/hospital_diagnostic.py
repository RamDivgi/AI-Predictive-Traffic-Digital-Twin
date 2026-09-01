import os
import sys

# Setup environment to import correctly
os.chdir(r'd:\AIML\Projects\Major\AI-Predictive-Traffic')
sys.path.append('controller')

import config
from hospital_manager import HospitalManager
from astar_router import AStarRouter
import sumolib

def run_diagnostic():
    print(f"Loading NET_FILE: {config.NET_FILE}")
    print(f"Loading HOSPITALS_FILE: {config.HOSPITALS_FILE}")
    
    # Initialize HospitalManager
    # Note: sumolib needs file URI for absolute paths in some windows Python versions, but HospitalManager
    # uses readNet(str). If it fails, we handle it.
    try:
        net_uri = f"file:///{str(config.NET_FILE).replace(os.sep, '/')}"
        hm = HospitalManager(net_uri, str(config.HOSPITALS_FILE))
    except Exception as e:
        print(f"Failed to load HospitalManager with URI: {e}")
        # Try raw path
        hm = HospitalManager(str(config.NET_FILE), str(config.HOSPITALS_FILE))

    hospitals = hm.get_all_hospitals()
    print(f"Loaded {len(hospitals)} hospitals.")
    
    # AStarRouter expects no args for net
    router = AStarRouter()
    
    # We need a starting edge for the ambulance.
    # Where does the ambulance typically start?
    # Usually it's defined in the rou.xml file or config.
    # Let's find a valid passenger edge to start from, e.g. "1538932912#0" or similar
    # We can just pick the first passenger edge in the network.
    # We know the ambulance starts at 1096889856 based on rou.xml files
    start_edge = "1096889856"
    
    if start_edge not in [e.getID() for e in hm.net.getEdges()]:
        print(f"Warning: Edge {start_edge} not found. Picking first passenger edge.")
        start_edge = None
        for edge in hm.net.getEdges():
            if edge.allows("passenger"):
                start_edge = edge.getID()
                break
            
    if not start_edge:
        print("No valid passenger edges found in network to start from!")
        return

    print(f"\nUsing simulated ambulance spawn edge: {start_edge}")
    print("-" * 80)
    
    final_edges_seen = {}
    
    for hosp in hospitals:
        print(f"Hospital ID: {hosp.id}")
        print(f"Hospital Name: {hosp.name}")
        print(f"Hospital Coordinates: ({hosp.x}, {hosp.y})")
        
        dest_edge_id = hosp.nearest_edge
        print(f"Nearest SUMO edge: {dest_edge_id}")
        
        if not dest_edge_id:
            print("  --> FAIL: No nearest edge found.")
            print("-" * 80)
            continue
            
        edge_obj = hm.net.getEdge(dest_edge_id)
        # Getting edge coordinates (approximate middle)
        shape = edge_obj.getShape()
        mid_x = sum(p[0] for p in shape) / len(shape)
        mid_y = sum(p[1] for p in shape) / len(shape)
        print(f"Nearest edge approx coordinates: ({mid_x:.2f}, {mid_y:.2f})")
        
        route = router.find_route(start_edge, dest_edge_id, 0.0, 15.0)
        
        if not route or not route.edge_ids:
            print(f"  --> FAIL: No route found from {start_edge} to {dest_edge_id}")
        else:
            final_route_edge = route.edge_ids[-1]
            print(f"Computed route length: {len(route.edge_ids)} edges")
            print(f"Final route edge: {final_route_edge}")
            
            # Find the junction
            final_edge_obj = hm.net.getEdge(final_route_edge)
            to_node = final_edge_obj.getToNode().getID()
            print(f"Final route junction: {to_node}")
            
            if final_route_edge == dest_edge_id:
                print("  --> PASS: Route reaches the selected destination edge.")
            else:
                print("  --> FAIL: Route final edge does not match destination edge!")
                
            final_edges_seen[hosp.id] = final_route_edge
            
        print("-" * 80)
        
    # Check if all final edges are the same
    unique_final_edges = set(final_edges_seen.values())
    print("\nSummary of Final Edges:")
    for hid, fedg in final_edges_seen.items():
        print(f"  {hid} -> {fedg}")
        
    print(f"\nTotal unique final edges: {len(unique_final_edges)} out of {len(final_edges_seen)} valid destinations.")

if __name__ == '__main__':
    run_diagnostic()
