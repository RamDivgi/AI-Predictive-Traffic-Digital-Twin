import os
import sumolib

net_file = "D:/AIML/Projects/Major/AI-Predictive-Traffic/simulation/mangaluru/mangaluru_ai.net.xml.gz"
net = sumolib.net.readNet(net_file)

kan_edge_in = net.getEdge("1080446743#0")
print(f"Incoming edges to {kan_edge_in.getID()}:")
for inc, _ in kan_edge_in.getIncoming().items():
    print(f"  {inc.getID()} (allows passenger: {inc.allows('passenger')})")
    for inc2, _ in inc.getIncoming().items():
        print(f"    {inc2.getID()} (allows passenger: {inc2.allows('passenger')})")

