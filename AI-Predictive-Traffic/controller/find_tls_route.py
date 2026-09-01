import sumolib
import random

net_file = "d:/AIML/Projects/Major/AI-Predictive-Traffic/simulation/mangaluru/presentation_selection1.net.xml"
net = sumolib.net.readNet(net_file)

tls = net.getTrafficLights()
print(f"Total TLS in network: {len(tls)}")

for t in tls:
    # Get nodes for this TLS
    edges = t.getEdges()
    if len(edges) > 0:
        print(f"TLS {t.getID()} controls edges: {[e.getID() for e in edges]}")
        # Find incoming edges to this TLS
        
        # Let's just find a route that goes from some node to another node passing through this TLS
        for e in edges:
            in_edge = e
            # Just want a straight forward path through it
            print(f"  Possible TLS edge: {e.getID()}")
