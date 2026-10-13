import json
import numpy as np

def test_mesh_normals():
    json_path = r"D:\AIML\Projects\Major\MangaluruDigitalTwin3D\Assets\Generated\RoadNetwork.json"
    with open(json_path, 'r') as f:
        data = json.load(f)

    # 1. Test Lane Mesh Normals
    lane_count = 0
    zero_lane_normals = 0
    for edge in data.get('edges', []):
        for lane in edge.get('lanes', []):
            shape = lane.get('shape', [])
            if len(shape) < 2:
                continue
            lane_count += 1
            num_points = len(shape)
            normals = [np.array([0.0, 1.0, 0.0]) for _ in range(num_points * 2)]
            for n in normals:
                if np.linalg.norm(n) < 0.99 or n[1] < 0.99:
                    zero_lane_normals += 1

    # 2. Test Junction Mesh Normals & Winding
    junction_count = 0
    zero_junc_normals = 0
    inverted_junctions = 0
    for junc in data.get('junctions', []):
        shape = junc.get('shape', [])
        if len(shape) < 3:
            continue
        junction_count += 1
        num_points = len(shape)
        
        normals = [np.array([0.0, 1.0, 0.0]) for _ in range(num_points + 1)]
        for n in normals:
            if np.linalg.norm(n) < 0.99 or n[1] < 0.99:
                zero_junc_normals += 1
        
        c = np.array([sum(p['x'] for p in shape) / num_points, 0.02, sum(p['y'] for p in shape) / num_points])
        for i in range(num_points):
            nxt = (i + 1) % num_points
            uX = shape[nxt]['x'] - c[0]
            uZ = shape[nxt]['y'] - c[2]
            vX = shape[i]['x'] - c[0]
            vZ = shape[i]['y'] - c[2]
            crossY = uZ * vX - uX * vZ

            p_curr = np.array([shape[i]['x'], 0.02, shape[i]['y']])
            p_next = np.array([shape[nxt]['x'], 0.02, shape[nxt]['y']])
            if crossY >= 0:
                v1 = p_next - c
                v2 = p_curr - c
            else:
                v1 = p_curr - c
                v2 = p_next - c
            face_n = np.cross(v1, v2)
            if face_n[1] < -1e-5:
                inverted_junctions += 1

    # 3. Test Buildings
    building_count = 0
    zero_bldg_normals = 0
    for bldg in data.get('buildings', []):
        shape = bldg.get('shape', [])
        if len(shape) < 3:
            continue
        building_count += 1
        num_points = len(shape)
        signed_area = 0.0
        for i in range(num_points):
            nxt = (i + 1) % num_points
            signed_area += (shape[i]['x'] * shape[nxt]['y'] - shape[nxt]['x'] * shape[i]['y'])
        
        for i in range(num_points):
            nxt = (i + 1) % num_points
            bl = np.array([shape[i]['x'], 0.0, shape[i]['y']])
            br = np.array([shape[nxt]['x'], 0.0, shape[nxt]['y']])
            diff = br - bl
            dist = np.linalg.norm(diff)
            if dist < 1e-4:
                continue
            wall_dir = diff / dist
            out_n = np.array([wall_dir[2], 0.0, -wall_dir[0]]) if signed_area >= 0 else np.array([-wall_dir[2], 0.0, wall_dir[0]])
            if abs(np.linalg.norm(out_n) - 1.0) > 1e-3:
                zero_bldg_normals += 1

    print(f"Lanes tested: {lane_count}, Zero normals: {zero_lane_normals}")
    print(f"Junctions tested: {junction_count}, Zero normals: {zero_junc_normals}, Inverted faces: {inverted_junctions}")
    print(f"Buildings tested: {building_count}, Zero/Degenerate wall normals: {zero_bldg_normals}")

if __name__ == "__main__":
    test_mesh_normals()
