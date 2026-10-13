import struct
import zlib
from pathlib import Path

def find_front_direction(fbx_path):
    with open(fbx_path, 'rb') as f:
        data = f.read()
    pos = data.find(b'Vertices')
    arr_idx = data.find(b'd', pos, pos+100)
    arr_len, enc, comp_len = struct.unpack('<III', data[arr_idx+1:arr_idx+13])
    raw = data[arr_idx+13:arr_idx+13+arr_len*8] if enc == 0 else zlib.decompress(data[arr_idx+13:arr_idx+13+comp_len])
    verts = struct.unpack(f'<{arr_len}d', raw)
    xs = [v/100.0 for v in verts[0::3]]
    ys = [v/100.0 for v in verts[1::3]]
    zs = [v/100.0 for v in verts[2::3]]
    
    # Check entrance features (steps/porch usually near ground Y in [0, 1.5]m with extreme Z)
    ground_pts = [(xs[i], ys[i], zs[i]) for i in range(len(xs)) if ys[i] < 0.5]
    pos_z_pts = [p for p in ground_pts if p[2] > 0]
    neg_z_pts = [p for p in ground_pts if p[2] < 0]
    
    # Check door/entrance cutout or overhang
    max_z = max(zs)
    min_z = min(zs)
    print(f"{fbx_path.stem}:")
    print(f"  Z range: [{min_z:.2f}, {max_z:.2f}]")
    print(f"  Points near ground (Y<0.5m): +Z count={len(pos_z_pts)}, -Z count={len(neg_z_pts)}")

models = [
    Path(r"D:\AIML\Projects\Major\MangaluruDigitalTwin3D\Assets\Models\Models\Buildings\Residential House 01\fbx\Residential House 01.fbx"),
    Path(r"D:\AIML\Projects\Major\MangaluruDigitalTwin3D\Assets\Models\Models\Buildings\Residential House 02\fbx\Residential House 02.fbx"),
    Path(r"D:\AIML\Projects\Major\MangaluruDigitalTwin3D\Assets\Models\Models\Buildings\Residential House 09\fbx\Residential House 09.fbx"),
    Path(r"D:\AIML\Projects\Major\MangaluruDigitalTwin3D\Assets\Models\Models\Buildings\175 Bloor St W\fbx\175 Bloor St W (version 2.0).fbx"),
    Path(r"D:\AIML\Projects\Major\MangaluruDigitalTwin3D\Assets\Models\Models\Buildings\594 Bloor St E\fbx\594 Bloor St E (version 2.0).fbx")
]

for m in models:
    find_front_direction(m)
