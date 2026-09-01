import sumolib
import sys

MANGALURU_NET = "d:/AIML/Projects/Major/AI-Predictive-Traffic/simulation/mangaluru/mangaluru_ai.net.xml.gz"

net = sumolib.net.readNet(MANGALURU_NET)

start_edge_id = "1096889856"
dest_edge_id = "-26299202#3" # Highland Hospital nearest edge
kankanady_edge_id = "1080446743#0"

start_edge = net.getEdge(start_edge_id)
dest_edge = net.getEdge(dest_edge_id)
kankanady_edge = net.getEdge(kankanady_edge_id)

route1 = net.getShortestPath(start_edge, kankanady_edge, vClass="passenger")
route2 = net.getShortestPath(kankanady_edge, dest_edge, vClass="passenger")

if not route1 or not route2:
    print("Could not find continuous route.")
    sys.exit(1)

route1_edges = [e.getID() for e in route1[0]]
route2_edges = [e.getID() for e in route2[0]]

# remove duplicate Kankanady edge at the boundary
final_route = route1_edges + route2_edges[1:]

print("Final Route Edges:")
print(" ".join(final_route))
print(f"Total Edges: {len(final_route)}")

import traci
# Calculate total length by just checking edges (approximate)
total_length = sum([net.getEdge(e).getLength() for e in final_route])
print(f"Total Length: {total_length:.2f} m")

hx, hy = 1687.4691396001144, 1134.9806500039995
dest_x, dest_y = dest_edge.getToNode().getCoord()
import math
dist = math.hypot(dest_x - hx, dest_y - hy)
print(f"Distance from end to Highland Hospital POI: {dist:.2f} m")
