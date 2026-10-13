import xml.etree.ElementTree as ET

tree = ET.parse('AI-Predictive-Traffic/simulation/mangaluru/presentation_demo.rou.xml')
root = tree.getroot()

amb_routes = []
for veh in root.findall('.//vehicle'):
    if veh.get('id') == 'ambulance':
        route = veh.find('route')
        if route is not None:
            amb_routes.append(route.get('edges').split())

print('Found ambulance routes:', len(amb_routes))
target_edges = {
    '298371899': {'27191039#2', '-27191039#3', '-903009073'},
    '8387081772': {'27191039#3', '-27191039#4', '-903009075'},
    '11288614860': {'27191039#4', '-1218259556', '-27191039#5', '-1218977913'}
}

if amb_routes:
    edges = set(amb_routes[0])
    print('Ambulance route edges count:', len(edges))
    for tid, tedges in target_edges.items():
        print(f'TLS {tid} edges in route: {tedges.intersection(edges)}')
else:
    print("No ambulance vehicle found in presentation_demo.rou.xml, checking other rou.xml files...")
    import glob
    for p in glob.glob('AI-Predictive-Traffic/simulation/mangaluru/*.rou.xml'):
        t = ET.parse(p)
        r = t.getroot()
        for veh in r.findall('.//vehicle'):
            if veh.get('id') == 'ambulance':
                rt = veh.find('route')
                if rt is not None:
                    ed = set(rt.get('edges').split())
                    print(f"File {p}:")
                    for tid, tedges in target_edges.items():
                        print(f"  TLS {tid} edges in route: {tedges.intersection(ed)}")
