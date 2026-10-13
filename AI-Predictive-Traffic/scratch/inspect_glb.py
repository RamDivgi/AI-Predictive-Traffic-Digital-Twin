import struct
import json

filename = 'd:/AIML/Projects/Major/gte_siemens_led_california_traffic_signal_set_3.glb'
try:
    with open(filename, 'rb') as f:
        magic = f.read(4)
        if magic != b'glTF':
            print('Not a valid GLB file')
            exit(1)
        version, length = struct.unpack('<II', f.read(8))
        chunk_len, chunk_type = struct.unpack('<II', f.read(8))
        if chunk_type != 0x4E4F534A: # 'JSON'
            print('First chunk is not JSON')
            exit(1)
        json_data = f.read(chunk_len).decode('utf-8')
        gltf = json.loads(json_data)
        
        print('Nodes:')
        for i, n in enumerate(gltf.get('nodes', [])):
            print(f"  {i}: {n.get('name', 'Unnamed')}")
            
        print('\nMaterials:')
        for i, m in enumerate(gltf.get('materials', [])):
            print(f"  {i}: {m.get('name', 'Unnamed')}")
except Exception as e:
    print(f'Error: {e}')
