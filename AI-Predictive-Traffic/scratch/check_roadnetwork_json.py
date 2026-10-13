import json
from pathlib import Path

for path in ['visualization/RoadNetwork.json', '../MangaluruDigitalTwin3D/Assets/Generated/RoadNetwork.json']:
    p = Path(path)
    if not p.exists():
        print(f'{path} does not exist!')
        continue
    with open(p, 'r') as f:
        data = json.load(f)
    print(f'=== {path} ===')
    tls_list = data.get('traffic_lights', [])
    print(f'Total traffic lights in JSON: {len(tls_list)}')
    for tid in ['298371899', '8387081772', '11288614860']:
        found = [t for t in tls_list if t['id'] == tid]
        if found:
            t = found[0]
            print(f'  Found {tid}: x={t["x"]}, y={t["y"]}, controlled_juncs={t["controlled_junctions"]}, num_links={len(t["controlled_links"])}')
        else:
            print(f'  MISSING {tid} in {path}!')
