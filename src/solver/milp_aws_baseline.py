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

def build_and_solve_milp(inst, w1=1.0, w2=0.0, eps_z1=None, eps_z2=None, 
                         limit_z1=None, limit_z2=None, time_limit_s=600):
    """
    Builds and solves the MO-IHLNDP MILP.
    Includes weights and optional objective limits (inequality constraints) for AWS.
    """
    solver = pywraplp.Solver.CreateSolver('SCIP')
    if not solver:
        return None
    solver.SetTimeLimit(int(time_limit_s * 1000))

    dims = inst["dimensions"]
    num_H, num_I, num_S, num_J, num_M = dims["num_H"], dims["num_I"], dims["num_S"], dims["num_J"], dims["num_M"]
    
    global_p = inst["global_params"]
    chi, gamma, alpha, Phi, eta = global_p["chi"], global_p["gamma"], global_p["alpha"], global_p["daganzo_phi"], global_p["daganzo_eta"]
    big_M = global_p.get("big_M", 1e7)

    hub_p = inst["hub_params"]
    F_hub = [hub_p["fixed_cost"][str(k)] for k in inst["nodes"]["hub_indices"]]
    C_hub = [hub_p["hold_cost"][str(k)] for k in inst["nodes"]["hub_indices"]]
    K_hub = [hub_p["capacity"][str(k)] for k in inst["nodes"]["hub_indices"]]
    tot_cap = sum(K_hub)

    # Variables
    x = {ki: solver.IntVar(0, 1, f'x_{ki}') for ki in range(num_H)}
    q = {ki: solver.NumVar(0, K_hub[ki], f'q_{ki}') for ki in range(num_H)}
    y = {}
    z_iks = {}
    z_jks = {}
    f_khms = {}
    w_trans = {}
    u_is = {}
    v_js = {}
    z2_max_s = {}
    x_act = {}

    for ki in range(num_H):
        solver.Add(q[ki] <= K_hub[ki] * x[ki])

    for si in range(num_S):
        sc = inst["scenarios"][si]
        z2_max_s[si] = solver.NumVar(0, solver.infinity(), f'W_{si}')
        for ki in range(num_H):
            k_node = inst["nodes"]["hub_indices"][ki]
            y[ki, si] = solver.IntVar(0, 1, f'y_{ki}_{si}')
            x_act[ki, si] = solver.IntVar(0, 1, f'x_act_{ki}_{si}')
            # Match C++ decoder: A hub is "active" if it was built AND (it's safe OR it's the least-risky fallback)
            min_risk_s = min(inst["scenarios"][si]["risk"][inst["nodes"]["hub_indices"][h]] for h in range(num_H))
            is_safe_or_best = (sc["risk"][k_node] <= chi or sc["risk"][k_node] <= min_risk_s + 1e-7)
            if not is_safe_or_best:
                solver.Add(x_act[ki, si] == 0)
            else:
                solver.Add(x_act[ki, si] <= x[ki])

            if sc["risk"][k_node] > chi:
                # If definitely risky, it can't be a reactive hub (matching C++ decoder's y[ki] check)
                solver.Add(y[ki, si] == 0)

            for ii in range(num_I):
                z_iks[ii, ki, si] = solver.IntVar(0, 1, f'z_i{ii}_k{ki}_s{si}')
            for ji in range(num_J):
                z_jks[ji, ki, si] = solver.IntVar(0, 1, f'z_j{ji}_k{ki}_s{si}')
            for hi in range(num_H):
                for m in range(num_M):
                    f_khms[ki, hi, m, si] = solver.NumVar(0, tot_cap, f'f_k{ki}h{hi}m{m}s{si}')
                    w_trans[ki, hi, m, si] = solver.IntVar(0, 1, f'w_k{ki}h{hi}m{m}s{si}')
                    solver.Add(f_khms[ki, hi, m, si] <= tot_cap * sc["accessibility"][m][k_node][inst["nodes"]["hub_indices"][hi]])
                    solver.Add(f_khms[ki, hi, m, si] <= tot_cap * w_trans[ki, hi, m, si])

        for ii in range(num_I):
            u_is[ii, si] = solver.NumVar(0, solver.infinity(), f'u_{ii}_{si}')
            i_node = inst["nodes"]["demand_indices"][ii]
            if sc["demand"][str(i_node)] > 1e-6:
                solver.Add(sum(z_iks[ii, ki, si] for ki in range(num_H)) + u_is[ii, si] == 1)
                for ki in range(num_H):
                    solver.Add(z_iks[ii, ki, si] <= x_act[ki, si] + y[ki, si])
                    acc_sum = sum(sc["accessibility"][m][inst["nodes"]["hub_indices"][ki]][i_node] for m in range(num_M))
                    solver.Add(z_iks[ii, ki, si] <= acc_sum)
            else:
                solver.Add(u_is[ii, si] == 0)
                for ki in range(num_H): solver.Add(z_iks[ii, ki, si] == 0)

        for ji in range(num_J):
            v_js[ji, si] = solver.NumVar(0, solver.infinity(), f'v_{ji}_{si}')
            j_node = inst["nodes"]["origin_indices"][ji]
            if sc["supply"][str(j_node)] > 1e-6:
                solver.Add(sum(z_jks[ji, ki, si] for ki in range(num_H)) + v_js[ji, si] == 1)
                for ki in range(num_H):
                    solver.Add(z_jks[ji, ki, si] <= x_act[ki, si] + y[ki, si])
                    acc_sum = sum(sc["accessibility"][m][j_node][inst["nodes"]["hub_indices"][ki]] for m in range(num_M))
                    solver.Add(z_jks[ji, ki, si] <= acc_sum)
            else:
                solver.Add(v_js[ji, si] == 0)
                for ki in range(num_H): solver.Add(z_jks[ji, ki, si] == 0)

        for ki in range(num_H):
            k_node = inst["nodes"]["hub_indices"][ki]
            inventory_s = q[ki]
            
            # (C11) Demand sum must be converted via gamma
            sum_demand_items = sum(z_iks[ii, ki, si] * float(sc["demand"][str(inst["nodes"]["demand_indices"][ii])]) * gamma for ii in range(num_I))
            sum_supply_items = sum(z_jks[ji, ki, si] * float(sc["supply"][str(inst["nodes"]["origin_indices"][ji])]) for ji in range(num_J))
            sum_trans_in     = sum(f_khms[hi, ki, m, si] for hi in range(num_H) for m in range(num_M))
            sum_trans_out    = sum(f_khms[ki, hi, m, si] for hi in range(num_H) for m in range(num_M))

            solver.Add(
                inventory_s + sum_supply_items + sum_trans_in >= sum_demand_items + sum_trans_out
            )
            solver.Add(y[ki, si] + x_act[ki, si] <= 1)

        # Mode 2 Quota
        h_i = sum(z_iks[ii, ki, si] for ii in range(num_I) for ki in range(num_H) if sc["accessibility"][2][inst["nodes"]["hub_indices"][ki]][inst["nodes"]["demand_indices"][ii]] and not any(sc["accessibility"][m2][inst["nodes"]["hub_indices"][ki]][inst["nodes"]["demand_indices"][ii]] for m2 in range(num_M) if m2 != 2))
        h_j = sum(z_jks[ji, ki, si] for ji in range(num_J) for ki in range(num_H) if sc["accessibility"][2][inst["nodes"]["origin_indices"][ji]][inst["nodes"]["hub_indices"][ki]] and not any(sc["accessibility"][m2][inst["nodes"]["origin_indices"][ji]][inst["nodes"]["hub_indices"][ki]] for m2 in range(num_M) if m2 != 2))
        h_t = sum(w_trans[ki, hi, 2, si] for ki in range(num_H) for hi in range(num_H))
        tot_l = sum(z_iks[ii, ki, si] for ii in range(num_I) for ki in range(num_H)) + sum(z_jks[ji, ki, si] for ji in range(num_J) for ki in range(num_H)) + sum(w_trans[ki, hi, m, si] for ki in range(num_H) for hi in range(num_H) for m in range(num_M))
        solver.Add(h_i + h_j + h_t <= 0.15 * tot_l + 0.999)

        # Z2 Bounds
        for ii in range(num_I):
            i_node = inst["nodes"]["demand_indices"][ii]
            if float(sc["demand"][str(i_node)]) <= 1e-6: continue
            lam_is = inst["lambda"][f"{i_node}_{si}"]
            penalty = float(sc["demand"][str(i_node)]) * math.expm1(min(lam_is * 24.0, 20.0))
            solver.Add(z2_max_s[si] >= u_is[ii, si] * penalty)
            for ki in range(num_H):
                k_node = inst["nodes"]["hub_indices"][ki]
                min_t = min((inst["transport"]["time"][m][k_node][i_node] for m in range(num_M) if sc["accessibility"][m][k_node][i_node]), default=None)
                if min_t is not None:
                    c_dep = float(sc["demand"][str(i_node)]) * math.expm1(min(lam_is * (sc["hub_process_time"][str(k_node)] + 2.0 * min_t), 20.0))
                    solver.Add(z2_max_s[si] >= c_dep * z_iks[ii, ki, si])

    # Obj Z1
    z1_expr = sum(F_hub[ki] * x[ki] + C_hub[ki] * q[ki] for ki in range(num_H))
    for si, sc in enumerate(inst["scenarios"]):
        pi = sc["probability"]
        z1_expr += pi * sum(sc["hub_reactive_cost"][str(inst["nodes"]["hub_indices"][ki])] * y[ki, si] for ki in range(num_H))
        for ji in range(num_J):
            j_node = inst["nodes"]["origin_indices"][ji]
            for ki in range(num_H):
                k_node = inst["nodes"]["hub_indices"][ki]
                min_c = min((inst["transport"]["cost"][m][j_node][k_node] for m in range(num_M) if sc["accessibility"][m][j_node][k_node]), default=None)
                if min_c is not None: z1_expr += pi * min_c * float(sc["supply"][str(j_node)]) * z_jks[ji, ki, si]
        for ki in range(num_H):
            for hi in range(num_H):
                for m in range(num_M):
                    if sc["accessibility"][m][inst["nodes"]["hub_indices"][ki]][inst["nodes"]["hub_indices"][hi]]:
                        z1_expr += pi * alpha * inst["transport"]["cost"][m][inst["nodes"]["hub_indices"][ki]][inst["nodes"]["hub_indices"][hi]] * f_khms[ki, hi, m, si]
        for ii in range(num_I):
            for ki in range(num_H):
                z1_expr += pi * inst["theta"][ki][ii][si] * z_iks[ii, ki, si]
        z1_expr += pi * sum(u_is[ii, si] * big_M for ii in range(num_I))
        z1_expr += pi * sum(v_js[ji, si] * big_M for ji in range(num_J))

    z2_expr = sum(inst["scenarios"][si]["probability"] * z2_max_s[si] for si in range(num_S))

    # AWS Specific Constraints: limits on objectives
    if limit_z1 is not None:
        solver.Add(z1_expr <= limit_z1)
    if limit_z2 is not None:
        solver.Add(z2_expr <= limit_z2)

    if eps_z2 is not None:
        solver.Add(z2_expr <= eps_z2)
        solver.Minimize(z1_expr)
    elif eps_z1 is not None:
        solver.Add(z1_expr <= eps_z1)
        solver.Minimize(z2_expr)
    else:
        solver.Minimize(w1 * z1_expr + w2 * z2_expr)

    status = solver.Solve()
    if status in [pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE]:
        return {
            "status": "OPTIMAL" if status == pywraplp.Solver.OPTIMAL else "FEASIBLE",
            "Z1": z1_expr.solution_value(), "Z2": z2_expr.solution_value(),
            "X": [int(x[ki].solution_value() > 0.5) for ki in range(num_H)],
            "R": [q[ki].solution_value() / K_hub[ki] if K_hub[ki] > 0 else 0.0 for ki in range(num_H)],
            "CV": sum(u_is[ii, si].solution_value() for ii in range(num_I) for si in range(num_S)) + sum(v_js[ji, si].solution_value() for ji in range(num_J) for si in range(num_S))
        }
    return {"status": "INFEASIBLE"}

def run_aws(inst, n_initial=5, delta_j_target=0.1, C=1.5, time_limit=600):
    """
    AWS Algorithm implementation following Step 1-8 of the paper.
    """
    print("Step 1: Calculating Anchor Points and Normalization Factors")
    p1 = build_and_solve_milp(inst, w1=1.0, w2=0.0, time_limit_s=time_limit) # Min Z1
    if not p1 or p1["status"] == "INFEASIBLE": return []
    # Lexicographic for p1 (Min Z2 given Min Z1)
    p1 = build_and_solve_milp(inst, eps_z1=p1["Z1"]+1e-4, w1=0.0, w2=1.0, time_limit_s=time_limit)
    
    p2 = build_and_solve_milp(inst, w1=0.0, w2=1.0, time_limit_s=time_limit) # Min Z2
    if not p2 or p2["status"] == "INFEASIBLE": return [p1]
    # Lexicographic for p2 (Min Z1 given Min Z2)
    p2 = build_and_solve_milp(inst, eps_z2=p2["Z2"]+1e-4, w1=1.0, w2=0.0, time_limit_s=time_limit)

    z1_min, z1_max = p1["Z1"], p2["Z1"]
    z2_min, z2_max = p2["Z2"], p1["Z2"]
    
    # Scale factors (sf) for Step 1
    # Paper uses sf_i0 = J_i_max - J_i_min (normalization)
    sf1 = max(z1_max - z1_min, 1e-6)
    sf2 = max(z2_max - z2_min, 1e-6)

    def normalize(z1, z2):
        return (z1 - z1_min) / sf1, (z2 - z2_min) / sf2

    print(f"Anchor P1: ({p1['Z1']}, {p1['Z2']}), Anchor P2: ({p2['Z1']}, {p2['Z2']})")

    # Step 2: Initial coarse representation
    print(f"Step 2: Initial Coarse Front (n={n_initial})")
    front = [p1, p2]
    for i in range(1, n_initial):
        w1 = i / n_initial
        w2 = 1.0 - w1
        # Use normalized weights
        sol = build_and_solve_milp(inst, w1=w1/sf1, w2=w2/sf2, time_limit_s=time_limit)
        if sol and sol["status"] != "INFEASIBLE": front.append(sol)
    
    # Front management: unique, non-dominated, and sorted by Z1
    def update_front(pts):
        pts = sorted(pts, key=lambda x: x["Z1"])
        unique = []
        for p in pts:
            if not unique or (abs(p["Z1"] - unique[-1]["Z1"]) > 1e-3 or abs(p["Z2"] - unique[-1]["Z2"]) > 1e-3):
                unique.append(p)
        filtered = []
        for i, s1 in enumerate(unique):
            dominated = False
            for j, s2 in enumerate(unique):
                if i == j: continue
                if s2["Z1"] <= s1["Z1"] + 1e-5 and s2["Z2"] <= s1["Z2"] + 1e-5:
                    if s2["Z1"] < s1["Z1"] - 1e-5 or s2["Z2"] < s1["Z2"] - 1e-5:
                        dominated = True; break
            if not dominated: filtered.append(s1)
        return filtered

    front = update_front(front)

    # Step 4-8: Iterative Refinement
    iteration = 0
    while iteration < 5: # Safety cap on iterations
        iteration += 1
        print(f"AWS Iteration {iteration}, Current Front Size: {len(front)}")
        
        segments = []
        total_len = 0
        for i in range(len(front) - 1):
            nz1_a, nz2_a = normalize(front[i]["Z1"], front[i]["Z2"])
            nz1_b, nz2_b = normalize(front[i+1]["Z1"], front[i+1]["Z2"])
            dist = math.sqrt((nz1_a - nz1_b)**2 + (nz2_a - nz2_b)**2)
            segments.append({'p_a': front[i], 'p_b': front[i+1], 'dist': dist})
            total_len += dist
        
        if not segments: break
        l_avg = total_len / len(segments)
        
        # Step 8 termination
        if all(s['dist'] <= delta_j_target for s in segments):
            print("Termination criteria met (all segments < delta_j).")
            break
            
        new_solutions = []
        for s in segments:
            # Step 4-5
            ni = round(C * (s['dist'] / l_avg))
            if ni <= 1: continue
            
            # Step 6: Offset distances
            # Angle theta
            p1_x, p1_y = normalize(s['p_a']["Z1"], s['p_a']["Z2"])
            p2_x, p2_y = normalize(s['p_b']["Z1"], s['p_b']["Z2"])
            
            # Paper uses vertical offset for delta_2 and horizontal for delta_1
            # tan(theta) = -(P1y - P2y)/(P1x - P2x)
            theta = math.atan2(-(p1_y - p2_y), (p1_x - p2_x))
            d1_norm = delta_j_target * math.cos(theta)
            d2_norm = delta_j_target * math.sin(theta)
            
            # Denormalize offsets
            d1 = d1_norm * sf1
            d2 = d2_norm * sf2
            
            # Step 7: Sub-optimization with box constraints
            # Z1 <= P1x - d1, Z2 <= P2y - d2
            # Note: P1 is left point (lower Z1), P2 is right point (lower Z2)
            for j in range(1, ni):
                # Adaptive weights perpendicular to the segment
                # vector (P2x-P1x, P2y-P1y), perp is (-(P2y-P1y), P2x-P1x)
                w1_adaptive = -(p2_y - p1_y) / sf1
                w2_adaptive = (p2_x - p1_x) / sf2
                
                sol = build_and_solve_milp(inst, w1=w1_adaptive, w2=w2_adaptive, 
                                           limit_z1=s['p_b']["Z1"] - d1,
                                           limit_z2=s['p_a']["Z2"] - d2,
                                           time_limit_s=time_limit)
                if sol and sol["status"] != "INFEASIBLE":
                    new_solutions.append(sol)
        
        if not new_solutions:
            print("No new solutions found in this iteration.")
            break
        
        front = update_front(front + new_solutions)
        
    return front

def main():
    parser = argparse.ArgumentParser(description="MILP AWS Baseline: MO-IHLNDP Adaptive Weighted-Sum solver.")
    parser.add_argument("--instance", required=True, help="Path to the JSON instance file.")
    parser.add_argument("--out", required=True, help="Path to save results JSON.")
    parser.add_argument("--n_initial", type=int, default=5, help="Number of initial divisions.")
    parser.add_argument("--delta_j", type=float, default=0.1, help="Target segment length (normalized).")
    parser.add_argument("--time_limit", type=int, default=300, help="Time limit per solve.")
    args = parser.parse_args()

    inst = load_instance(args.instance)
    t_start = time.time()
    pareto = run_aws(inst, n_initial=args.n_initial, delta_j_target=args.delta_j, time_limit=args.time_limit)
    t_total = time.time() - t_start

    out_data = {
        "meta": {
            "solver": "MILP_AWS_Baseline",
            "instance": args.instance,
            "total_elapsed_s": t_total,
            "n_initial": args.n_initial,
            "delta_j": args.delta_j
        },
        "pareto_front": pareto
    }

    with open(args.out, "w") as f:
        json.dump(out_data, f, indent=2)

    print(f"\nAWS Baseline finished. Solutions: {len(pareto)}, Time: {t_total:.2f}s")

if __name__ == "__main__":
    main()
