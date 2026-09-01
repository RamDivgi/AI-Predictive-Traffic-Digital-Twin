import os
import sumolib

net_file = "D:/AIML/Projects/Major/AI-Predictive-Traffic/simulation/mangaluru/mangaluru_ai.net.xml.gz"
net = sumolib.net.readNet(net_file)

try:
    edge = net.getEdge("1080446743#0")
    node = edge.getToNode()
    print(f"Edge: {edge.getID()}")
    print(f"To Node: {node.getID()}")
    print(f"Node Type: {node.getType()}")
    tls = node.getTLS()
    if tls:
        print(f"TLS ID: {tls.getID()}")
    else:
        print("No TLS")
except Exception as e:
    print(e)
