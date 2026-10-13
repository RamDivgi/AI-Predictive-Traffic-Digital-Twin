import sys
sys.path.append('AI-Predictive-Traffic')
import sumolib

net = sumolib.net.readNet('AI-Predictive-Traffic/simulation/mangaluru/presentation_selection2.net.xml')

# Highland hospital nearest edge
# Let's find highland hospital in presentation_labels.add.xml
import xml.etree.ElementTree as ET
tree = ET.parse('AI-Predictive-Traffic/simulation/mangaluru/presentation_labels.add.xml')
for poi in tree.getroot().findall('poi'):
    if 'highland' in poi.get('id', '').lower():
        print(f"Highland POI: {poi.attrib}")
        x, y = float(poi.get('x')), float(poi.get('y'))
        nearby = net.getNeighboringEdges(x, y, r=200)
        suitable = [(e, d) for e, d in nearby if e.allows('passenger')]
        suitable.sort(key=lambda x: x[1])
        dest_edge = suitable[0][0].getID()
        print(f"Highland nearest edge: {dest_edge}")

spawn_edge = '1096889856'
print(f"Spawn: {spawn_edge}")

# Check sumolib shortest path
route, cost = net.getShortestPath(net.getEdge(spawn_edge), net.getEdge(dest_edge))
edge_ids = [e.getID() for e in route]
print("Shortest path edges:", edge_ids)

target_edges = {
    '298371899': {'27191039#2', '-27191039#3', '-903009073'},
    '8387081772': {'27191039#3', '-27191039#4', '-903009075'},
    '11288614860': {'27191039#4', '-1218259556', '-27191039#5', '-1218977913'}
}

for tid, edges in target_edges.items():
    print(f"TLS {tid} in route: {edges.intersection(set(edge_ids))}")
