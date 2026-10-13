import json
import math

with open('MangaluruDigitalTwin3D/Assets/Generated/RoadNetwork.json') as f:
    d = json.load(f)

lane_dict = {}
for e in d['edges']:
    for l in e['lanes']:
        lane_dict[l['id']] = l

target_ids = ['298371899', '8387081772', '11288614860']

for tls in d['traffic_lights']:
    if tls['id'] in target_ids:
        print(f"==================================================")
        print(f"TLS {tls['id']} at ({tls['x']}, {tls['y']}):")
        processed_edges = set()
        for link in tls['controlled_links']:
            fl = link['from_lane']
            if fl.startswith(':'): continue
            edge = fl.rsplit('_', 1)[0]
            if edge in processed_edges: continue
            processed_edges.add(edge)
            
            lane = lane_dict.get(fl)
            if not lane:
                print(f"  Lane {fl} missing!")
                continue
            pts = lane['shape']
            p_prev = pts[-2]
            p_last = pts[-1]
            dx = p_last['x'] - p_prev['x']
            dy = p_last['y'] - p_prev['y']
            length = math.hypot(dx, dy)
            dir_x = dx / length
            dir_y = dy / length
            
            # Left roadside offset: (-dir_y, dir_x)
            left_x = -dir_y
            left_y = dir_x
            sig_x = p_last['x'] + left_x * 2.5
            sig_y = p_last['y'] + left_y * 2.5
            
            # Local pos relative to tlsRoot
            rel_x = sig_x - tls['x']
            rel_z = sig_y - tls['y']
            
            # Orientation angle in degrees
            # Facing oncoming traffic: LookRotation(-dir, up)
            # -dir has components (-dir_x, -dir_y)
            angle_deg = math.degrees(math.atan2(-dir_x, -dir_y))
            
            print(f"  Approach Edge '{edge}':")
            print(f"    From Lane: {fl}")
            print(f"    Road end: ({p_last['x']:.2f}, {p_last['y']:.2f}), dir: ({dir_x:.2f}, {dir_y:.2f})")
            print(f"    Signal Pos (World): ({sig_x:.2f}, {sig_y:.2f})")
            print(f"    Signal Pos (Local to TLS): ({rel_x:.2f}, {rel_z:.2f})")
            print(f"    Facing Vector (-dir): ({-dir_x:.2f}, 0, {-dir_y:.2f})")
