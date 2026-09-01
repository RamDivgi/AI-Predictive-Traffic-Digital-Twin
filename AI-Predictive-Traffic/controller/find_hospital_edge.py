import sumolib
from pathlib import Path

MANGALURU_NET = "d:/AIML/Projects/Major/AI-Predictive-Traffic/simulation/mangaluru/mangaluru_ai.net.xml.gz"

net = sumolib.net.readNet(MANGALURU_NET)

hx, hy = 1687.4691396001144, 1134.9806500039995

nearest_edges = net.getNeighboringEdges(hx, hy, r=100.0)
suitable = [(edge, dist) for edge, dist in nearest_edges if edge.allows("passenger")]
suitable.sort(key=lambda item: item[1])

print(f"Nearest edges to Highland Hospital (hx={hx}, hy={hy}):")
for edge, dist in suitable[:5]:
    print(f"Edge: {edge.getID()}, Distance: {dist:.2f}m")

# Current destination edge
dest = net.getEdge("903009071#4")
shape = dest.getShape()
print(f"\nCurrent dest edge shape: {shape}")
