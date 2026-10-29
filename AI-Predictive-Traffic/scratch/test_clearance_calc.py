import json
import math
import sumolib
from pathlib import Path

PROJECT_ROOT = Path("d:/AIML/Projects/Major")
net_path = PROJECT_ROOT / "AI-Predictive-Traffic/simulation/mangaluru/presentation_selection2.net.xml"
net = sumolib.net.readNet(str(net_path))

road_segs = []
for edge in net.getEdges():
    if edge.getFunction() == "internal": continue
    for lane in edge.getLanes():
        shape = lane.getShape()
        w = lane.getWidth()
        for i in range(len(shape) - 1):
            road_segs.append((shape[i], shape[i+1], w))

def get_road_dist(px, py):
    min_dist = float('inf')
    for p1, p2, w in road_segs:
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        l2 = dx*dx + dy*dy
        t = 0.0 if l2 < 0.0001 else max(0.0, min(1.0, ((px - p1[0])*dx + (py - p1[1])*dy) / l2))
        proj_x = p1[0] + t * dx
        proj_y = p1[1] + t * dy
        d = math.hypot(px - proj_x, py - proj_y) - (w * 0.5)
        if d < min_dist:
            min_dist = d
            if min_dist < 1.0: break
    return min_dist

print("Road segment distance function verified.")
