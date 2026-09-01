import sys
import os
import random
import sumolib

PROJECT_ROOT = "D:\\AIML\\Projects\\Major\\AI-Predictive-Traffic"
sys.path.insert(0, PROJECT_ROOT)
MANGALURU_NET = os.path.join(PROJECT_ROOT, "simulation", "mangaluru", "presentation_selection2.net.xml")

net = sumolib.net.readNet(MANGALURU_NET)
edges = [e for e in net.getEdges() if e.getFunction() == '' and e.allows('passenger')]

bbox = net.getBBoxXY()
min_x, min_y = bbox[0]
max_x, max_y = bbox[1]

grid = {}
GRID_W = 4
GRID_H = 4
dx = (max_x - min_x) / GRID_W
dy = (max_y - min_y) / GRID_H

for e in edges:
    if e.getID() == '1096889856': 
        continue
        
    shape = e.getShape()
    if not shape: continue
    cx = sum(p[0] for p in shape) / len(shape)
    cy = sum(p[1] for p in shape) / len(shape)
    
    col = min(int((cx - min_x) / dx), GRID_W - 1)
    row = min(int((cy - min_y) / dy), GRID_H - 1)
    
    if (col, row) not in grid:
        grid[(col, row)] = []
    grid[(col, row)].append(e)

non_empty_cells = list(grid.keys())
vehicles_to_add = []

v_id = 0
for _ in range(3): # 3 vehicles per valid grid cell (~45 vehicles total)
    for cell in non_empty_cells:
        orig_edge = random.choice(grid[cell])
        
        dest_candidates = [c for c in non_empty_cells if c != cell]
        if not dest_candidates: dest_candidates = non_empty_cells
        dest_cell = random.choice(dest_candidates)
        
        # Try to find a routed path
        for _retry in range(10):
            dest_edge = random.choice(grid[dest_cell])
            path, cost = net.getShortestPath(orig_edge, dest_edge)
            if path is not None and len(path) > 1:
                depart_time = round(random.uniform(0.0, 60.0), 1)
                vehicles_to_add.append({
                    'orig': orig_edge.getID(),
                    'dest': dest_edge.getID(),
                    'path_len': len(path),
                    'orig_cell': cell,
                    'dest_cell': dest_cell
                })
                v_id += 1
                break
                
print(f"Generated {len(vehicles_to_add)} vehicles")
origins = [v['orig'] for v in vehicles_to_add]
orig_cells = [v['orig_cell'] for v in vehicles_to_add]

from collections import Counter
print(f"Top 5 origins: {Counter(origins).most_common(5)}")
print(f"Origin cell distribution: {Counter(orig_cells).most_common(5)}")

amb_edge = net.getEdge('1096889856')
amb_shape = amb_edge.getShape()
amb_cx = sum(p[0] for p in amb_shape) / len(amb_shape)
amb_cy = sum(p[1] for p in amb_shape) / len(amb_shape)
print(f"Ambulance is at {amb_cx}, {amb_cy}")
