import sys
import os
import random
import math
import sumolib
import xml.etree.ElementTree as ET

PROJECT_ROOT = "D:\\AIML\\Projects\\Major\\AI-Predictive-Traffic"
sys.path.insert(0, PROJECT_ROOT)
MANGALURU_NET = os.path.join(PROJECT_ROOT, "simulation", "mangaluru", "presentation_selection2.net.xml")

net = sumolib.net.readNet(MANGALURU_NET)
edges = [e for e in net.getEdges() if e.getFunction() == '' and e.allows('passenger')]

# Get ambulance location
amb_edge = net.getEdge('1096889856')
amb_shape = amb_edge.getShape()
amb_cx = sum(p[0] for p in amb_shape) / len(amb_shape)
amb_cy = sum(p[1] for p in amb_shape) / len(amb_shape)

vehicles_to_add = []

def get_edge_center(edge):
    shape = edge.getShape()
    if not shape: return 0, 0
    return sum(p[0] for p in shape) / len(shape), sum(p[1] for p in shape) / len(shape)

# Let's generate ~200 vehicles
target_vehicles = 200

# Try to randomly pick valid trips
valid_trips = []
v_id = 0

origins_used = set()
dests_used = set()
routes_used = set()
vehicles_near_amb = 0

regions_origins = set()
regions_dests = set()

# Define grid for regions (just for stats)
bbox = net.getBBoxXY()
min_x, min_y = bbox[0]
max_x, max_y = bbox[1]
dx = (max_x - min_x) / 4
dy = (max_y - min_y) / 4

attempts = 0
while len(valid_trips) < target_vehicles and attempts < 2000:
    attempts += 1
    orig_edge = random.choice(edges)
    dest_edge = random.choice(edges)
    
    if orig_edge == dest_edge:
        continue
        
    orig_cx, orig_cy = get_edge_center(orig_edge)
    dest_cx, dest_cy = get_edge_center(dest_edge)
    
    # Distance to ambulance
    dist_to_amb = math.hypot(orig_cx - amb_cx, orig_cy - amb_cy)
    
    # Exclusion zone: fewer vehicles near ambulance start
    if dist_to_amb < 250:
        if random.random() > 0.1: # 90% chance to reject
            continue
            
    # Try to find path
    path, cost = net.getShortestPath(orig_edge, dest_edge)
    if path is not None and len(path) > 2:
        # Route hash to check uniqueness
        route_str = " ".join([e.getID() for e in path])
        
        # We want variety in routes
        if route_str in routes_used and random.random() > 0.2:
            continue
            
        depart_time = round(random.uniform(0.0, 60.0), 1)
        
        valid_trips.append({
            'id': f'rand_car_{v_id}',
            'depart': depart_time,
            'from': orig_edge.getID(),
            'to': dest_edge.getID(),
            'route': route_str
        })
        
        origins_used.add(orig_edge.getID())
        dests_used.add(dest_edge.getID())
        routes_used.add(route_str)
        if dist_to_amb < 250:
            vehicles_near_amb += 1
            
        col = int((orig_cx - min_x) / dx)
        row = int((orig_cy - min_y) / dy)
        regions_origins.add((col, row))
        
        d_col = int((dest_cx - min_x) / dx)
        d_row = int((dest_cy - min_y) / dy)
        regions_dests.add((d_col, d_row))
        
        v_id += 1

print(f"Total background vehicles: {len(valid_trips)}")
print(f"Unique origin edges: {len(origins_used)}")
print(f"Unique destination edges: {len(dests_used)}")
print(f"Unique routes: {len(routes_used)}")
print(f"Spatial regions used (origins): {len(regions_origins)}/16")
print(f"Spatial regions used (dests): {len(regions_dests)}/16")
print(f"Vehicles near ambulance spawn: {vehicles_near_amb}")

depart_times = [v['depart'] for v in valid_trips]
hist = [0, 0, 0, 0, 0, 0]
for d in depart_times:
    idx = min(int(d / 10), 5)
    hist[idx] += 1
print(f"Departure-time distribution (10s intervals): {hist}")

