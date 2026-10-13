import json
import xml.etree.ElementTree as ET
from pathlib import Path

# Paths
PROJECT_ROOT = Path("d:/AIML/Projects/Major/AI-Predictive-Traffic")
SUMO_NET_FILE = PROJECT_ROOT / "simulation" / "mangaluru" / "presentation_selection2.net.xml"
UNITY_FILE = PROJECT_ROOT / "visualization" / "RoadNetwork.json"

# Parse SUMO
tree = ET.parse(SUMO_NET_FILE)
root = tree.getroot()

sumo_tls_ids = set()
tls_controlled_nodes = {}  # tls_id -> set of nodes it controls

for tl in root.findall('tlLogic'):
    tl_id = tl.get('id')
    sumo_tls_ids.add(tl_id)
    tls_controlled_nodes[tl_id] = set()

# A connection describes which tl controls which link/approach
for conn in root.findall('connection'):
    tl_id = conn.get('tl')
    if tl_id:
        from_edge = conn.get('from')
        to_edge = conn.get('to')
        # To find the exact node, we need to find the junction connecting these edges,
        # or we can look at the junction elements directly.

sumo_nodes_tls = {} # node_id -> set of tl_ids
for junction in root.findall('junction'):
    node_id = junction.get('id')
    if junction.get('type') == 'traffic_light':
        # Which tls control this junction?
        # A junction can have multiple tlLogic elements (usually not, but possible),
        # or more commonly, the tlLogic ID might be different from the junction ID if it's a cluster.
        # But `junction` might have `incLanes` or we can find `connection` that goes through this junction.
        pass

# The easier way to map: A connection has `from` and `to` and `tl`.
# A junction has `incLanes` which are the lanes approaching it.
# We can find out which node a `tlLogic` is controlling.

# Let's use sumolib for easier parsing
import sumolib
net = sumolib.net.readNet(str(SUMO_NET_FILE))

sumo_tls_controllers = net.getTrafficLights()
sumo_tls_ids_lib = {tl.getID() for tl in sumo_tls_controllers}

print(f"SUMO TLS from XML (tlLogic): {len(sumo_tls_ids)}")
print(f"SUMO TLS from sumolib: {len(sumo_tls_ids_lib)}")

tls_to_nodes = {}
node_to_tls = {}
for tl in sumo_tls_controllers:
    tl_id = tl.getID()
    tls_to_nodes[tl_id] = set()
    for conn in tl.getLinks():
        # conn is a dictionary mapping from connection to link index?
        # Actually in sumolib, getLinks() returns a dictionary of links:
        # It's a dict mapping node -> list of links?
        pass

# Let's inspect sumolib TrafficLight methods
# Actually, the simplest is to look at nodes of type "traffic_light".
tls_nodes_sumo = [n for n in net.getNodes() if n.getType() == "traffic_light"]
print(f"SUMO nodes of type 'traffic_light': {len(tls_nodes_sumo)}")

# Let's see how many tls ids actually exist
for node in tls_nodes_sumo:
    node_id = node.getID()
    # A node of type traffic_light has a getTLS() method in sumolib maybe?
    # tls = node.getTLS()
    pass

# Read Unity Export
with open(UNITY_FILE) as f:
    unity_data = json.load(f)

unity_tls_nodes = set(j['id'] for j in unity_data.get('traffic_lights', []))
print(f"Unity exported TLS nodes: {len(unity_tls_nodes)}")

# Let's print out the exact mismatch
common = sumo_tls_ids.intersection(unity_tls_nodes)
only_in_sumo = sumo_tls_ids - unity_tls_nodes
only_in_unity = unity_tls_nodes - sumo_tls_ids

print(f"Common TLS/Junction IDs: {len(common)}")
print(f"Only in SUMO TLS IDs (tlLogic IDs that aren't node IDs in Unity): {len(only_in_sumo)}")
print(f"Only in Unity (nodes marked as TLS that aren't tlLogic IDs): {len(only_in_unity)}")

# Let's try to map the Only In Unity nodes to their corresponding tlLogic.
# A tlLogic has connections. Each connection has a `from` edge and `to` edge.
# We can find the node where the `from` edge ends.
node_to_tls_id_map = {}
for conn in root.findall('connection'):
    tl = conn.get('tl')
    if tl:
        from_edge_id = conn.get('from')
        if net.hasEdge(from_edge_id):
            edge = net.getEdge(from_edge_id)
            node = edge.getToNode()
            node_id = node.getID()
            if node_id not in node_to_tls_id_map:
                node_to_tls_id_map[node_id] = set()
            node_to_tls_id_map[node_id].add(tl)

print("Mapping Unity-only nodes to SUMO TLS:")
for u in only_in_unity:
    if u in node_to_tls_id_map:
        print(f"  Unity Node {u} is controlled by SUMO TLS {node_to_tls_id_map[u]}")
    else:
        print(f"  Unity Node {u} is not controlled by any TLS connections!")

print("Mapping SUMO-only TLS to nodes:")
tls_to_nodes_map = {}
for n, tls_set in node_to_tls_id_map.items():
    for tl in tls_set:
        if tl not in tls_to_nodes_map:
            tls_to_nodes_map[tl] = set()
        tls_to_nodes_map[tl].add(n)

for s in only_in_sumo:
    if s in tls_to_nodes_map:
        print(f"  SUMO TLS {s} controls nodes {tls_to_nodes_map[s]}")
    else:
        print(f"  SUMO TLS {s} controls NO nodes!")
