import struct
import json
import sys

def inspect_glb(filename):
    try:
        with open(filename, 'rb') as f:
            magic = f.read(4)
            if magic != b'glTF':
                print('Not a valid GLB file')
                return
            version, length = struct.unpack('<II', f.read(8))
            chunk_len, chunk_type = struct.unpack('<II', f.read(8))
            if chunk_type != 0x4E4F534A: # 'JSON'
                print('First chunk is not JSON')
                return
            json_data = f.read(chunk_len).decode('utf-8')
            gltf = json.loads(json_data)
            
            nodes = gltf.get('nodes', [])
            meshes = gltf.get('meshes', [])
            materials = gltf.get('materials', [])
            
            print(f"GLB Node count: {len(nodes)}")
            print(f"GLB Mesh count: {len(meshes)}")
            print(f"GLB Material count: {len(materials)}")
            
            # Print Materials
            print("\n--- MATERIALS ---")
            for i, m in enumerate(materials):
                name = m.get('name', 'Unnamed')
                emissive = m.get('emissiveFactor', [0,0,0])
                print(f"Material {i}: {name} (Emissive: {emissive})")
                
            # Function to trace tree
            def trace_node(node_idx, indent=""):
                node = nodes[node_idx]
                name = node.get('name', 'Unnamed')
                mesh_idx = node.get('mesh')
                
                mesh_info = ""
                if mesh_idx is not None:
                    mesh = meshes[mesh_idx]
                    mesh_name = mesh.get('name', f'Mesh_{mesh_idx}')
                    prims = mesh.get('primitives', [])
                    mat_names = []
                    for p in prims:
                        mat_idx = p.get('material')
                        if mat_idx is not None:
                            mat_names.append(materials[mat_idx].get('name', 'Unnamed'))
                        else:
                            mat_names.append("NoMaterial")
                    mesh_info = f" [Mesh: {mesh_name} | Materials: {', '.join(mat_names)}]"
                    
                print(f"{indent}- Node {node_idx}: {name}{mesh_info}")
                for child_idx in node.get('children', []):
                    trace_node(child_idx, indent + "  ")

            print("\n--- HIERARCHY ---")
            scene_idx = gltf.get('scene', 0)
            scene = gltf.get('scenes', [])[scene_idx]
            for root_node_idx in scene.get('nodes', []):
                trace_node(root_node_idx)

    except Exception as e:
        print(f'Error: {e}')

if __name__ == "__main__":
    inspect_glb('d:/AIML/Projects/Major/gte_siemens_led_california_traffic_signal_set_3.glb')
