import os
import sumolib

net_file = "D:/AIML/Projects/Major/AI-Predictive-Traffic/simulation/mangaluru/mangaluru_ai.net.xml.gz"
net = sumolib.net.readNet(net_file)

route = "1096889856 -1096889856 184750315#2 1042171956 1366470615#1 1366470615#2 1042171954#0 1042171954#1 1042171954#2 1080446743#0 355391676#0 355391676#1 355391676#2 -355391671#0 184750308#17 184750308#18 184750308#19 184750308#20 1538932913#5 903009071#4"

xs = []
ys = []

for edge_id in route.split():
    if not net.hasEdge(edge_id): continue
    edge = net.getEdge(edge_id)
    shape = edge.getShape()
    for x, y in shape:
        xs.append(x)
        ys.append(y)

min_x, max_x = min(xs), max(xs)
min_y, max_y = min(ys), max(ys)

print(f"Bounding box: {min_x}, {min_y}, {max_x}, {max_y}")
print(f"Center: {(min_x + max_x) / 2}, {(min_y + max_y) / 2}")
print(f"Width: {max_x - min_x}, Height: {max_y - min_y}")

