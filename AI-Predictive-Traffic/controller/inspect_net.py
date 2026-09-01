import os
import sumolib

net_file = os.path.join(os.path.dirname(__file__), '..', 'simulation', 'mangaluru', 'mangaluru_ai.net.xml.gz')

if not os.path.exists(net_file):
    print(f"Network file not found: {net_file}")
    exit(1)

print(f"Parsing network: {net_file}")
net = sumolib.net.readNet(net_file)

tls_list = net.getTrafficLights()
print(f"Found {len(tls_list)} traffic light programs.")

tls_dict = {}

for tls in tls_list:
    tls_id = tls.getID()
    if tls_id not in tls_dict:
        tls_dict[tls_id] = tls

print("\n--- TLS Information ---")
for tls_id, tls in tls_dict.items():
    # A TLS controls one or more junctions
    # In sumolib, a TLS object doesn't directly have a getJunction() method in older versions.
    # We can get the controlled edges/lanes and find the nodes.
    # Usually the TLS ID is often the junction ID in SUMO, unless it's a joined TLS.
    connections = tls.getConnections()
    
    nodes = set()
    incoming_edges = set()
    outgoing_edges = set()
    
    for conn in connections:
        # conn is a list containing [incoming_lane, outgoing_lane, link_index]
        inc_lane = conn[0]
        out_lane = conn[1]
        
        inc_edge = inc_lane.getEdge()
        out_edge = out_lane.getEdge()
        
        incoming_edges.add(inc_edge.getID())
        outgoing_edges.add(out_edge.getID())
        
        nodes.add(inc_edge.getToNode())
    
    if len(nodes) == 0:
        continue
        
    print(f"\nTLS ID: {tls_id}")
    for node in nodes:
        print(f"  Junction ID: {node.getID()}")
        print(f"  X/Y: {node.getCoord()}")
    
    print(f"  Incoming edges: {', '.join(sorted(list(incoming_edges)))}")
    print(f"  Outgoing edges: {', '.join(sorted(list(outgoing_edges)))}")
