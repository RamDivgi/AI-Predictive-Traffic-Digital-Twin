import json

with open('MangaluruDigitalTwin3D/Assets/Generated/RoadNetwork.json') as f:
    d = json.load(f)

tls_list = d.get('traffic_lights', [])
print(f'Total TLS in RoadNetwork.json: {len(tls_list)}')

target_ids = ['298371899', '8387081772', '11288614860']
for t in tls_list:
    if t['id'] in target_ids:
        print(f"TLS {t['id']}: x={t['x']}, y={t['y']}, juncs={t['controlled_junctions']}")
        edges = set()
        for link in t['controlled_links']:
            from_lane = link['from_lane']
            if not from_lane.startswith(':'):
                edge = from_lane.rsplit('_', 1)[0]
                edges.add(edge)
            print(f"   link: idx={link['link_index']} from={link['from_lane']} to={link['to_lane']}")
        print(f"   Unique approach edges: {edges}")

edge_dict = {e['id']: e for e in d.get('edges', [])}
for tid in target_ids:
    print(f"\nChecking lane shapes for TLS {tid}:")
    t = next(x for x in tls_list if x['id'] == tid)
    for link in t['controlled_links']:
        fl = link['from_lane']
        if fl.startswith(':'):
            continue
        edge_id = fl.rsplit('_', 1)[0]
        if edge_id in edge_dict:
            edge = edge_dict[edge_id]
            lane = next((l for l in edge['lanes'] if l['id'] == fl), None)
            if lane:
                print(f"   {fl}: points={len(lane['shape'])}, start={lane['shape'][0]}, end={lane['shape'][-1]}")
            else:
                print(f"   {fl}: lane not found in edge {edge_id}")
        else:
            print(f"   {edge_id}: edge not found in edges!")
