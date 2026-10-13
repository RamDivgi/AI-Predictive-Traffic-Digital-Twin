import sys, os
sys.path.insert(0, os.path.abspath('.'))
from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)

print('--- VERIFYING CLEAN DATA MAPPINGS ---')

# 1. Starting points mapping
pts = client.get('/starting-points').json()
assert len(pts) == 4, f'Expected 4 points, got {len(pts)}'
for p in pts:
    assert 'label' in p and p['label'], f'Missing label in {p}'
    assert 'name' in p and p['name'], f'Missing name in {p}'
    assert 'outgoing_edge' in p and p['outgoing_edge'], f'Missing outgoing_edge in {p}'
    print(f"Start Point: {p['name']} -> {p['outgoing_edge']}")

# 2. Road Network Edges mapping
edges = client.get('/network/edges').json()
assert len(edges) > 50, f'Expected >50 edges, got {len(edges)}'
for e in edges[:5]:
    assert 'id' in e and e['id'], f'Missing id in {e}'
    assert 'edge_id' in e and e['edge_id'], f'Missing edge_id in {e}'
    assert 'lanes' in e and e['lanes'] > 0, f'Missing lanes in {e}'
    assert 'lane_count' in e and e['lane_count'] > 0, f'Missing lane_count in {e}'
    print(f"Road Edge: {e['edge_id']} ({e['lanes']} lanes, {e.get('length_m')}m)")

# 3. Hospital recommendation
rec = client.get('/hospitals/recommend?start_edge=1096889856').json()
assert 'recommendations' in rec and len(rec['recommendations']) > 0
top = rec['recommendations'][0]
assert 'name' in top and top['name']
assert 'cost_seconds' in top and top['cost_seconds'] > 0
assert 'distance_meters' in top and top['distance_meters'] > 0
print(f"Top Recommendation: {top['name']} ({top['cost_seconds']}s, {top['distance_meters']}m)")

print('--- ALL DATA INTEGRITY CHECKS PASSED (100%) ---')
