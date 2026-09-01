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

print(f"BBox: {bbox}")
print(f"Total edges: {len(edges)}")

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

print(f"Grid cells with edges: {len(grid)}")
for k, v in grid.items():
    print(f"Cell {k}: {len(v)} edges")
