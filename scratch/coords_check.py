import json

with open('MangaluruDigitalTwin3D/Assets/Generated/RoadNetwork.json') as f:
    d = json.load(f)

for t in d['traffic_lights']:
    if t['id'] in ['298371899', '8387081772', '11288614860']:
        print(f"TLS {t['id']}: x={t['x']}, y={t['y']}")

for h in d['hospitals']:
    print(f"Hospital {h['name']}: x={h['x']}, y={h['y']}")
