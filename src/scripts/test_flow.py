import json
from scripts.map_decoder import decode_exact

inst = json.load(open('data/cv/cv_large_drnd.json'))
sols = "results/exp2/CV_large_seed0.json"
try:
    with open(sols, 'r') as f:
        data = json.load(f)
        
    s = data['pareto'][0] if 'pareto' in data else data[0]

    print("Seed 0, Sol 0:")
    for si in range(3):
        res = decode_exact(s, inst, si)
        print(f"Scenario {si}:")
        print("  Transshipments:", res['transshipments'])
        print("  Reactive Hubs :", res['reactive_hubs'])
        print("  Inventory:", res['inventory'])
        print("  Hub Load :", res['hub_load'])
        net_inv = [res['inventory'][ki] - res['hub_load'][ki] for ki in range(inst['dimensions']['num_H'])]
        print("  Net Inv  :", net_inv)

except Exception as e:
    import traceback
    traceback.print_exc()
