import os
import sumolib

net_file = "D:/AIML/Projects/Major/AI-Predictive-Traffic/simulation/mangaluru/mangaluru_ai.net.xml.gz"
net = sumolib.net.readNet(net_file)

tls_id = "joinedS_11152279217_cluster_11151324665_3610155471"
tls = next((t for t in net.getTrafficLights() if t.getID() == tls_id), None)

if tls:
    programs = tls.getPrograms()
    for prog_id, prog in programs.items():
        print(f"\nProgram: {prog_id}")
        phases = prog.getPhases()
        for i, phase in enumerate(phases):
            # phase is an object in sumolib.net.Phase
            print(f"Phase {i} (duration {phase.duration}): {phase.state}")
