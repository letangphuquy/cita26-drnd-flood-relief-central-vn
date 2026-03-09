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

    Decision variables follow the paper formulation exactly:
      x_k         : binary, planned hub establishment
      y_ks        : binary, reactive hub in scenario s
      z_iks       : binary, demand i assigned to hub k in scenario s  (NO mode dimension)
      z_jks       : binary, origin j supplies hub k in scenario s      (NO mode dimension)
      q_k         : continuous, inventory pre-positioned at hub k
      f_khms      : continuous, lateral transshipment flow k->h via mode m in scenario s
      w_trans_khms: binary, indicator that the transshipment arc k->h/m/s is used
      u_is, v_js  : continuous slack for unassigned demand/supply (penalized)
      W_s (z2_max_s): continuous, epigraph variable for max deprivation per scenario
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

    chi   = inst["global_params"]["chi"]
    # NOTE: big_M lives under global_params, not at root level
    big_M = inst["global_params"].get("big_M", 1e7)
    gamma = inst["global_params"]["gamma"]
    alpha = inst["global_params"]["alpha"]
    Phi   = inst["global_params"]["daganzo_phi"]
    eta   = inst["global_params"]["daganzo_eta"]

    F_hub = [inst["hub_params"]["fixed_cost"][str(k)] for k in inst["nodes"]["hub_indices"]]
    C_hub = [inst["hub_params"]["hold_cost"][str(k)]  for k in inst["nodes"]["hub_indices"]]
    K_hub = [inst["hub_params"]["capacity"][str(k)]   for k in inst["nodes"]["hub_indices"]]

    # Tight upper bound on flow variables
    tot_cap = sum(K_hub)

    # -------------------------------------------------------------------------
    # 1. Decision Variables
    # -------------------------------------------------------------------------
    x = {}  # x_k ∈ {0,1}: planned hub
    q = {}  # q_k >= 0   : pre-positioned inventory
    for ki in range(num_H):
        x[ki] = solver.IntVar(0, 1, f'x_{ki}')
        q[ki] = solver.NumVar(0, K_hub[ki], f'q_{ki}')
        # (C2) inventory only if hub is built: q_k <= kappa_k * x_k
        solver.Add(q[ki] <= K_hub[ki] * x[ki])

    y        = {}  # y_{k,s} ∈ {0,1}
    # z_iks  : demand i -> hub k in scenario s  (single variable, no mode index)
    z_iks    = {}
    # z_jks  : origin j -> hub k in scenario s  (single variable, no mode index)
    z_jks    = {}
    f_khms   = {}  # lateral transshipment flow
    w_trans  = {}  # binary arc-use indicator
    u_is     = {}  # unassigned demand slack
    v_js     = {}  # unassigned supply slack
    z2_max_s = {}  # W_s (epigraph for Z2)

    for si in range(num_S):
        z2_max_s[si] = solver.NumVar(0, solver.infinity(), f'W_{si}')
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

    # -------------------------------------------------------------------------
    # Scenario-dependent planned hub activation
    # x_act[k,s] = 1 iff hub k was built AND its risk <= chi in scenario s.
    # Implemented as a continuous variable in [0,1] tightened by two inequalities
    # rather than an integer var, to avoid branching overhead.
    # -------------------------------------------------------------------------
    x_act = {}
    for si in range(num_S):
        sc = inst["scenarios"][si]
        # Find the minimum risk among ALL hub candidates in this scenario
        min_risk_s = min(inst["scenarios"][si]["risk"][inst["nodes"]["hub_indices"][h]] for h in range(num_H))
        for ki in range(num_H):
            x_act[ki, si] = solver.IntVar(0, 1, f'x_act_{ki}_{si}')
            # (a) can only be active if hub was built
            # Match C++ decoder: A hub is "active" if it was built AND (it's safe OR it's the least-risky fallback)
            k_node = inst["nodes"]["hub_indices"][ki]
            
            # x_act[ki, si] = 1 iff (x[ki] == 1) AND (risk <= chi OR risk == min_risk_s)
            is_safe_or_best = (sc["risk"][k_node] <= chi or sc["risk"][k_node] <= min_risk_s + 1e-7)
            
            if not is_safe_or_best:
                solver.Add(x_act[ki, si] == 0)
            else:
                solver.Add(x_act[ki, si] <= x[ki])
                # Optimization: x_act can be 1 if x[ki] is 1 and it's safe/best. 
                # The solver will naturally want x_act=1 to use pre-positioned inventory.

    # -------------------------------------------------------------------------
    # 2. Constraints
    # -------------------------------------------------------------------------
    for si, sc in enumerate(inst["scenarios"]):
        for ki in range(num_H):
            k_node = inst["nodes"]["hub_indices"][ki]

            # (C1) Hub mutual exclusivity: a location is either planned OR reactive
            solver.Add(x[ki] + y[ki, si] <= 1)

            # (C3) Safety constraint for reactive hub: r_{ks} * y_{ks} <= chi
            #      Equivalently: y_{ks} = 0 whenever r_k > chi
            risk_k = sc["risk"][k_node]
            if risk_k > chi:
                solver.Add(y[ki, si] == 0)
            else:
                # Linearised safety: risk_k * y[ki,si] <= chi * y[ki,si] is trivially
                # true; the constraint is only binding when risk_k > chi (above).
                # Add an explicit bound for the BigM-free form:
                solver.Add(risk_k * y[ki, si] <= chi)

        # ---- Demand assignment constraints -----------------------------------
        for ii in range(num_I):
            i_node = inst["nodes"]["demand_indices"][ii]
            demand_i = float(sc["demand"][str(i_node)])

            if demand_i > 1e-6:
                # (C4) Single-allocation: sum_k z_iks + u_is = 1
                solver.Add(
                    sum(z_iks[ii, ki, si] for ki in range(num_H)) + u_is[ii, si] == 1
                )
                for ki in range(num_H):
                    k_node = inst["nodes"]["hub_indices"][ki]

                    # (C6) Assignment only to active hub (planned-active or reactive)
                    solver.Add(z_iks[ii, ki, si] <= x_act[ki, si] + y[ki, si])

                    # (C8) Assignment only if at least one mode is accessible
                    #      z_iks <= sum_m a_{ikms}
                    acc_sum = sum(
                        sc["accessibility"][m][k_node][i_node]
                        for m in range(num_M)
                    )
                    solver.Add(z_iks[ii, ki, si] <= acc_sum)
            else:
                # Zero demand: freeze all assignment variables
                solver.Add(u_is[ii, si] == 0)
                for ki in range(num_H):
                    solver.Add(z_iks[ii, ki, si] == 0)

        # ---- Origin assignment constraints -----------------------------------
        for ji in range(num_J):
            j_node = inst["nodes"]["origin_indices"][ji]
            supply_j = float(sc["supply"][str(j_node)])

            if supply_j > 1e-6:
                # (C5) Single-allocation: sum_k z_jks + v_js = 1
                solver.Add(
                    sum(z_jks[ji, ki, si] for ki in range(num_H)) + v_js[ji, si] == 1
                )
                for ki in range(num_H):
                    k_node = inst["nodes"]["hub_indices"][ki]

                    # (C7) Assignment only to active hub
                    solver.Add(z_jks[ji, ki, si] <= x_act[ki, si] + y[ki, si])

                    # (C9) Assignment only if at least one mode is accessible
                    acc_sum = sum(
                        sc["accessibility"][m][j_node][k_node]
                        for m in range(num_M)
                    )
                    solver.Add(z_jks[ji, ki, si] <= acc_sum)
            else:
                solver.Add(v_js[ji, si] == 0)
                for ki in range(num_H):
                    solver.Add(z_jks[ji, ki, si] == 0)

        # ---- Transshipment and flow constraints ------------------------------
        for ki in range(num_H):
            k_node = inst["nodes"]["hub_indices"][ki]
            for hi in range(num_H):
                for m in range(num_M):
                    h_node = inst["nodes"]["hub_indices"][hi]
                    # (C10) Transshipment only on intact arcs
                    solver.Add(
                        f_khms[ki, hi, m, si] <= tot_cap * sc["accessibility"][m][k_node][h_node]
                    )
                    # Arc-use indicator coupling
                    solver.Add(f_khms[ki, hi, m, si] <= tot_cap * w_trans[ki, hi, m, si])

            # (C11) Inventory + supply + transshipment_in >= demand + transshipment_out
            inventory_s = q[ki]
            
            # Demand sum must be converted from people to relief items via gamma
            sum_demand_items = sum(z_iks[ii, ki, si] * float(sc["demand"][str(inst["nodes"]["demand_indices"][ii])]) * gamma for ii in range(num_I))
            sum_supply_items = sum(z_jks[ji, ki, si] * float(sc["supply"][str(inst["nodes"]["origin_indices"][ji])]) for ji in range(num_J))
            sum_trans_in     = sum(f_khms[hi, ki, m, si] for hi in range(num_H) for m in range(num_M))
            sum_trans_out    = sum(f_khms[ki, hi, m, si] for hi in range(num_H) for m in range(num_M))

            solver.Add(
                inventory_s + sum_supply_items + sum_trans_in >= sum_demand_items + sum_trans_out
            )
            # (C12) Assignment/Flow only if active (planned-active or reactive)
            solver.Add(y[ki, si] + x_act[ki, si] <= 1)

            # (C12) Throughput capacity: total inflow <= kappa * hub_active
            solver.Add(
                q[ki] + sum(z_jks[ji, ki, si] * float(sc["supply"][str(inst["nodes"]["origin_indices"][ji])]) for ji in range(num_J)) + sum(f_khms[hi, ki, m, si] for hi in range(num_H) for m in range(num_M)) <= K_hub[ki] * (x_act[ki, si] + y[ki, si])
            )

        # ---- Helicopter quota (Mode index 2 = air/helicopter) ---------------
        # At most 15% of active routing links may use mode 2.
        # Using w_trans and z_iks/z_jks (same as before, but now z has no mode dim).
        # Count of helicopter z-links: each z_iks with helicopter as the only
        # accessible mode counts once. Since z_iks is not mode-indexed, we track
        # whether that assignment *uses* helicopter via the accessibility pattern.
        # For the quota, we tie it to the arc-use indicators w_trans for
        # transshipment links (mode=2), and separately for z links we use the
        # accessibility flag per mode as a coefficient proxy.
        heli_assign_i = solver.Sum(
            z_iks[ii, ki, si]
            for ii in range(num_I)
            for ki in range(num_H)
            if (
                sc["accessibility"][2][inst["nodes"]["hub_indices"][ki]][inst["nodes"]["demand_indices"][ii]]
                and not any(
                    sc["accessibility"][m2][inst["nodes"]["hub_indices"][ki]][inst["nodes"]["demand_indices"][ii]]
                    for m2 in range(num_M) if m2 != 2
                )
            )
        )
        heli_assign_j = solver.Sum(
            z_jks[ji, ki, si]
            for ji in range(num_J)
            for ki in range(num_H)
            if (
                sc["accessibility"][2][inst["nodes"]["origin_indices"][ji]][inst["nodes"]["hub_indices"][ki]]
                and not any(
                    sc["accessibility"][m2][inst["nodes"]["origin_indices"][ji]][inst["nodes"]["hub_indices"][ki]]
                    for m2 in range(num_M) if m2 != 2
                )
            )
        )
        heli_trans = solver.Sum(
            w_trans[ki, hi, 2, si]
            for ki in range(num_H)
            for hi in range(num_H)
        )
        total_links_s = (
            solver.Sum(z_iks[ii, ki, si] for ii in range(num_I) for ki in range(num_H)) +
            solver.Sum(z_jks[ji, ki, si] for ji in range(num_J) for ki in range(num_H)) +
            solver.Sum(w_trans[ki, hi, m, si] for ki in range(num_H) for hi in range(num_H) for m in range(num_M))
        )
        solver.Add(heli_assign_i + heli_assign_j + heli_trans <= 0.15 * total_links_s + 0.999)

        # ---- Z2 linearization -----------------------------------------------
        # W_s >= C^dep_{i,k,s} * z_iks  for all i,k,s  (eq:deprivation_bound)
        # C^dep_{i,k,s} = D_is * ( exp(lambda_is * (tau_ks + 2 * min_m tau_kim)) - 1 )
        # Because z_iks is single-allocation per demand, this is Big-M-free:
        # exactly one z_iks can be 1 per demand i, so W_s >= max_k [C^dep * z_iks].
        for ii in range(num_I):
            i_node = inst["nodes"]["demand_indices"][ii]
            demand_i = float(sc["demand"][str(i_node)])
            if demand_i <= 1e-6:
                continue

            lam_is = inst["lambda"][f"{i_node}_{si}"]

            # Penalty for unassigned demand (no hub reached)
            penalty = demand_i * min(math.expm1(lam_is * 24.0), 1e6)  # 24h wait cap
            solver.Add(z2_max_s[si] >= u_is[ii, si] * penalty)

            for ki in range(num_H):
                k_node = inst["nodes"]["hub_indices"][ki]

                # Find best (minimum) travel time for (i, k) pair across accessible modes
                min_t = float('inf')
                any_acc = False
                for m in range(num_M):
                    if sc["accessibility"][m][k_node][i_node]:
                        t = inst["transport"]["time"][m][k_node][i_node]
                        if t < min_t:
                            min_t = t
                        any_acc = True

                if any_acc:
                    tau_ks = sc["hub_process_time"][str(k_node)]
                    omega_iks = tau_ks + 2.0 * min_t
                    c_dep = demand_i * math.expm1(min(lam_is * omega_iks, 20.0))

                    # W_s >= C^dep_{iks} * z_{iks}   (binding when z_{iks}=1)
                    solver.Add(z2_max_s[si] >= c_dep * z_iks[ii, ki, si])

    # -------------------------------------------------------------------------
    # 3. Objective Functions
    # -------------------------------------------------------------------------
    # Z1: expected logistics cost
    z1_expr = solver.Sum(F_hub[ki] * x[ki] + C_hub[ki] * q[ki] for ki in range(num_H))

    for si, sc in enumerate(inst["scenarios"]):
        pi = sc["probability"]

        # Reactive hub setup cost (charged if y[ki,si] = 1)
        z1_expr += pi * solver.Sum(
            sc["hub_reactive_cost"][str(inst["nodes"]["hub_indices"][ki])] * y[ki, si]
            for ki in range(num_H)
        )

        # Origin-to-hub supply flow cost
        # Cost uses cheapest accessible mode per (j, k) pair in scenario s.
        for ji in range(num_J):
            j_node = inst["nodes"]["origin_indices"][ji]
            supply_j = float(sc["supply"][str(j_node)])
            for ki in range(num_H):
                k_node = inst["nodes"]["hub_indices"][ki]
                # Find cheapest accessible mode cost for this pair
                min_c = float('inf')
                any_acc = False
                for m in range(num_M):
                    if sc["accessibility"][m][j_node][k_node]:
                        c = inst["transport"]["cost"][m][j_node][k_node]
                        if c < min_c:
                            min_c = c
                        any_acc = True
                if any_acc:
                    # c_{jks} = min_m C_{jkm} (paper eq:obj1 comment for c_{jks})
                    z1_expr += pi * (min_c * supply_j * z_jks[ji, ki, si])

        # Inter-hub lateral transshipment cost (discounted by alpha)
        for ki in range(num_H):
            k_node = inst["nodes"]["hub_indices"][ki]
            for hi in range(num_H):
                h_node = inst["nodes"]["hub_indices"][hi]
                for m in range(num_M):
                    if sc["accessibility"][m][k_node][h_node]:
                        c_thm = inst["transport"]["cost"][m][k_node][h_node]
                        z1_expr += pi * (alpha * c_thm * f_khms[ki, hi, m, si])

        # Last-mile cost via pre-computed Daganzo CA theta[ki][ii][si]
        for ii in range(num_I):
            for ki in range(num_H):
                theta_val = inst["theta"][ki][ii][si]
                z1_expr += pi * (theta_val * z_iks[ii, ki, si])

        # Penalty for slack (unassigned demand/supply)
        z1_expr += pi * (sum(u_is[ii, si] for ii in range(num_I)) * big_M)
        z1_expr += pi * (sum(v_js[ji, si] for ji in range(num_J)) * big_M)

    # Z2: expected maximum deprivation cost
    z2_expr = solver.Sum(
        inst["scenarios"][si]["probability"] * z2_max_s[si]
        for si in range(num_S)
    )

    # Weighted-sum objective (w1 + w2 = 1)
    solver.Minimize(max(w1, 1e-7) * z1_expr + w2 * z2_expr)

    # Epsilon-constraint override (for exact Pareto front tracing)
    if eps_z2 is not None:
        solver.Add(z2_expr <= eps_z2)
        solver.Minimize(z1_expr)
    elif eps_z1 is not None:
        solver.Add(z1_expr <= eps_z1)
        solver.Minimize(z2_expr)

    # -------------------------------------------------------------------------
    # 4. Solve and extract results
    # -------------------------------------------------------------------------
    t0 = time.time()
    cpu0 = time.process_time()
    status = solver.Solve()
    elapsed = time.time() - t0
    cpu_elapsed = time.process_time() - cpu0

    if status == pywraplp.Solver.OPTIMAL or status == pywraplp.Solver.FEASIBLE:
        X_res = [int(x[ki].solution_value() > 0.5) for ki in range(num_H)]
        # Inventory fill ratios
        R_res = [
            q[ki].solution_value() / K_hub[ki] if K_hub[ki] > 0 else 0.0
            for ki in range(num_H)
        ]
        # Total unassigned demand+supply (constraint violation count)
        CV_val = (
            sum(u_is[ii, si].solution_value() for ii in range(num_I) for si in range(num_S)) +
            sum(v_js[ji, si].solution_value() for ji in range(num_J) for si in range(num_S))
        )

        return {
            "status":    "OPTIMAL" if status == pywraplp.Solver.OPTIMAL else "FEASIBLE",
            "Z1":        z1_expr.solution_value(),
            "Z2":        z2_expr.solution_value(),
            "X":         X_res,
            "R":         R_res,
            "CV":        CV_val,
            "elapsed_s": elapsed,
            "cpu_time_s": cpu_elapsed,
        }
    else:
        print(f"Solver status: {status}")
        return {"status": "INFEASIBLE", "elapsed_s": time.time() - t0, "cpu_time_s": time.process_time() - cpu0}


def run_weighted_sum(inst, steps=1000, time_limit=600):
    """Run weighted-sum MILP. Iterates through weight combinations and returns non-dominated front."""
    if steps < 2:
        steps = 2

    front = []

    for i in range(steps):
        w1 = (steps - 1 - i) / (steps - 1)
        w2 = 1.0 - w1

        print(f"Solving weighted-sum {i+1}/{steps}: w1={w1:.3f}, w2={w2:.3f}")
        sol = build_and_solve_milp(inst, w1=w1, w2=w2, time_limit_s=time_limit)

        if sol and sol["status"] != "INFEASIBLE":
            print(f"  Result: Z1={sol['Z1']:.4f}, Z2={sol['Z2']:.4f}, "
                  f"CV={sol['CV']:.2f}, time={sol['elapsed_s']:.2f}s")
            front.append(sol)
        else:
            elapsed = sol.get("elapsed_s", "?") if sol else "?"
            print(f"  Weighted-sum {i+1} failed or infeasible (time={elapsed}s).")

    # Filter dominated solutions
    filtered = []
    for s1 in front:
        dominated = any(
            s2["Z1"] <= s1["Z1"] and s2["Z2"] <= s1["Z2"]
            and (s2["Z1"] < s1["Z1"] or s2["Z2"] < s1["Z2"])
            for s2 in front
        )
        if not dominated:
            filtered.append(s1)

    return filtered


def main():
    parser = argparse.ArgumentParser(description="MILP Baseline: MO-IHLNDP weighted-sum solver.")
    parser.add_argument("--instance",   required=True, help="Path to the JSON instance file.")
    parser.add_argument("--out",        required=True, help="Path to save results JSON.")
    parser.add_argument("--steps",      type=int, default=1000, help="Number of weighted-sum points.")
    parser.add_argument("--time_limit", type=int, default=600, help="Per-solve SCIP time limit (s).")
    args = parser.parse_args()

    inst = load_instance(args.instance)

    t_start = time.time()
    cpu_start = time.process_time()
    pareto  = run_weighted_sum(inst, steps=args.steps, time_limit=args.time_limit)
    t_total = time.time() - t_start
    cpu_total = time.process_time() - cpu_start

    per_solve_times = [s.get("elapsed_s", 0.0) for s in pareto]
    per_solve_cpu   = [s.get("cpu_time_s", 0.0) for s in pareto]

    out_data = {
        "meta": {
            "solver":           "MILP_WeightedSum_SCIP",
            "instance":         args.instance,
            "steps":            args.steps,
            "time_limit_s":     args.time_limit,
            "total_elapsed_s":  t_total,
            "total_cpu_s":      cpu_total,
            "per_solve_time_s": per_solve_times,
            "per_solve_cpu_s":  per_solve_cpu,
        },
        "pareto_front": pareto
    }

    with open(args.out, "w") as f:
        json.dump(out_data, f, indent=2)

    print(f"\nMILP Baseline finished.")
    print(f"  Pareto solutions found : {len(pareto)}")
    print(f"  Total wall-clock time  : {t_total:.2f}s")
    print(f"  Results saved to       : {args.out}")


if __name__ == "__main__":
    main()
