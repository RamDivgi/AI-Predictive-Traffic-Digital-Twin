import sumolib

net_file = "d:/AIML/Projects/Major/AI-Predictive-Traffic/simulation/mangaluru/presentation_selection1.net.xml"
net = sumolib.net.readNet(net_file)

start_edge_id = "1096889856"
end_edge_id = "903009071#4"

if net.hasEdge(start_edge_id) and net.hasEdge(end_edge_id):
    start_edge = net.getEdge(start_edge_id)
    end_edge = net.getEdge(end_edge_id)
    path = net.getShortestPath(start_edge, end_edge)
    if path:
        edges, cost = path
        print("Found valid route in presentation_selection1.net.xml:")
        print(" ".join([e.getID() for e in edges]))
    else:
        print(f"No route found between {start_edge_id} and {end_edge_id} in presentation_selection1.net.xml")
else:
    print("Start or end edge missing in presentation_selection1.net.xml")
