import json
import math

with open('MangaluruDigitalTwin3D/Assets/Generated/RoadNetwork.json', 'r') as f:
    network_data = json.load(f)

lane_dict = {}
for edge in network_data.get('edges', []):
    for lane in edge.get('lanes', []):
        lane_dict[lane['id']] = lane

tls_list = network_data.get('traffic_lights', [])
print(f"Total TLS in json: {len(tls_list)}")

target_ids = ['298371899', '8387081772', '11288614860']

for tls in tls_list:
    tid = tls['id']
    is_target = tid in target_ids
    
    signals_created = []
    skipped_reasons = []
    
    processed_edges = set()
    
    for link in tls.get('controlled_links', []):
        from_lane = link.get('from_lane', '')
        if not from_lane:
            skipped_reasons.append(f"link {link.get('link_index')}: empty from_lane")
            continue
        if from_lane.startswith(':'):
            continue
            
        last_underscore = from_lane.rfind('_')
        from_edge = from_lane[:last_underscore] if last_underscore > 0 else from_lane
        
        if from_edge in processed_edges:
            continue
        processed_edges.add(from_edge)
        
        if from_lane not in lane_dict:
            skipped_reasons.append(f"edge {from_edge} (lane {from_lane}): NOT IN lane_dict")
            continue
            
        lane_data = lane_dict[from_lane]
        shape = lane_data.get('shape', [])
        if len(shape) < 2:
            skipped_reasons.append(f"edge {from_edge} (lane {from_lane}): shape < 2 points ({len(shape)})")
            continue
            
        p_prev = shape[-2]
        p_last = shape[-1]
        
        dx = p_last['x'] - p_prev['x']
        dy = p_last['y'] - p_prev['y']
        mag = math.hypot(dx, dy)
        if mag == 0:
            skipped_reasons.append(f"edge {from_edge}: dir is zero")
            continue
            
        dir_x = dx / mag
        dir_z = dy / mag
        
        # In Unity: leftDir = -Vector3.Cross(Vector3.up, dir).normalized
        # Cross((0,1,0), (dir_x, 0, dir_z)) = (1*dir_z - 0*0, 0, 0*0 - 1*dir_x) = (dir_z, 0, -dir_x)
        # -Cross = (-dir_z, 0, dir_x)
        left_x = -dir_z
        left_z = dir_x
        
        offset = 2.5
        sig_pos_x = p_last['x'] + left_x * offset
        sig_pos_z = p_last['y'] + left_z * offset
        
        signals_created.append((from_edge, sig_pos_x, sig_pos_z))
        
    if is_target or len(signals_created) == 0:
        print(f"\nTLS {tid}: Created {len(signals_created)} signals.")
        for s in signals_created:
            print(f"  Signal_{s[0]} at ({s[1]:.2f}, {s[2]:.2f})")
        if skipped_reasons:
            print(f"  Skipped: {skipped_reasons}")
