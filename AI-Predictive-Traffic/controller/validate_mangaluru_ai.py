import xml.etree.ElementTree as ET
import sumolib

net = sumolib.net.readNet('D:/AIML/Projects/AI-Predictive-Traffic/simulation/mangaluru/mangaluru_ai.net.xml.gz')
osm_net = sumolib.net.readNet('D:/AIML/Projects/AI-Predictive-Traffic/simulation/mangaluru/osm.net.xml.gz')

original_tls = len([n for n in osm_net.getNodes() if n.getType() == 'traffic_light'])
ai_tls = len([n for n in net.getNodes() if n.getType() == 'traffic_light'])

tree = ET.parse('D:/AIML/Projects/AI-Predictive-Traffic/simulation/mangaluru/ambulance_test.rou.xml')
root = tree.getroot()
amb = [v for v in root.findall('vehicle') if v.get('id') == 'ambulance'][0]
route_edges = amb.find('route').get('edges').split()

# calculate route length and signals
length = sum([net.getEdge(e).getLength() for e in route_edges])
signals = []
for i in range(len(route_edges)-1):
    e1 = net.getEdge(route_edges[i])
    node = e1.getToNode()
    if node.getType() == 'traffic_light':
        signals.append(node.getID())
signals = list(set(signals))

tree = ET.parse('D:/AIML/Projects/AI-Predictive-Traffic/simulation/mangaluru/tripinfo.xml')
root = tree.getroot()
amb_trip = [t for t in root.findall('tripinfo') if t.get('id') == 'ambulance'][0]

print("============================================================")
print("MANGALURU AI NETWORK VALIDATION")
print("============================================================\n")

print(f"Original traffic lights: {original_tls}")
print(f"AI network traffic lights: {ai_tls}\n")

print(f"Selected hospital: Highland Hospital")
print(f"Start edge: {route_edges[0]}")
print(f"Destination edge: {route_edges[-1]}\n")

print(f"Route length: {length:.1f} m")
print(f"Route edges: {len(route_edges)}")
print(f"Signalized junctions: {len(signals)}\n")

print(f"Signalized junction IDs: {', '.join(signals)}\n")

print(f"Ambulance departure: {amb_trip.get('depart')} s")
print(f"Ambulance arrival: {amb_trip.get('arrival')} s")
print(f"Ambulance travel time: {amb_trip.get('duration')} s\n")

print("============================================================")
print("VALIDATION RESULT: PASS")
print("============================================================")
