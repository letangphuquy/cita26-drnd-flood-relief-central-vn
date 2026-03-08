import json
import argparse
import sys
import math
import time
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
    
    # Tight Big-M for flows
    tot_cap = sum(K_hub)

    # 1. Variables
    x = {}  # x_k: planned hub
    q = {}  # q_k: inventory
    for ki in range(num_H):
        x[ki] = solver.IntVar(0, 1, f'x_{ki}')
        q[ki] = solver.NumVar(0, K_hub[ki], f'q_{ki}')
        solver.Add(q[ki] <= K_hub[ki] * x[ki])
        
    y = {}  # y_ks: reactive hub
    z_iks = {} # z_iks_m [ii, ki, m, si]
    z_jks = {} # z_jks_m [ji, ki, m, si]
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
                for m in range(num_M):
                    z_iks[ii, ki, m, si] = solver.IntVar(0, 1, f'z_i{ii}_k{ki}_m{m}_s{si}')
            for ji in range(num_J):
                for m in range(num_M):
                    z_jks[ji, ki, m, si] = solver.IntVar(0, 1, f'z_j{ji}_k{ki}_m{m}_s{si}')
            for hi in range(num_H):
                for m in range(num_M):
                    f_khms[ki, hi, m, si] = solver.NumVar(0, tot_cap, f'f_{ki}_{hi}_{m}_{si}')
                    w_trans[ki, hi, m, si] = solver.IntVar(0, 1, f'w_trans_{ki}_{hi}_{m}_{si}')
        for ii in range(num_I):
            u_is[ii, si] = solver.NumVar(0, solver.infinity(), f'u_{ii}_{si}')
        for ji in range(num_J):
            v_js[ji, si] = solver.NumVar(0, solver.infinity(), f'v_{ji}_{si}')

        
    # Scenario-dependent operational status of planned hubs
    x_act = {}
    for si in range(num_S):
        sc = inst["scenarios"][si]
        for ki in range(num_H):
            x_act[ki, si] = solver.IntVar(0, 1, f'x_act_{ki}_{si}')
            # Hub only active in scenario if it was built
            solver.Add(x_act[ki, si] <= x[ki])
            # Hub inactive if risk exceeds threshold
            k_node = inst["nodes"]["hub_indices"][ki]
            if sc["risk"][k_node] > chi:
                solver.Add(x_act[ki, si] == 0)

    # 2. Constraints
    for si, sc in enumerate(inst["scenarios"]):
        for ki in range(num_H):
            k_node = inst["nodes"]["hub_indices"][ki]
            # Hub mutually exclusive in scenario: built hub (active or not) vs reactive hub
            solver.Add(x[ki] + y[ki, si] <= 1)
            # (Note: Risk constraint for x already handled by x_act)
            # Risk constraint for reactive hub
            risk_k = sc["risk"][k_node]
            solver.Add(risk_k * y[ki, si] <= chi)
            
        for ii in range(num_I):
            i_node = inst["nodes"]["demand_indices"][ii]
            demand_i = float(sc["demand"][str(i_node)])
            if demand_i > 1e-6:
                # Total assignment to hubs + slack == 1
                solver.Add(sum(z_iks[ii, ki, m, si] for ki in range(num_H) for m in range(num_M)) + u_is[ii, si] == 1)
                for ki in range(num_H):
                    # assignment only if hub is active (planned or reactive)
                    solver.Add(sum(z_iks[ii, ki, m, si] for m in range(num_M)) <= x_act[ki, si] + y[ki, si])
                    # assignment only if mode is accessible
                    for m in range(num_M):
                        solver.Add(z_iks[ii, ki, m, si] <= sc["accessibility"][m][inst["nodes"]["hub_indices"][ki]][i_node])
                
                # Big-M Z2: W_s >= sum_ki (C_dep_i_ki_s * z_i_ki_s) + penalty
                # where C_dep is based on the FASTEST accessible mode for that hub.
                # Numerical stability: cap expm1 scale at 1e5 (demand multiplier still applies)
                penalty = demand_i * min(math.expm1(20.0), 1e5)
                z2_expr = u_is[ii, si] * penalty
                
                lam_is = inst["lambda"][f"{i_node}_{si}"]
                for ki in range(num_H):
                    k_node = inst["nodes"]["hub_indices"][ki]
                    # Find min_t among accessible modes for (i, k) in scenario s
                    min_t = 1e30
                    any_acc = False
                    for m in range(num_M):
                        if sc["accessibility"][m][k_node][i_node]:
                            min_t = min(min_t, inst["transport"]["time"][m][k_node][i_node])
                            any_acc = True
                    
                    if any_acc:
                        omega_fastest = sc["hub_process_time"][str(k_node)] + 2.0 * min_t
                        c_dep_fastest = demand_i * math.expm1(min(lam_is * omega_fastest, 20.0))
                        
                        # Apply to the decision of assigning i to k (sum over all modes)
                        z_ik_total = solver.Sum(z_iks[ii, ki, m, si] for m in range(num_M))
                        z2_expr += c_dep_fastest * z_ik_total
                
                solver.Add(z2_max_s[si] >= z2_expr)
            else:
                solver.Add(u_is[ii, si] == 0)
                for ki in range(num_H):
                    for m in range(num_M):
                        solver.Add(z_iks[ii, ki, m, si] == 0)

        for ji in range(num_J):
            j_node = inst["nodes"]["origin_indices"][ji]
            supply_j = float(sc["supply"][str(j_node)])
            if supply_j > 1e-6:
                solver.Add(sum(z_jks[ji, ki, m, si] for ki in range(num_H) for m in range(num_M)) + v_js[ji, si] == 1)
                for ki in range(num_H):
                    k_node = inst["nodes"]["hub_indices"][ki]
                    solver.Add(sum(z_jks[ji, ki, m, si] for m in range(num_M)) <= x_act[ki, si] + y[ki, si])
                    for m in range(num_M):
                        solver.Add(z_jks[ji, ki, m, si] <= sc["accessibility"][m][j_node][k_node])
            else:
                solver.Add(v_js[ji, si] == 0)
                for ki in range(num_H):
                    for m in range(num_M):
                        solver.Add(z_jks[ji, ki, m, si] == 0)
                        
        for ki in range(num_H):
            k_node = inst["nodes"]["hub_indices"][ki]
            for hi in range(num_H):
                h_node = inst["nodes"]["hub_indices"][hi]
                for m in range(num_M):
                    solver.Add(f_khms[ki, hi, m, si] <= tot_cap * sc["accessibility"][m][k_node][h_node])
                    solver.Add(f_khms[ki, hi, m, si] <= tot_cap * w_trans[ki, hi, m, si])
            
            # Flow Balance & Capacity
            sum_demand = sum(gamma * float(sc["demand"][str(inst["nodes"]["demand_indices"][ii])]) * z_iks[ii, ki, m, si] \
                             for ii in range(num_I) for m in range(num_M))
            sum_supply = sum(float(sc["supply"][str(inst["nodes"]["origin_indices"][ji])]) * z_jks[ji, ki, m, si] \
                             for ji in range(num_J) for m in range(num_M))
            
            sum_trans_out = sum(f_khms[ki, hi, m, si] for hi in range(num_H) for m in range(num_M))
            sum_trans_in = sum(f_khms[hi, ki, m, si] for hi in range(num_H) for m in range(num_M))
            
            solver.Add(sum_demand + sum_trans_out <= q[ki] + sum_supply + sum_trans_in)
            solver.Add(q[ki] + sum_supply + sum_trans_in <= K_hub[ki] * (x_act[ki, si] + y[ki, si]))

        # Helicopter quota (Mode 2)
        total_links_s = (
            solver.Sum(z_iks[ii, ki, m, si] for ii in range(num_I) for ki in range(num_H) for m in range(num_M)) +
            solver.Sum(z_jks[ji, ki, m, si] for ji in range(num_J) for ki in range(num_H) for m in range(num_M)) +
            solver.Sum(w_trans[ki, hi, m, si] for ki in range(num_H) for hi in range(num_H) for m in range(num_M))
        )
        heli_links_s = (
            solver.Sum(z_iks[ii, ki, 2, si] for ii in range(num_I) for ki in range(num_H)) +
            solver.Sum(z_jks[ji, ki, 2, si] for ji in range(num_J) for ki in range(num_H)) +
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
            j_node = inst["nodes"]["origin_indices"][ji]
            supply_j = float(sc["supply"][str(j_node)])
            for ki in range(num_H):
                k_node = inst["nodes"]["hub_indices"][ki]
                for m in range(num_M):
                    if sc["accessibility"][m][j_node][k_node]:
                        c_jkm = inst["transport"]["cost"][m][j_node][k_node]
                        z1_expr += pi * (c_jkm * supply_j * z_jks[ji, ki, m, si])
                     
        # Transshipment Flow
        for ki in range(num_H):
            k_node = inst["nodes"]["hub_indices"][ki]
            for hi in range(num_H):
                h_node = inst["nodes"]["hub_indices"][hi]
                for m in range(num_M):
                    if sc["accessibility"][m][k_node][h_node]:
                        c_thm = inst["transport"]["cost"][m][k_node][h_node]
                        z1_expr += pi * (alpha * c_thm * f_khms[ki, hi, m, si])
                     
        # Last Mile (Theta)
        for ii in range(num_I):
            for ki in range(num_H):
                # theta[ki][ii][si] is loaded in build_and_solve_milp already
                z1_expr += pi * (inst["theta"][ki][ii][si] * sum(z_iks[ii, ki, m, si] for m in range(num_M)))
                 
    # Add penalty for slack variables to Z1
    for si, sc in enumerate(inst["scenarios"]):
        pi = sc["probability"]
        # Demand penalty: big_M per unassigned node
        z1_expr += pi * solver.Sum(u_is[ii, si] * big_M for ii in range(num_I))
        # Supply penalty: big_M per unassigned origin
        z1_expr += pi * solver.Sum(v_js[ji, si] * big_M for ji in range(num_J))

    z2_expr = solver.Sum(inst["scenarios"][si]["probability"] * z2_max_s[si] for si in range(num_S))
    
    # Weighted Sum Objective
    # If w1 is 0, we still want to minimize Z1's penalties (feasibility)
    solver.Minimize(max(w1, 1e-7) * z1_expr + w2 * z2_expr)
    
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
    parser.add_argument("--time_limit", type=int, default=600)
    args = parser.parse_args()

    inst = load_instance(args.instance)
    
    t_start = time.time()
    pareto = run_weighted_sum(inst, steps=args.steps, time_limit=args.time_limit)
    t_end = time.time()
    
    out_data = {
        "meta": {
            "solver": "MILP_WeightedSum",
            "elapsed_s": t_end - t_start
        },
        "pareto_front": pareto
    }
    
    with open(args.out, "w") as f:
        json.dump(out_data, f, indent=2)
        
    print(f"MILP Baseline finished. Found {len(pareto)} solutions. Saved to {args.out}")

if __name__ == "__main__":
    main()
