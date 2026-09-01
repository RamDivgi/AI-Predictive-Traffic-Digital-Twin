import os
import sumolib

net_file = "D:/AIML/Projects/Major/AI-Predictive-Traffic/simulation/mangaluru/mangaluru_ai.net.xml.gz"
net = sumolib.net.readNet(net_file)

tls_id = "joinedS_11152279217_cluster_11151324665_3610155471"
tls = next((t for t in net.getTrafficLights() if t.getID() == tls_id), None)

if tls:
    print(f"Found TLS: {tls.getID()}")
    conns = tls.getConnections()
    programs = tls.getPrograms()
    
    # Let's find which connection corresponds to 1080446743#0
    print("\nConnections:")
    target_indices = []
    for conn in conns:
        inc_lane = conn[0]
        out_lane = conn[1]
        link_idx = conn[2]
        inc_edge = inc_lane.getEdge().getID()
        out_edge = out_lane.getEdge().getID()
        
        print(f"Link {link_idx}: {inc_edge} -> {out_edge}")
        if inc_edge == "1080446743#0" and out_edge == "355391676#0":
            target_indices.append(link_idx)
            
    print(f"\nTarget Link Indices for 1080446743#0 -> 355391676#0: {target_indices}")
    
    for prog_id, prog in programs.items():
        print(f"\nProgram: {prog_id}")
        for i, phase in enumerate(prog.getPhases()):
            print(f"Phase {i} (duration {phase.duration}): {phase.state}")
else:
    print("TLS not found")
