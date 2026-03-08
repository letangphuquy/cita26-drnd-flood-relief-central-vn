import json
import argparse
import sys
import math
import numpy as np
from ortools.linear_solver import pywraplp

def load_instance(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def calc_theta_is_constant(D_is, A_i, kim, C_m, Q_m, Phi, eta):
    """Calculate the deterministic last-mile cost per assigning grid i to hub k via mode m in scenario s."""
    if D_is <= 1e-6:
        return 0.0
    line_haul = 2.0 * kim * math.ceil(D_is / Q_m)
    local_detour = C_m * Phi * math.sqrt(math.ceil(D_is / eta) * A_i)
    return line_haul + local_detour

def build_and_solve_milp(inst, w1=1.0, w2=0.0, eps_z1=None, eps_z2=None, time_limit_s=600):
    """
    Builds the MO-IHLNDP MILP using OR-Tools (SCIP).
    Minimizes Z = w1 * Z1 + w2 * Z2
    """
    solver = pywraplp.Solver.CreateSolver('SCIP')
    if not solver:
        print("SCIP solver not available.")
        return None
    
    solver.SetTimeLimit(time_limit_s * 1000)

    dims = inst["dimensions"]
    num_H = dims["num_H"]
    num_I = dims["num_I"]
    num_S = dims["num_S"]
    num_J = dims["num_J"]
    num_M = dims["num_M"]
    
    chi = inst["global_params"]["chi"]
    big_M = inst.get("big_M", 1e9)
    gamma = inst["global_params"]["gamma"]
    alpha = inst["global_params"]["alpha"]
    Phi = inst["global_params"]["daganzo_phi"]
    eta = inst["global_params"]["daganzo_eta"]

    F_hub = [inst["hub_params"]["fixed_cost"][str(k)] for k in inst["nodes"]["hub_indices"]]
    C_hub = [inst["hub_params"]["hold_cost"][str(k)] for k in inst["nodes"]["hub_indices"]]
    K_hub = [inst["hub_params"]["capacity"][str(k)] for k in inst["nodes"]["hub_indices"]]
    
    # 0. Pre-compute constant matrices
    theta_const = np.zeros((num_I, num_H, num_S))
    c_dep_iks = np.zeros((num_I, num_H, num_S))
    
    demand_is_m2 = np.zeros((num_I, num_H, num_S))
    orig_c_jks = np.full((num_J, num_H, num_S), big_M)
    orig_is_m2 = np.zeros((num_J, num_H, num_S))
    
    for si, sc in enumerate(inst["scenarios"]):
        for ii in range(num_I):
            i_node = inst["nodes"]["demand_indices"][ii]
            D_is = sc["demand"][str(i_node)]
            lam_is = inst["lambda"][f"{i_node}_{si}"]
            
            for ki in range(num_H):
                k_node = inst["nodes"]["hub_indices"][ki]
                best_cost = big_M
                best_time = big_M
                best_m = -1
                for m in range(num_M):
                    if sc["accessibility"][m][k_node][i_node]:
                        c_kim = inst["transport"]["cost"][m][k_node][i_node]
                        t_kim = inst["transport"]["time"][m][k_node][i_node]
                        if c_kim < best_cost: best_cost = c_kim
                        if t_kim < best_time:
                            best_time = t_kim
                            best_m = m
                
                # Theta for Z1 (pre-computed in instance, but we can verify or use inst["theta"])
                theta_const[ii, ki, si] = inst["theta"][ki][ii][si]
                
                # C_dep for Z2 (linearization parameter)
                if best_m != -1:
                    omega_is = sc["hub_process_time"][str(k_node)] + 2.0 * best_time
                    c_dep_iks[ii, ki, si] = D_is * math.expm1(min(lam_is * omega_is, 20.0))
                    if best_m == 2:
                        demand_is_m2[ii, ki, si] = 1
                else:
                    c_dep_iks[ii, ki, si] = D_is * math.expm1(20.0) # Maximum penalty
                        
        for ji in range(num_J):
            j_node = inst["nodes"]["origin_indices"][ji]
            for ki in range(num_H):
                k_node = inst["nodes"]["hub_indices"][ki]
                best_c = big_M
                best_m = -1
                for m in range(num_M):
                    if sc["accessibility"][m][j_node][k_node]:
                        if inst["transport"]["cost"][m][j_node][k_node] < best_c:
                            best_c = inst["transport"]["cost"][m][j_node][k_node]
                            best_m = m
                if best_m != -1:
                    orig_c_jks[ji, ki, si] = best_c
                    if best_m == 2:
                        orig_is_m2[ji, ki, si] = 1

    # Tight Big-M for flows
    tot_cap = sum(K_hub)

    # 1. Variables
    x = {}  # x_k: planned hub
    q = {}  # q_k: inventory
    for ki in range(num_H):
        x[ki] = solver.IntVar(0, 1, f'x_{ki}')
        q[ki] = solver.NumVar(0, K_hub[ki], f'q_{ki}')
        
    y = {}  # y_ks: reactive hub
    z_iks = {} # z_iks: demand i assigned to hub k in scenario s
    z_jks = {} # z_jks: origin j assigned to hub k in scenario s
    f_khms = {} # lateral transshipment
    w_trans = {} # binary indicator for transshipment mode active
    
    u_is = {} # Unassigned demand slack
    v_js = {} # Unassigned supply slack
    
    z2_max_s = {} # Max deprivation cost per scenario
    for si in range(num_S):
        z2_max_s[si] = solver.NumVar(0, solver.infinity(), f'z2_max_{si}')
        for ki in range(num_H):
            y[ki, si] = solver.IntVar(0, 1, f'y_{ki}_{si}')
            for ii in range(num_I):
                z_iks[ii, ki, si] = solver.IntVar(0, 1, f'z_i{ii}_k{ki}_s{si}')
            for ji in range(num_J):
                z_jks[ji, ki, si] = solver.IntVar(0, 1, f'z_j{ji}_k{ki}_s{si}')
            for hi in range(num_H):
                for m in range(num_M):
                    f_khms[ki, hi, m, si] = solver.NumVar(0, tot_cap, f'f_{ki}_{hi}_{m}_{si}')
                    w_trans[ki, hi, m, si] = solver.IntVar(0, 1, f'w_trans_{ki}_{hi}_{m}_{si}')
        for ii in range(num_I):
            u_is[ii, si] = solver.NumVar(0, solver.infinity(), f'u_{ii}_{si}')
        for ji in range(num_J):
            v_js[ji, si] = solver.NumVar(0, solver.infinity(), f'v_{ji}_{si}')

        
    # 2. Constraints
    for ki in range(num_H):
        # Inventory cap for planned hubs
        solver.Add(q[ki] <= K_hub[ki] * x[ki])
        for si, sc in enumerate(inst["scenarios"]):
            # Hub mutually exclusive in scenario
            solver.Add(x[ki] + y[ki, si] <= 1)
            # Safe zone constraint for ANY active hub
            risk_k = sc["risk"][inst["nodes"]["hub_indices"][ki]]
            solver.Add(risk_k * (x[ki] + y[ki, si]) <= chi)
            
        for ii in range(num_I):
            demand_i = sc["demand"][str(inst["nodes"]["demand_indices"][ii])]
            if demand_i > 1e-6:
                # Single allocation demand with slack
                solver.Add(sum(z_iks[ii, ki, si] for ki in range(num_H)) + u_is[ii, si] == 1)
                for ki in range(num_H):
                    solver.Add(z_iks[ii, ki, si] <= x[ki] + y[ki, si])
                    acc_sum = sum(sc["accessibility"][m][inst["nodes"]["hub_indices"][ki]][inst["nodes"]["demand_indices"][ii]] for m in range(num_M))
                    solver.Add(z_iks[ii, ki, si] <= acc_sum)
                
                # Rigorous Linearization: W_s >= sum_k (C_dep_iks * z_iks) + penalty for unassigned
                # Penalty for unassigned: D * exp(20)
                unassigned_penalty = demand_i * math.expm1(20.0)
                solver.Add(z2_max_s[si] >= sum(c_dep_iks[ii, ki, si] * z_iks[ii, ki, si] for ki in range(num_H)) + unassigned_penalty * u_is[ii, si])
            else:
                solver.Add(u_is[ii, si] == 0)
                for ki in range(num_H):
                    solver.Add(z_iks[ii, ki, si] == 0)

        for ji in range(num_J):
            supply_j = sc["supply"][str(inst["nodes"]["origin_indices"][ji])]
            if supply_j > 1e-6:
                # Origin allocation with slack
                # Changed to == 1 with slack to track unmet supply if disconnected
                solver.Add(sum(z_jks[ji, ki, si] for ki in range(num_H)) + v_js[ji, si] == 1)
                for ki in range(num_H):
                    solver.Add(z_jks[ji, ki, si] <= x[ki] + y[ki, si])
                    acc_sum = sum(sc["accessibility"][m][inst["nodes"]["origin_indices"][ji]][inst["nodes"]["hub_indices"][ki]] for m in range(num_M))
                    solver.Add(z_jks[ji, ki, si] <= acc_sum)
            else:
                 solver.Add(v_js[ji, si] == 0)
                 for ki in range(num_H):
                    solver.Add(z_jks[ji, ki, si] == 0)
                    
        for ki in range(num_H):
            k_node = inst["nodes"]["hub_indices"][ki]
            for hi in range(num_H):
                h_node = inst["nodes"]["hub_indices"][hi]
                # Bound flow by capacity and access
                for m in range(num_M):
                    solver.Add(f_khms[ki, hi, m, si] <= tot_cap * sc["accessibility"][m][k_node][h_node])
                    # Bound flow by binary activity indicator
                    solver.Add(f_khms[ki, hi, m, si] <= tot_cap * w_trans[ki, hi, m, si])
            
            # Flow Balance & Capacity
            i_demand_nodes = inst["nodes"]["demand_indices"]
            sum_demand = sum(gamma * float(sc["demand"][str(i_node)]) * z_iks[ii, ki, si] for ii, i_node in enumerate(i_demand_nodes))
            
            j_origin_nodes = inst["nodes"]["origin_indices"]
            sum_supply = sum(float(sc["supply"][str(j_node)]) * z_jks[ji, ki, si] for ji, j_node in enumerate(j_origin_nodes))
            
            sum_trans_out = sum(f_khms[ki, hi, m, si] for hi in range(num_H) for m in range(num_M))
            sum_trans_in = sum(f_khms[hi, ki, m, si] for hi in range(num_H) for m in range(num_M))
            
            # Flow Balance: Demand + OutFlow <= Inventory + Supply + InFlow
            solver.Add(sum_demand + sum_trans_out <= q[ki] + sum_supply + sum_trans_in)
            # Throughput Capacity: Inventory + Supply + InFlow <= kappa
            solver.Add(q[ki] + sum_supply + sum_trans_in <= K_hub[ki] * (x[ki] + y[ki, si]))

        # Helicopter link restriction (max 15%)
        # Calculate established links
        total_links_s = (
            solver.Sum(z_iks[ii, ki, si] for ii in range(num_I) for ki in range(num_H)) +
            solver.Sum(z_jks[ji, ki, si] for ji in range(num_J) for ki in range(num_H)) +
            solver.Sum(w_trans[ki, hi, m, si] for ki in range(num_H) for hi in range(num_H) for m in range(num_M))
        )
        heli_links_s = (
            solver.Sum(z_iks[ii, ki, si] * demand_is_m2[ii, ki, si] for ii in range(num_I) for ki in range(num_H)) +
            solver.Sum(z_jks[ji, ki, si] * orig_is_m2[ji, ki, si] for ji in range(num_J) for ki in range(num_H)) +
            solver.Sum(w_trans[ki, hi, 2, si] for ki in range(num_H) for hi in range(num_H))
        )
        solver.Add(heli_links_s <= 0.15 * total_links_s + 0.999)


    # 3. Objective Functions
    # Z1 
    z1_expr = solver.Sum(F_hub[ki] * x[ki] + C_hub[ki] * q[ki] for ki in range(num_H))
    
    for si, sc in enumerate(inst["scenarios"]):
        pi = sc["probability"]
        # Reactive setup
        z1_expr += pi * solver.Sum(sc["hub_reactive_cost"][str(inst["nodes"]["hub_indices"][ki])] * y[ki, si] for ki in range(num_H))
        
        # Origin to Hub
        for ji in range(num_J):
            for ki in range(num_H):
                c_jks = orig_c_jks[ji, ki, si]
                if c_jks < big_M:
                     j_node = inst["nodes"]["origin_indices"][ji]
                     z1_expr += pi * (c_jks * float(sc["supply"][str(j_node)]) * z_jks[ji, ki, si])
                     
        # Transshipment Flow
        for ki in range(num_H):
            k_node = inst["nodes"]["hub_indices"][ki]
            for hi in range(num_H):
                h_node = inst["nodes"]["hub_indices"][hi]
                for m in range(num_M):
                    c_thm = inst["transport"]["cost"][m][k_node][h_node]
                    z1_expr += pi * (c_thm * alpha * f_khms[ki, hi, m, si])
                     
        # Last Mile
        for ki in range(num_H):
            for ii in range(num_I):
                 z1_expr += pi * (theta_const[ii, ki, si] * z_iks[ii, ki, si])
                 
    # Add penalty for slack variables to Z1
    for si, sc in enumerate(inst["scenarios"]):
        pi = sc["probability"]
        # Demand penalty: big_M per unassigned node
        z1_expr += pi * solver.Sum(u_is[ii, si] * big_M for ii in range(num_I))
        # Supply penalty: small penalty or just tracking? Let's use big_M to enforce assignment if possible.
        z1_expr += pi * solver.Sum(v_js[ji, si] * big_M for ji in range(num_J))

    z2_expr = solver.Sum(inst["scenarios"][si]["probability"] * z2_max_s[si] for si in range(num_S))
    
    # Weighted Sum Objective
    solver.Minimize(w1 * z1_expr + w2 * z2_expr)
    
    # Epsilon Constraint fallback (for extremes if needed)
    if eps_z2 is not None:
        solver.Add(z2_expr <= eps_z2)
        solver.Minimize(z1_expr)
    elif eps_z1 is not None:
        solver.Add(z1_expr <= eps_z1)
        solver.Minimize(z2_expr)
        
    status = solver.Solve()
    
    if status == pywraplp.Solver.OPTIMAL or status == pywraplp.Solver.FEASIBLE:
        # Extract variables
        X_res = [int(x[ki].solution_value() > 0.5) for ki in range(num_H)]
        CV_val = sum(u_is[ii, si].solution_value() for ii in range(num_I) for si in range(num_S))
        CV_val += sum(v_js[ji, si].solution_value() for ji in range(num_J) for si in range(num_S))
        
        return {
            "status": "OPTIMAL" if status == pywraplp.Solver.OPTIMAL else "FEASIBLE",
            "Z1": z1_expr.solution_value(),
            "Z2": z2_expr.solution_value(),
            "X": X_res,
            "CV": CV_val,
            "A": [], "R": [q[ki].solution_value()/K_hub[ki] if K_hub[ki]>0 else 0 for ki in range(num_H)], "W": []
        }
    else:
        print(f"Solver status: {status}")
        return {"status": "INFEASIBLE"}

def run_weighted_sum(inst, steps=9, time_limit=600):
    """Run weighted-sum MILP. iterates through weight combinations."""
    front = []
    
    # Adjust steps to ensure we cover extremes
    if steps < 2: steps = 2
    
    for i in range(steps):
        # Weight for Z1
        w1 = (steps - 1 - i) / (steps - 1)
        # Weight for Z2
        w2 = 1.0 - w1
        
        print(f"Solving weighted-sum {i+1}/{steps}: w1={w1:.2f}, w2={w2:.2f}")
        sol = build_and_solve_milp(inst, w1=w1, w2=w2, time_limit_s=time_limit)
        
        if sol and sol["status"] != "INFEASIBLE":
            print(f"  Result: Z1={sol['Z1']:.2f}, Z2={sol['Z2']:.2f}, CV={sol['CV']:.2f}")
            front.append(sol)
        else:
            print(f"  Weighted-sum {i+1} failed or infeasible.")

    # Filter dominated solutions
    filtered = []
    for s1 in front:
        dom = any(
            s2["Z1"] <= s1["Z1"] and s2["Z2"] <= s1["Z2"]
            and (s2["Z1"] < s1["Z1"] or s2["Z2"] < s1["Z2"])
            for s2 in front
        )
        if not dom:
            filtered.append(s1)

    return filtered

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--instance", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--steps", type=int, default=5)
    args = parser.parse_args()

    inst = load_instance(args.instance)
    pareto = run_weighted_sum(inst, steps=args.steps, time_limit=300)
    
    out_data = {
        "meta": {"solver": "MILP_WeightedSum"},
        "pareto_front": pareto
    }
    
    with open(args.out, "w") as f:
        json.dump(out_data, f, indent=2)
        
    print(f"MILP Baseline finished. Found {len(pareto)} solutions. Saved to {args.out}")

if __name__ == "__main__":
    main()
