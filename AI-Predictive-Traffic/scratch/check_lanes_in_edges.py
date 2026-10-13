import json

with open('visualization/RoadNetwork.json') as f:
    data = json.load(f)

edge_lanes = set()
for e in data['edges']:
    for l in e['lanes']:
        edge_lanes.add(l['id'])

print(f"Total lanes in edges: {len(edge_lanes)}")

for tid in ['298371899', '8387081772', '11288614860']:
    tls_matches = [t for t in data['traffic_lights'] if t['id'] == tid]
    if not tls_matches:
        print(f"TLS {tid} not in traffic_lights!")
        continue
    tls = tls_matches[0]
    print(f"\nTLS {tid} (links count={len(tls['controlled_links'])}):")
    for link in tls['controlled_links']:
        from_lane = link['from_lane']
        in_dict = from_lane in edge_lanes
        print(f"  Link {link['link_index']}: from_lane={from_lane} (in edges: {in_dict})")
