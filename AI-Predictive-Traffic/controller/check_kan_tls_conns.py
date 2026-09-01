import os
import sumolib

net_file = "D:/AIML/Projects/Major/AI-Predictive-Traffic/simulation/mangaluru/mangaluru_ai.net.xml.gz"
net = sumolib.net.readNet(net_file)

tls_id = "joinedS_11152279217_cluster_11151324665_3610155471"

try:
    tls = next((t for t in net.getTrafficLights() if t.getID() == tls_id), None)
    if tls:
        conns = tls.getConnections()
        inc_edges = set([c[0].getEdge().getID() for c in conns])
        out_edges = set([c[1].getEdge().getID() for c in conns])
        print(f"Incoming edges: {inc_edges}")
        print(f"Outgoing edges: {out_edges}")
    else:
        print("TLS not found")
except Exception as e:
    print(e)
