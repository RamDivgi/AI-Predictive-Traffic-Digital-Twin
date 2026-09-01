import os
import sumolib

net_file = "D:/AIML/Projects/Major/AI-Predictive-Traffic/simulation/mangaluru/mangaluru_ai.net.xml.gz"
net = sumolib.net.readNet(net_file)

tls_list = net.getTrafficLights()
tls_ids = [tls.getID() for tls in tls_list]
print(f"cluster_11151324665_3610155471 in tls_ids: {'cluster_11151324665_3610155471' in tls_ids}")

try:
    node = net.getNode("cluster_11151324665_3610155471")
    print(f"Node Type: {node.getType()}")
    # Let's check TLS connections
    tls_found = False
    for tls in tls_list:
        conns = tls.getConnections()
        for conn in conns:
            inc_edge = conn[0].getEdge()
            if inc_edge.getToNode().getID() == node.getID():
                print(f"Node is controlled by TLS: {tls.getID()}")
                tls_found = True
                break
        if tls_found:
            break
except Exception as e:
    print(e)
