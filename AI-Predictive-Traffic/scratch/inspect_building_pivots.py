import struct
import zlib
from pathlib import Path

def inspect_model(name, fbx_path):
    print("=" * 60)
    print(f"[{name}] -> {fbx_path.name}")
    with open(fbx_path, 'rb') as f:
        data = f.read()
        
    pos = data.find(b'Vertices')
    if pos != -1:
        arr_idx = data.find(b'd', pos, pos+100)
        if arr_idx != -1:
            arr_len, enc, comp_len = struct.unpack('<III', data[arr_idx+1:arr_idx+13])
            raw = data[arr_idx+13:arr_idx+13+arr_len*8] if enc == 0 else zlib.decompress(data[arr_idx+13:arr_idx+13+comp_len])
            verts = struct.unpack(f'<{arr_len}d', raw)
            xs = [v/100.0 for v in verts[0::3]]
            ys = [v/100.0 for v in verts[1::3]]
            zs = [v/100.0 for v in verts[2::3]]
            min_x, max_x = min(xs), max(xs)
            min_y, max_y = min(ys), max(ys)
            min_z, max_z = min(zs), max(zs)
            print(f"  Width (X):  [{min_x:6.2f}, {max_x:6.2f}], span={max_x-min_x:5.2f}m, center={(min_x+max_x)/2:5.2f}m")
            print(f"  Height (Y): [{min_y:6.2f}, {max_y:6.2f}], span={max_y-min_y:5.2f}m, center={(min_y+max_y)/2:5.2f}m")
            print(f"  Depth (Z):  [{min_z:6.2f}, {max_z:6.2f}], span={max_z-min_z:5.2f}m, center={(min_z+max_z)/2:5.2f}m")
            
            # Let's inspect which direction has the front entrance or longest facade
            # For houses, the front door is typically at -Z or +Z.
            # Let's check aspect ratio of X vs Z
            if max_x - min_x > max_z - min_z:
                print(f"  Geometry: WIDE facade along X ({max_x-min_x:.1f}m wide x {max_z-min_z:.1f}m deep)")
            else:
                print(f"  Geometry: DEEP plot along Z ({max_x-min_x:.1f}m wide x {max_z-min_z:.1f}m deep)")

models = {
    "Bldg_Commercial01": r"D:\AIML\Projects\Major\MangaluruDigitalTwin3D\Assets\Models\Models\Buildings\Charlies Chow\fbx\Charlies Chow (Version 2.0).fbx",
    "Bldg_Commercial02": r"D:\AIML\Projects\Major\MangaluruDigitalTwin3D\Assets\Models\Models\Buildings\House of Antoine\House of Antoine.fbx",
    "Bldg_Commercial03": r"D:\AIML\Projects\Major\MangaluruDigitalTwin3D\Assets\Models\Models\Buildings\594 Bloor St E\fbx\594 Bloor St E (version 2.0).fbx",
    "Bldg_House01": r"D:\AIML\Projects\Major\MangaluruDigitalTwin3D\Assets\Models\Models\Buildings\Residential House 01\fbx\Residential House 01.fbx",
    "Bldg_House02": r"D:\AIML\Projects\Major\MangaluruDigitalTwin3D\Assets\Models\Models\Buildings\Residential House 02\fbx\Residential House 02.fbx",
    "Bldg_House05": r"D:\AIML\Projects\Major\MangaluruDigitalTwin3D\Assets\Models\Models\Buildings\Residential House 05\Residential House 05.fbx",
    "Bldg_House07": r"D:\AIML\Projects\Major\MangaluruDigitalTwin3D\Assets\Models\Models\Buildings\Residential House 09\fbx\Residential House 09.fbx",
    "Bldg_House11": r"D:\AIML\Projects\Major\MangaluruDigitalTwin3D\Assets\Models\Models\Buildings\Residential House 11\fbx\Residential House 11.fbx",
    "Bldg_Office01": r"D:\AIML\Projects\Major\MangaluruDigitalTwin3D\Assets\Models\Models\Buildings\721 Bloor St W, Whitby\fbx\721 Bloor St W (version 2.0).fbx",
    "Bldg_Office02": r"D:\AIML\Projects\Major\MangaluruDigitalTwin3D\Assets\Models\Models\Buildings\175 Bloor St W\fbx\175 Bloor St W (version 2.0).fbx"
}

for name, path_str in models.items():
    inspect_model(name, Path(path_str))
