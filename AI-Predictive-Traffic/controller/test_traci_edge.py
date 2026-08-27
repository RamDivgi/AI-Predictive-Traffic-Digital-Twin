import traci
print([m for m in dir(traci.edge) if not m.startswith('_')])
