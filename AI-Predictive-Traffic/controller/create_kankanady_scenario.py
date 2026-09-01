import os
import sumolib
import random

net_file = "D:/AIML/Projects/Major/AI-Predictive-Traffic/simulation/mangaluru/mangaluru_ai.net.xml.gz"
rou_file = "D:/AIML/Projects/Major/AI-Predictive-Traffic/simulation/mangaluru/kankanady_demo.rou.xml"
cfg_file = "D:/AIML/Projects/Major/AI-Predictive-Traffic/simulation/mangaluru/kankanady_demo.sumocfg"

net = sumolib.net.readNet(net_file)

# Find a route from an upstream edge to a hospital passing through Kankanady TLS
kan_edge_in = net.getEdge("1080446743#0")
kan_edge_out = net.getEdge("355391676#0")

# Walk backwards from 1042171954#2 to find a good starting edge about 1-2 km away
start_edge = net.getEdge("1042171954#2")
for _ in range(20):
    inc = start_edge.getIncoming()
    if not inc: break
    valid = [e for e, _ in inc.items() if e.allows("passenger")]
    if valid:
        start_edge = valid[0]
    else:
        break

dest_edge = kan_edge_out
for _ in range(15):
    out = dest_edge.getOutgoing()
    if not out: break
    valid = [e for e, _ in out.items() if e.allows("passenger")]
    if valid:
        dest_edge = valid[0]
    else:
        break

amb_route_1 = net.getShortestPath(start_edge, kan_edge_in, vClass="passenger")
amb_route_2 = net.getShortestPath(kan_edge_out, dest_edge, vClass="passenger")

amb_edges = [e.getID() for e in amb_route_1[0]] + [e.getID() for e in amb_route_2[0]]

# Generate background traffic
random.seed(42)
drivable_edges = [e for e in net.getEdges() if e.allows("passenger") and e.getFunction() != "internal"]

bg_vehicles = []

# 1. City-wide normal traffic
for i in range(250):
    src = random.choice(drivable_edges)
    dst = random.choice(drivable_edges)
    if src != dst:
        try:
            route = net.getShortestPath(src, dst, vClass="passenger")
            if route and route[0]:
                depart = random.uniform(0.0, 150.0)
                edges_str = " ".join([e.getID() for e in route[0]])
                bg_vehicles.append((depart, f"city_{i}", "passenger", edges_str))
        except Exception:
            pass

# 2. Concentrated traffic at Kankanady to build a queue organically
for i in range(25):
    src = random.choice(drivable_edges)
    dst = random.choice(drivable_edges)
    try:
        r1 = net.getShortestPath(src, kan_edge_in, vClass="passenger")
        r2 = net.getShortestPath(kan_edge_out, dst, vClass="passenger")
        if r1 and r1[0] and r2 and r2[0]:
            # Depart between 0 and 15 seconds to ensure they hit the red light right before ambulance arrives
            depart = random.uniform(0.0, 15.0)
            e1 = [e.getID() for e in r1[0]]
            e2 = [e.getID() for e in r2[0]]
            edges_str = " ".join(e1 + e2)
            bg_vehicles.append((depart, f"kan_queue_{i}", "passenger", edges_str))
    except Exception:
        pass

bg_vehicles.append((20.0, "ambulance", "ambulance", "amb_route"))
bg_vehicles.sort(key=lambda x: x[0])

with open(rou_file, "w") as f:
    f.write('<routes>\n')
    f.write('    <vType id="passenger" vClass="passenger" guiShape="passenger" maxSpeed="15.0" color="blue"/>\n')
    f.write('    <vType id="ambulance" vClass="emergency" guiShape="emergency" speedFactor="1.5" accel="2.5" decel="3.5" color="red" emissionClass="HBEFA3/PC_G_EU4"/>\n')
    f.write(f'    <route id="amb_route" edges="{" ".join(amb_edges)}"/>\n')
    
    for depart, vid, vtype, route_str in bg_vehicles:
        if vtype == "ambulance":
            f.write('    <vehicle id="ambulance" type="ambulance" route="amb_route" depart="20.0" departLane="best"/>\n')
        else:
            f.write(f'    <vehicle id="{vid}" type="passenger" depart="{depart:.1f}">\n')
            f.write(f'        <route edges="{route_str}"/>\n')
            f.write(f'    </vehicle>\n')
            
    f.write('</routes>\n')

with open(cfg_file, "w") as f:
    f.write('<configuration>\n')
    f.write('    <input>\n')
    f.write('        <net-file value="mangaluru_ai.net.xml.gz"/>\n')
    f.write('        <route-files value="kankanady_demo.rou.xml"/>\n')
    f.write('        <additional-files value="hospitals.add.xml"/>\n')
    f.write('    </input>\n')
    f.write('</configuration>\n')

print("Created files.")
