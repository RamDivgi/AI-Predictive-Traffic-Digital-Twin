import sumolib
import sys

net_file = "d:/AIML/Projects/Major/AI-Predictive-Traffic/simulation/mangaluru/presentation_selection1.net.xml"
try:
    net = sumolib.net.readNet(net_file)
    print(f"Loaded {net_file}")
    
    edges = net.getEdges()
    junctions = net.getNodes()
    tls = net.getTrafficLights()
    
    print(f"Edges: {len(edges)}")
    print(f"Junctions: {len(junctions)}")
    print(f"TLS: {len(tls)}")
    
    # Search for anything related to omega or karavali or kmc
    print("\n--- POIs/Edges matching 'omega', 'karavali', 'kmc' ---")
    for edge in edges:
        id = edge.getID().lower()
        if 'omega' in id or 'karavali' in id or 'kmc' in id:
            print(f"Edge: {edge.getID()}")
            
    for j in junctions:
        id = j.getID().lower()
        if 'omega' in id or 'karavali' in id or 'kmc' in id:
            print(f"Junc: {j.getID()}")
            
    # Also print all TLS IDs to see what we have
    print("\n--- TLS IDs ---")
    for t in tls:
        print(f"TLS: {t.getID()}")
        
except Exception as e:
    print(f"Error: {e}")
