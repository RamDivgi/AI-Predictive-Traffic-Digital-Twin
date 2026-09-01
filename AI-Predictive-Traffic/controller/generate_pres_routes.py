import random

rou_file = "d:/AIML/Projects/Major/AI-Predictive-Traffic/simulation/mangaluru/presentation_demo.rou.xml"

amb_route = "1096889856 -1096889856 -184750315#1 -184750315#0 1055574152#1 1055574152#2 26182678#1 26182678#2 26182678#3 26299204#0 1189020226#1 1189020226#2 1189020226#3 -132363066#1 -132363066#0 903009071#1"

with open(rou_file, 'w') as f:
    f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
    f.write('<routes>\n')
    f.write('    <vType id="passenger" vClass="passenger" guiShape="passenger" maxSpeed="15.0" color="blue" length="5.0"/>\n')
    f.write('    <vType id="ambulance" vClass="emergency" guiShape="emergency" speedFactor="1.5" accel="2.5" decel="3.5" color="red" length="7.0" width="2.5"/>\n')
    
    f.write(f'    <route id="amb_route" edges="{amb_route}"/>\n')
    
    # Ambulance
    f.write('    <vehicle id="ambulance" type="ambulance" route="amb_route" depart="10.0" departLane="best"/>\n')
    
    # Background traffic - cars on the same route but starting earlier to create queue at TLS
    amb_edges = amb_route.split()
    
    for i in range(30):
        # We want cars to spawn ahead of the ambulance and drive on the same path to get stuck at the red light
        depart_time = random.uniform(0, 15)
        # Start at various points along the first half of the route
        start_idx = random.randint(0, 8)
        end_idx = random.randint(max(10, start_idx+1), len(amb_edges)-1)
        sub_route = " ".join(amb_edges[start_idx:end_idx+1])
        f.write(f'    <vehicle id="car_{i}" type="passenger" depart="{depart_time:.1f}">\n')
        f.write(f'        <route edges="{sub_route}"/>\n')
        f.write('    </vehicle>\n')
        
    f.write('</routes>\n')

print(f"Generated {rou_file}")
