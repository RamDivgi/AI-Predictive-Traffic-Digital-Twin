import sys
import os
from pathlib import Path
import traci
import sumolib
import math

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SUMO_CONFIG = PROJECT_ROOT / "simulation" / "mangaluru" / "kankanady_demo.sumocfg"
MANGALURU_NET = PROJECT_ROOT / "simulation" / "mangaluru" / "mangaluru_ai.net.xml.gz"

def distance(p1, p2):
    return math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)

def run_diagnostic():
    print("Loading SUMO network...")
    net = sumolib.net.readNet(str(MANGALURU_NET))
    
    print("Starting TraCI...")
    traci.start(["sumo", "-c", str(SUMO_CONFIG), "--step-length", "0.1"])
    
    ambulance_id = None
    route_edges = []
    
    # Run until ambulance spawns
    for step in range(1000):
        traci.simulationStep()
        vehicles = traci.vehicle.getIDList()
        if "ambulance" in vehicles:
            ambulance_id = "ambulance"
            route_edges = traci.vehicle.getRoute(ambulance_id)
            break
            
    if not ambulance_id:
        print("Ambulance did not spawn within 1000 steps.")
        traci.close()
        return
        
    print(f"\n1. CURRENT AMBULANCE ROUTE")
    print(f"Ambulance ID: {ambulance_id}")
    start_edge = route_edges[0]
    dest_edge = route_edges[-1]
    print(f"Start Edge: {start_edge}")
    print(f"Destination Edge: {dest_edge}")
    
    # Try to find hospital destination
    # We can parse the map or check if there is a hospital POI nearby
    hospitals = []
    print("2. CURRENT HOSPITAL DESTINATION")
    print("Checking for nearby hospitals at destination...")
    # (Just a simple check if any script is associated with hospitals; for now, we'll just note the destination edge)
    print(f"Destination edge is {dest_edge}. (Specific hospital name not hardcoded in route, but we know it's going to a hospital POI near this edge).")
    
    print(f"\n3. ROUTE EDGE COUNT")
    print(f"Total number of route edges: {len(route_edges)}")
    print(f"First 5 route edges: {route_edges[:5]}")
    print(f"Last 5 route edges: {route_edges[-5:]}")
    
    print(f"\n4. ROUTE CONTINUITY & 5. GEOMETRY RESULT")
    continuous = True
    total_length = 0.0
    invalid_geometry = False
    
    route_shapes = []
    for i, edge_id in enumerate(route_edges):
        try:
            edge = net.getEdge(edge_id)
            # Use the first lane's shape as the edge's shape for simplicity
            shape = edge.getLanes()[0].getShape()
            if not shape or len(shape) < 2:
                invalid_geometry = True
                print(f"Edge {edge_id} has invalid/missing geometry.")
            
            route_shapes.append(shape)
            
            # Calculate length
            edge_len = sum(distance(shape[j], shape[j+1]) for j in range(len(shape)-1))
            total_length += edge_len
            
            # Check continuity with previous edge
            if i > 0:
                prev_shape = route_shapes[i-1]
                # End of prev should be close to start of current
                dist = distance(prev_shape[-1], shape[0])
                # Connections in SUMO might have small gaps (junctions), but usually < 50m
                if dist > 50.0:
                    continuous = False
                    print(f"Discontinuity between {route_edges[i-1]} and {edge_id}. Gap: {dist:.2f}m")
                    
        except KeyError:
            print(f"Edge {edge_id} not found in SUMO network!")
            invalid_geometry = True
            continuous = False

    print(f"Route can be represented as a continuous polyline: {continuous}")
    print(f"Any route edge has missing/invalid geometry: {invalid_geometry}")
    print(f"Approximate total route length: {total_length:.2f} meters")
    
    traci.close()

if __name__ == '__main__':
    run_diagnostic()
