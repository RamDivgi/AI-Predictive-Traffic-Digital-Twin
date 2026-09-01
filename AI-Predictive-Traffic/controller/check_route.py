import os
import sumolib

net_file = "D:/AIML/Projects/Major/AI-Predictive-Traffic/simulation/mangaluru/mangaluru_ai.net.xml.gz"
net = sumolib.net.readNet(net_file)

start_edge_id = "26206100#7"
dest_edge_id = "26325820"

try:
    start_edge = net.getEdge(start_edge_id)
    dest_edge = net.getEdge(dest_edge_id)
    
    route = net.getShortestPath(start_edge, dest_edge, vClass="emergency")
    if route and route[0]:
        print(f"Valid route from {start_edge_id} to {dest_edge_id}")
        print(f"Edges: {[e.getID() for e in route[0]]}")
    else:
        print("No route found")
except Exception as e:
    print(f"Error: {e}")
