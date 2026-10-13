import re

with open('MangaluruDigitalTwin3D/Assets/Models/Models/TrafficLights/Middle/MiddleTrafficLight.fbx', 'rb') as f:
    fbx = f.read()

matches = re.findall(b'Model: [0-9]+, "Model::([^"]+)", "([^"]+)"', fbx)
for m in matches:
    print(m[0].decode('latin1'), '->', m[1].decode('latin1'))

# Find geometric translation/rotation of nodes
for node in [b'MiddleTrafficLight', b'red_light', b'yellow_light', b'green_light']:
    idx = fbx.find(node)
    if idx != -1:
        snippet = fbx[idx:idx+400]
        # find Property70
        props = re.findall(b'P: "([^"]+)", "([^"]+)", [^,]*, [^,]*, (.*)', snippet)
        print(f"\nNode {node.decode('latin1')}:")
        for p in props[:5]:
            print(" ", p[0].decode('latin1'), p[1].decode('latin1'), p[2].decode('latin1'))
