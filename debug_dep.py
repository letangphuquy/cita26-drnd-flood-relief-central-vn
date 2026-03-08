
import json
import math
import os

with open("data/cv/cv_small_drnd.json", "r") as f:
    inst = json.load(f)

for si, sc in enumerate(inst["scenarios"]):
    print(f"\nScenario {si} ({sc['name']}):")
    max_c_dep = 0
    min_c_dep = 1e30
    
    for ii, i_node in enumerate(inst["nodes"]["demand_indices"]):
        demand_i = sc["demand"][str(i_node)]
        lam_is = inst["lambda"][f"{i_node}_{si}"]
        
        for ki, k_node in enumerate(inst["nodes"]["hub_indices"]):
            hub_proc = sc["hub_process_time"][str(k_node)]
            
            # Use min_t among accessible modes
            min_t = 1e30
            any_acc = False
            for m in range(3):
                if sc["accessibility"][m][k_node][i_node]:
                    min_t = min(min_t, inst["transport"]["time"][m][k_node][i_node])
                    any_acc = True
            
            if not any_acc: continue
            
            omega = hub_proc + 2.0 * min_t
            c_dep = demand_i * math.expm1(min(lam_is * omega, 20.0))
            max_c_dep = max(max_c_dep, c_dep)
            min_c_dep = min(min_c_dep, c_dep)
    
    print(f"  Min c_dep: {min_c_dep:.2f}")
    print(f"  Max c_dep: {max_c_dep:.2e}")
    
    # Find one outlier
    print("  Outlier example (c_dep > 1e10):")
    for ii, i_node in enumerate(inst["nodes"]["demand_indices"]):
        demand_i = sc["demand"][str(i_node)]
        lam_is = inst["lambda"][f"{i_node}_{si}"]
        for ki, k_node in enumerate(inst["nodes"]["hub_indices"]):
            hub_proc = sc["hub_process_time"][str(k_node)]
            for m in range(3):
                if sc["accessibility"][m][k_node][i_node]:
                    t_kim = inst["transport"]["time"][m][k_node][i_node]
                    omega = hub_proc + 2.0 * t_kim
                    val = lam_is * omega
                    c_dep = demand_i * math.expm1(min(val, 20.0))
                    if c_dep > 1e10:
                        print(f"    Link i={i_node}, k={k_node}, m={m}: demand={demand_i:.1f}, lam={lam_is:.2f}, hub_proc={hub_proc:.2f}, t_kim={t_kim:.2f} -> val={val:.2f}, c_dep={c_dep:.2e}")
                        break
            else: continue
            break
