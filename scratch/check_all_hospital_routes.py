import sys
sys.path.append('AI-Predictive-Traffic')
from controller.hospital_manager import HospitalManager
from controller.astar_router import AStarRouter
import sumolib

net_file = 'AI-Predictive-Traffic/simulation/mangaluru/presentation_selection2.net.xml'
hospitals_file = 'AI-Predictive-Traffic/simulation/mangaluru/presentation_labels.add.xml'

net = sumolib.net.readNet(net_file)
hm = HospitalManager(net_file, hospitals_file)
router = AStarRouter(net_file)

spawn_edge = '1096889856'
print(f"Spawn edge: {spawn_edge}")

target_tls_edges = {
    '298371899': {'27191039#2', '-27191039#3', '-903009073'},
    '8387081772': {'27191039#3', '-27191039#4', '-903009075'},
    '11288614860': {'27191039#4', '-1218259556', '-27191039#5', '-1218977913'}
}

for h in hm.get_all_hospitals():
    route, cost = router.find_route(spawn_edge, h.nearest_edge)
    if route:
        r_set = set(route)
        hits = {}
        for tid, edges in target_tls_edges.items():
            common = r_set.intersection(edges)
            if common:
                hits[tid] = common
        print(f"Hospital {h.name} ({h.id}) edge={h.nearest_edge}: Route len={len(route)}, hits={hits}")
    else:
        print(f"Hospital {h.name} ({h.id}): No route found")
