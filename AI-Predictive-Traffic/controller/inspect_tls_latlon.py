import os
import sumolib

net_file = "D:/AIML/Projects/Major/AI-Predictive-Traffic/simulation/mangaluru/mangaluru_ai.net.xml.gz"
net = sumolib.net.readNet(net_file)

tls_nodes = [n for n in net.getNodes() if n.getType() == "traffic_light"]

print("--- TLS Nodes ---")
for n in tls_nodes:
    x, y = n.getCoord()
    lon, lat = net.convertXY2LonLat(x, y)
    print(f"Junction ID: {n.getID():>30} | XY: ({x:.2f}, {y:.2f}) | Lat/Lon: ({lat:.5f}, {lon:.5f})")
