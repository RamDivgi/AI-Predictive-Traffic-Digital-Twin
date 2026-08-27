import sumolib
import os

net_file = r"d:\AIML\Projects\AI-Predictive-Traffic\simulation\mangaluru\mangaluru_ai.net.xml.gz"

if not os.path.exists(net_file):
    print(f"Error: {net_file} not found")
    exit(1)

net = sumolib.net.readNet(net_file)

lat = 12.86640
lon = 74.85466

x, y = net.convertLonLat2XY(lon, lat)
print(f"SUMO X: {x}")
print(f"SUMO Y: {y}")
