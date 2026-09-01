import sumolib

net_file = "d:/AIML/Projects/Major/AI-Predictive-Traffic/simulation/mangaluru/presentation_selection1.net.xml"
net = sumolib.net.readNet(net_file)

starts = ["1096889856", "-1096889856", "26182678#1"]
ends = ["903009071#1", "26206100#7", "26299204#2"]

for start_id in starts:
    for end_id in ends:
        if net.hasEdge(start_id) and net.hasEdge(end_id):
            start_edge = net.getEdge(start_id)
            end_edge = net.getEdge(end_id)
            path = net.getShortestPath(start_edge, end_edge)
            if path:
                edges, cost = path
                route_str = " ".join([e.getID() for e in edges])
                print(f"Route from {start_id} to {end_id}:")
                print(route_str)
                # check if there's a TLS on this path
                has_tls = False
                for i in range(len(edges)-1):
                    if edges[i].getToNode().getType() == "traffic_light":
                        has_tls = True
                        print(f"  -> Passes through TLS at {edges[i].getToNode().getID()}")
                if has_tls:
                    print("  --> VALID TLS ROUTE!")
