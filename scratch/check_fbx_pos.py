# Let's inspect the hierarchy in MiddleTrafficLight.fbx
with open('MangaluruDigitalTwin3D/Assets/Models/Models/TrafficLights/Middle/MiddleTrafficLight.fbx', 'rb') as f:
    fbx = f.read()

# Let's search for "red_light" in fbx
import re
# Find all occurrences of red_light, yellow_light, green_light, MiddleTrafficPost
for name in [b'red_light', b'yellow_light', b'green_light', b'MiddleTrafficPost', b'MiddleTrafficLight']:
    matches = [m.start() for m in re.finditer(re.escape(name), fbx)]
    print(f"{name.decode('latin1')}: found at positions {matches}")
