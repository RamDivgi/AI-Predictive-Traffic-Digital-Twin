import struct
import zlib
from pathlib import Path

def find_details(fbx_path):
    with open(fbx_path, 'rb') as f: data = f.read()
    pos = data.find(b'Vertices')
    arr_idx = data.find(b'd', pos, pos+100)
    arr_len, enc, comp_len = struct.unpack('<III', data[arr_idx+1:arr_idx+13])
    raw = data[arr_idx+13:arr_idx+13+arr_len*8] if enc == 0 else zlib.decompress(data[arr_idx+13:arr_idx+13+comp_len])
    verts = struct.unpack(f'<{arr_len}d', raw)
    xs = [v/100.0 for v in verts[0::3]]
    ys = [v/100.0 for v in verts[1::3]]
    zs = [v/100.0 for v in verts[2::3]]
    
    # In house models, the front porch / steps are at ground level (Y < 0.2m)
    steps_z = [zs[i] for i in range(len(xs)) if 0.0 <= ys[i] <= 0.2]
    # Average Z of ground steps
    print(f"{fbx_path.stem}:")
    print(f"  Lowest vertices (0<=Y<=0.2m): count={len(steps_z)}, minZ={min(steps_z):.2f}, maxZ={max(steps_z):.2f}")
    # Highest roof peak:
    max_y = max(ys)
    roof_peak_z = [zs[i] for i in range(len(xs)) if ys[i] > max_y - 0.5]
    print(f"  Roof peak (Y > {max_y-0.5:.1f}m): count={len(roof_peak_z)}, avgZ={sum(roof_peak_z)/len(roof_peak_z):.2f}")

models = [
    Path(r"D:\AIML\Projects\Major\MangaluruDigitalTwin3D\Assets\Models\Models\Buildings\Residential House 01\fbx\Residential House 01.fbx"),
    Path(r"D:\AIML\Projects\Major\MangaluruDigitalTwin3D\Assets\Models\Models\Buildings\Residential House 02\fbx\Residential House 02.fbx"),
    Path(r"D:\AIML\Projects\Major\MangaluruDigitalTwin3D\Assets\Models\Models\Buildings\Residential House 09\fbx\Residential House 09.fbx"),
    Path(r"D:\AIML\Projects\Major\MangaluruDigitalTwin3D\Assets\Models\Models\Buildings\175 Bloor St W\fbx\175 Bloor St W (version 2.0).fbx"),
    Path(r"D:\AIML\Projects\Major\MangaluruDigitalTwin3D\Assets\Models\Models\Buildings\594 Bloor St E\fbx\594 Bloor St E (version 2.0).fbx")
]

for m in models:
    find_details(m)
