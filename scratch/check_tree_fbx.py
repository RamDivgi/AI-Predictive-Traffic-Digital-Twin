import struct, zlib

def inspect_fbx(path):
    print("Inspecting:", path)
    with open(path, "rb") as f:
        data = f.read()
    
    # In binary FBX, find 'Vertices' property
    idx = 0
    while True:
        idx = data.find(b'Vertices', idx)
        if idx == -1: break
        # read header
        # In FBX 7.4 (64-bit int length/offsets) or 7.1-7.3 (32-bit)
        # Check version at offset 23
        ver = struct.unpack('<I', data[23:27])[0]
        print("FBX version:", ver)
        if ver >= 7500:
            end_offset, num_props, prop_list_len, name_len = struct.unpack('<QQQB', data[idx-25:idx])
        else:
            end_offset, num_props, prop_list_len, name_len = struct.unpack('<IIIB', data[idx-13:idx])
        
        # After 'Vertices' string: type code
        type_code = chr(data[idx+8])
        array_len = struct.unpack('<I', data[idx+9:idx+13])[0]
        encoding = struct.unpack('<I', data[idx+13:idx+17])[0]
        comp_len = struct.unpack('<I', data[idx+17:idx+21])[0]
        print(f"type_code={type_code}, array_len={array_len}, encoding={encoding}, comp_len={comp_len}")
        
        if encoding == 1:
            raw = zlib.decompress(data[idx+21:idx+21+comp_len])
        else:
            raw = data[idx+21:idx+21+array_len*8]
        
        floats = struct.unpack(f'<{array_len}d', raw)
        xs = floats[0::3]
        ys = floats[1::3]
        zs = floats[2::3]
        print(f"X: [{min(xs):.2f} .. {max(xs):.2f}], span={max(xs)-min(xs):.2f}")
        print(f"Y: [{min(ys):.2f} .. {max(ys):.2f}], span={max(ys)-min(ys):.2f}")
        print(f"Z: [{min(zs):.2f} .. {max(zs):.2f}], span={max(zs)-min(zs):.2f}")
        break

inspect_fbx("MangaluruDigitalTwin3D/Assets/Models/Models/Trees/Maple/Maple.fbx")
inspect_fbx("MangaluruDigitalTwin3D/Assets/Models/Models/Trees/Pine/Pine.fbx")
inspect_fbx("MangaluruDigitalTwin3D/Assets/Models/Models/Trees/Fir/Fir.fbx")
