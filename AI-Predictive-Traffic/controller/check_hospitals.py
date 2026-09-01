import sys
from pathlib import Path
sys.path.insert(0, str(Path("d:/AIML/Projects/Major/AI-Predictive-Traffic/controller")))
import sumolib
import math

net_file = "d:/AIML/Projects/Major/AI-Predictive-Traffic/simulation/mangaluru/presentation_selection2.net.xml"
net = sumolib.net.readNet(net_file)

hospitals = [
    ("highland_hospital", 1687.46, 1134.98),
    ("kmc_hospital", 1017.28, 1723.68),
    ("city_hospital", 1527.72, 2595.90)
]

for name, x, y in hospitals:
    edges = net.getNeighboringEdges(x, y, 100) # search radius 100m
    if edges:
        edges.sort(key=lambda item: item[1]) # sort by distance
        nearest = edges[0][0]
        print(f"{name} is reachable! Nearest edge: {nearest.getID()} at dist {edges[0][1]:.2f}m")
    else:
        print(f"{name} is NOT reachable (no edges within 100m)")
