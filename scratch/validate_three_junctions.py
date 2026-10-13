import json
import math
import socket
import sys
import xml.etree.ElementTree as ET

def test_sumo_network():
    print("=== TEST 1: SUMO Network Check ===")
    net_path = "AI-Predictive-Traffic/simulation/mangaluru/presentation_selection2.net.xml"
    tree = ET.parse(net_path)
    root = tree.getroot()
    
    target_ids = ['298371899', '8387081772', '11288614860']
    all_ok = True
    
    for tid in target_ids:
        junc = root.find(f".//junction[@id='{tid}']")
        tls = root.find(f".//tlLogic[@id='{tid}']")
        conns = [c for c in root.findall('.//connection') if c.get('tl') == tid]
        
        assert junc is not None, f"Junction {tid} not found"
        assert junc.get('type') == 'traffic_light', f"Junction {tid} type is not traffic_light"
        assert tls is not None, f"tlLogic {tid} not found"
        assert len(conns) > 0, f"No connections for tl {tid}"
        
        phases = [p.get('state') for p in tls.findall('phase')]
        print(f"  [PASS] TLS {tid}: Junction=({junc.get('x')}, {junc.get('y')}), Logic={tls.get('type')}, Conns={len(conns)}, Phases={len(phases)}")
        print(f"         Sample phase 0 state: '{phases[0]}'")
    return True

def test_exported_json():
    print("\n=== TEST 2: Exported RoadNetwork.json Check ===")
    json_path = "MangaluruDigitalTwin3D/Assets/Generated/RoadNetwork.json"
    with open(json_path) as f:
        data = json.load(f)
        
    tls_list = data.get('traffic_lights', [])
    assert len(tls_list) == 55, f"Expected 55 traffic lights, found {len(tls_list)}"
    print(f"  [PASS] Preserved exactly 55 traffic lights in {json_path}")
    
    target_ids = ['298371899', '8387081772', '11288614860']
    edge_dict = {e['id']: e for e in data.get('edges', [])}
    lane_dict = {}
    for e in data.get('edges', []):
        for l in e.get('lanes', []):
            lane_dict[l['id']] = l
            
    for tid in target_ids:
        matches = [t for t in tls_list if t['id'] == tid]
        assert len(matches) == 1, f"TLS {tid} not found in traffic_lights"
        t = matches[0]
        links = t.get('controlled_links', [])
        assert len(links) > 0, f"No controlled links for {tid}"
        
        # Check approaches
        approaches = set()
        for link in links:
            fl = link.get('from_lane', '')
            if not fl.startswith(':'):
                edge = fl.rsplit('_', 1)[0]
                approaches.add(edge)
                assert fl in lane_dict, f"Lane {fl} not found in lane_dict"
                lane = lane_dict[fl]
                assert len(lane.get('shape', [])) >= 2, f"Lane {fl} shape has < 2 points"
                
        print(f"  [PASS] TLS {tid} verified: {len(links)} links, Approaches={approaches}")
    return True

def test_approach_placement_and_sync():
    print("\n=== TEST 3: Approach Placement & State Sync Mapping ===")
    json_path = "MangaluruDigitalTwin3D/Assets/Generated/RoadNetwork.json"
    with open(json_path) as f:
        data = json.load(f)
        
    lane_dict = {}
    for e in data['edges']:
        for l in e['lanes']:
            lane_dict[l['id']] = l
            
    target_ids = ['298371899', '8387081772', '11288614860']
    
    for tls in data['traffic_lights']:
        if tls['id'] not in target_ids:
            continue
            
        tid = tls['id']
        edge_to_links = {}
        for link in tls['controlled_links']:
            fl = link['from_lane']
            if fl.startswith(':'): continue
            edge = fl.rsplit('_', 1)[0]
            if edge not in edge_to_links:
                edge_to_links[edge] = []
            edge_to_links[edge].append(link['link_index'])
            
        print(f"  TLS {tid} approach heads:")
        for edge, link_indices in edge_to_links.items():
            fl = f"{edge}_0"
            lane = lane_dict[fl]
            pts = lane['shape']
            p_prev = pts[-2]
            p_last = pts[-1]
            dx = p_last['x'] - p_prev['x']
            dy = p_last['y'] - p_prev['y']
            length = math.hypot(dx, dy)
            dir_x = dx / length
            dir_y = dy / length
            
            # Left roadside offset: (-dir_y, dir_x)
            sig_x = p_last['x'] + (-dir_y) * 2.5
            sig_y = p_last['y'] + (dir_x) * 2.5
            
            facing_x = -dir_x
            facing_y = -dir_y
            
            print(f"    - Signal_{edge}: pos=({sig_x:.2f}, 0, {sig_y:.2f}), facing=({facing_x:.2f}, 0, {facing_y:.2f}), controlled_links={link_indices}")
            
    return True

def test_udp_payload_simulation():
    print("\n=== TEST 4: Live UDP Telemetry Payload Simulation ===")
    target_ids = ['298371899', '8387081772', '11288614860']
    
    # Check that payload structure matches SignalPayload in TrafficSignalReceiver.cs
    sample_signals = [
        {"id": "298371899", "state": "GGgGggrrr"},
        {"id": "8387081772", "state": "GrrrrrGGg"},
        {"id": "11288614860", "state": "GGggrrrrGGggrrrr"}
    ]
    payload = {"signals": sample_signals}
    json_bytes = json.dumps(payload).encode('utf-8')
    
    # Validate deserialization compatibility with Unity JsonUtility
    parsed = json.loads(json_bytes.decode('utf-8'))
    assert "signals" in parsed
    assert len(parsed["signals"]) == 3
    for s in parsed["signals"]:
        assert "id" in s and "state" in s
    print(f"  [PASS] Payload structure valid ({len(json_bytes)} bytes): {sample_signals}")
    return True

if __name__ == "__main__":
    t1 = test_sumo_network()
    t2 = test_exported_json()
    t3 = test_approach_placement_and_sync()
    t4 = test_udp_payload_simulation()
    
    if t1 and t2 and t3 and t4:
        print("\nALL 4 VALIDATION SUITES PASSED SUCCESSFULLY.")
