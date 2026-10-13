import re

with open('MangaluruDigitalTwin3D/Assets/Models/Models/TrafficLights/Middle/MiddleTrafficLight.fbx', 'rb') as f:
    fbx = f.read()

# In binary FBX, connections are stored at the end of the file in Connections: { ... C: "OO", child_id, parent_id ... }
# Let's search for "OO" or Model IDs.
pos = fbx.find(b'Connections')
if pos != -1:
    conn_data = fbx[pos:]
    print("Found Connections block, length:", len(conn_data))
    # extract ASCII-like strings
    strings = re.findall(b'Model::([a-zA-Z0-9_-]+)', conn_data)
    print("Models referenced in connections:", set(s.decode('latin1') for s in strings))
else:
    print("Connections block not found directly as ASCII")

# Let's check objects in MiddleTrafficLight
for m in [b'MiddleTrafficLight', b'MiddleTrafficPost', b'red_light', b'yellow_light', b'green_light']:
    count = fbx.count(m)
    print(f"{m.decode('latin1')}: count={count}")
