import sumolib

net_file = "d:/AIML/Projects/Major/AI-Predictive-Traffic/simulation/mangaluru/presentation_selection2.net.xml"
try:
    net = sumolib.net.readNet(net_file)
    amb_route = "1096889856 -1096889856 184750315#2 1042171956 1366470615#1 1366470615#2 1042171954#0 1042171954#1 1042171954#2 1080446743#0 355391676#0 355391676#1 355391676#2 -355391671#0 184750308#17 184750308#18 184750308#19 184750308#20 1538932913#5 903009071#4"
    missing = []
    for e in amb_route.split():
        if not net.hasEdge(e):
            missing.append(e)
    
    print(f"Checking presentation_selection2.net.xml")
    print(f"Missing {len(missing)} edges from original amb_route: {missing}")
except Exception as e:
    print(e)
