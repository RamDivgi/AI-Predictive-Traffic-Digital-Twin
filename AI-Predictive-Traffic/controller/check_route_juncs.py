import sumolib

net_file = "d:/AIML/Projects/Major/AI-Predictive-Traffic/simulation/mangaluru/presentation_selection1.net.xml"
net = sumolib.net.readNet(net_file)

route = "1096889856 -1096889856 -184750315#1 -184750315#0 1055574152#1 1055574152#2 26182678#1 26182678#2 26182678#3 26299204#0 903009071#4"
edges = route.split()

print("Junctions on route:")
for i in range(len(edges)-1):
    edge1 = net.getEdge(edges[i])
    edge2 = net.getEdge(edges[i+1])
    junc = edge1.getToNode()
    print(f"Junction: {junc.getID()} - Type: {junc.getType()}")
    if junc.getType() == "traffic_light":
        print("  -> TRAFFIC LIGHT JUNCTION!")

