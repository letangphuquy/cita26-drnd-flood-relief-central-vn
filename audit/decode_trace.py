#!/usr/bin/env python3
"""
decode_trace.py — Python replica of decoder.hpp (v3) for debugging.

Implements the full 7-step decoder faithfully:
  Step 1. Decode X/R/q, fixed stage-1 costs
  Step 2. Activate planned hubs per scenario (risk ≤ χ; fallback to safest)
  Step 3. Demand priority scores (urgency, isolation, dist — normalised)
  Step 4. Tiered demand allocation (anchor-proximity order, 3 passes)
  Step 5+6. MCF supply balancing (OR-Tools SimpleMinCostFlow)
  Step 7. Accumulate expected Z1, Z2

Usage:
    ./.venv/bin/python3 audit/decode_trace.py \
        --instance data/cv/v2/cv_small_drnd.json \
        --nsga    results/exp1/v2/CV_small_seed0.json \
        --milp    results/exp1/v2/cv_small_milp_aws.json \
        --sol-idx 3

Output: per-demand assignment trace, Z1 breakdown, comparison table.
"""
import json, math, argparse, sys
from pathlib import Path
from ortools.graph.python import min_cost_flow as mcf_lib

EPS = 1e-9
BIG_M_COST = 1e9

# ── helpers ────────────────────────────────────────────────────────────────

def norm_inplace(v):
    mn, mx = min(v), max(v)
    rng = mx - mn
    if rng < EPS:
        return [0.5] * len(v)
    return [(x - mn) / rng for x in v]


def best_mode_time(sc, tr_time, from_node, to_node, num_M):
    """Road→water→air priority; returns (mode, time). (-1, inf) if unreachable."""
    acc = sc["accessibility"]
    for m in (0, 1):
        if acc[m][from_node][to_node] and tr_time[m][from_node][to_node] < 1e8:
            return m, tr_time[m][from_node][to_node]
    if acc[2][from_node][to_node]:
        return 2, tr_time[2][from_node][to_node]
    return -1, float("inf")


def best_mode_cost(sc, tr_cost, from_node, to_node, num_M):
    """Road→water→air priority on cost; returns (mode, cost)."""
    acc = sc["accessibility"]
    for m in (0, 1):
        if acc[m][from_node][to_node] and tr_cost[m][from_node][to_node] < 1e8:
            return m, tr_cost[m][from_node][to_node]
    if acc[2][from_node][to_node]:
        return 2, tr_cost[2][from_node][to_node]
    return -1, float("inf")


def hub_anchor_order(inst):
    """
    Precompute hub_anchor_order[ki][j] = j-th closest hub to hub ki
    (Euclidean in lat/lon).  Mirrors decoder.hpp hub_anchor_order block.
    """
    coords = inst["nodes"]["coords"]
    hub_idx = inst["nodes"]["hub_indices"]
    num_H = len(hub_idx)
    order = []
    for ki in range(num_H):
        hi = hub_idx[ki]
        lat_i, lon_i = coords[hi]
        dists = []
        for kj in range(num_H):
            hj = hub_idx[kj]
            lat_j, lon_j = coords[hj]
            d2 = (lat_i - lat_j) ** 2 + (lon_i - lon_j) ** 2
            dists.append((d2, kj))
        dists.sort()
        order.append([kj for _, kj in dists])
    return order


# ── MCF supply balancer (Step 5+6) ────────────────────────────────────────

def run_mcf(net_inv, inst, sc, tr_cost, alpha, num_H, num_J, active, y_react):
    """
    Returns (Z1_supply, origin_hub_flow, h2h_flows) mirroring decoder.hpp lines 401–519.

    origin_hub_flow[jj][ki] = units routed from origin jj to hub ki
    h2h_flows = list of (src_ki, dst_ki, mode, used)
    Z1_supply = sum of cost * used for all flow edges
    """
    hub_idx = inst["nodes"]["hub_indices"]
    origin_idx = inst["nodes"]["origin_indices"]

    # Precompute o2h and h2h costs
    o2h_cost = {}
    o2h_mode = {}
    for jj, j in enumerate(origin_idx):
        for ki, k in enumerate(hub_idx):
            if not (active[ki] or y_react[ki]):
                continue
            m, c = best_mode_cost(sc, tr_cost, j, k, 3)
            if m != -1:
                o2h_cost[jj, ki] = c
                o2h_mode[jj, ki] = m

    h2h_cost = {}
    h2h_mode_map = {}
    for ski, sk in enumerate(hub_idx):
        if not (active[ski] or y_react[ski]):
            continue
        for dki, dk in enumerate(hub_idx):
            if ski == dki or not (active[dki] or y_react[dki]):
                continue
            m, c = best_mode_cost(sc, tr_cost, sk, dk, 3)
            if m != -1:
                h2h_cost[ski, dki] = alpha * c
                h2h_mode_map[ski, dki] = m

    # Integer-cap deficit hubs; b[SRC] = sum of caps to guarantee balance.
    deficit_caps = []
    for ki in range(num_H):
        if (active[ki] or y_react[ki]) and net_inv[ki] < -EPS:
            deficit_caps.append((ki, int(-net_inv[ki])))
    total_deficit_int = sum(c for _, c in deficit_caps)

    if total_deficit_int == 0:
        return 0.0, {}, []

    # OR-Tools SimpleMinCostFlow (integer costs → scale by 1000)
    SCALE = 1000
    smcf = mcf_lib.SimpleMinCostFlow()

    # Node numbering: SRC=0, origin[jj]=1..num_J, hub[ki]=num_J+1..num_J+num_H, SNK=num_J+num_H+1
    SRC = 0
    ORG0 = 1
    HUB0 = ORG0 + num_J
    SNK = HUB0 + num_H
    arc_meta = []  # (kind, src_idx, dst_idx, mode)

    total_origin_supply = 0
    for jj, j in enumerate(origin_idx):
        O = int(float(sc["supply"][str(j)]))
        if O <= 0:
            continue
        total_origin_supply += O
        smcf.add_arc_with_capacity_and_unit_cost(SRC, ORG0 + jj, O, 0)
        arc_meta.append(("src_org", jj, -1, -1))
        for ki in range(num_H):
            if (jj, ki) not in o2h_cost:
                continue
            c_int = int(o2h_cost[jj, ki] * SCALE)
            smcf.add_arc_with_capacity_and_unit_cost(ORG0 + jj, HUB0 + ki, O, c_int)
            arc_meta.append(("o2h", jj, ki, o2h_mode[jj, ki]))

    big_cap = total_origin_supply + sum(
        int(net_inv[ki]) for ki in range(num_H)
        if (active[ki] or y_react[ki]) and net_inv[ki] > EPS
    )
    big_cap = max(1, big_cap)

    for ki in range(num_H):
        if not (active[ki] or y_react[ki]):
            continue
        if net_inv[ki] > EPS:
            smcf.add_arc_with_capacity_and_unit_cost(SRC, HUB0 + ki, int(net_inv[ki]), 0)
            arc_meta.append(("src_hub", ki, -1, -1))

        for kj in range(num_H):
            if (ki, kj) not in h2h_cost:
                continue
            c_int = int(h2h_cost[ki, kj] * SCALE)
            smcf.add_arc_with_capacity_and_unit_cost(HUB0 + ki, HUB0 + kj, big_cap, c_int)
            arc_meta.append(("h2h", ki, kj, h2h_mode_map[ki, kj]))

    for ki, cap in deficit_caps:
        smcf.add_arc_with_capacity_and_unit_cost(HUB0 + ki, SNK, cap, 0)
        arc_meta.append(("hub_snk", ki, -1, -1))

    # Balance: b[SRC] = sum of integer deficit caps (not float total_deficit).
    smcf.set_node_supply(SRC, total_deficit_int)
    smcf.set_node_supply(SNK, -total_deficit_int)
    for jj in range(num_J):
        smcf.set_node_supply(ORG0 + jj, 0)
    for ki in range(num_H):
        smcf.set_node_supply(HUB0 + ki, 0)

    status = smcf.solve()
    if status != smcf.OPTIMAL:
        return 0.0, {}, []

    Z1_supply = 0.0
    origin_hub_flow = {(jj, ki): 0.0 for jj in range(num_J) for ki in range(num_H)}
    h2h_flows = []

    for arc_id, (kind, src_idx, dst_idx, mode) in enumerate(arc_meta):
        used = smcf.flow(arc_id)
        if used <= 0 or kind in ("src_org", "src_hub", "hub_snk"):
            continue
        if kind == "o2h":
            cost_per_unit = o2h_cost[src_idx, dst_idx]
            Z1_supply += cost_per_unit * used
            origin_hub_flow[src_idx, dst_idx] += used
        elif kind == "h2h":
            cost_per_unit = h2h_cost[src_idx, dst_idx]
            Z1_supply += cost_per_unit * used
            h2h_flows.append((src_idx, dst_idx, mode, used))

    return Z1_supply, origin_hub_flow, h2h_flows


# ── Main decoder ───────────────────────────────────────────────────────────

def decode_solution(inst, sol, verbose=False, label=""):
    """
    Full Python decoder mirroring decoder.hpp.
    sol: dict with keys X, R, A, W (lists).
    Returns: dict with Z1, Z2, CV, per-scenario details.
    """
    dims = inst["dimensions"]
    num_H, num_I, num_J, num_S, num_M = (
        dims["num_H"], dims["num_I"], dims["num_J"], dims["num_S"], dims["num_M"]
    )
    gp = inst["global_params"]
    chi, gamma, alpha = gp["chi"], gp["gamma"], gp["alpha"]

    hub_idx = inst["nodes"]["hub_indices"]
    demand_idx = inst["nodes"]["demand_indices"]
    origin_idx = inst["nodes"]["origin_indices"]
    tr_cost = inst["transport"]["cost"]
    tr_time = inst["transport"]["time"]
    theta = inst["theta"]          # [ki][ii][si]
    lam_raw = inst["lambda"]       # dict f"{ii}_{si}"
    coords = inst["nodes"]["coords"]
    hub_p = inst["hub_params"]
    F_hub = [hub_p["fixed_cost"][str(k)] for k in hub_idx]
    c_hold = [hub_p["hold_cost"][str(k)] for k in hub_idx]
    K_hub = [hub_p["capacity"][str(k)] for k in hub_idx]

    X = sol["X"]
    R = sol["R"]
    A = sol["A"]
    W = sol["W"]

    # ── Step 1: Decode q, fixed costs ──────────────────────────────────────
    q = [R[ki] * K_hub[ki] if X[ki] else 0.0 for ki in range(num_H)]
    Z1_fixed = sum(F_hub[ki] + c_hold[ki] * q[ki] for ki in range(num_H) if X[ki])

    # ── Pre-compute hub_anchor_order ───────────────────────────────────────
    hao = hub_anchor_order(inst)

    Z1 = 0.0
    Z2 = 0.0
    CV = 0.0
    per_sc = []

    for si in range(num_S):
        sc = inst["scenarios"][si]
        pi_s = sc["probability"]
        Z1_s = Z1_fixed  # start with fixed+holding (shared across scenarios)
        Z2_s = 0.0

        # ── Step 2: Activate planned hubs ──────────────────────────────────
        active = [False] * num_H
        y_react = [False] * num_H
        inventory = [0.0] * num_H

        for ki in range(num_H):
            k = hub_idx[ki]
            if X[ki] and sc["risk"][k] <= chi:
                active[ki] = True
                inventory[ki] = q[ki]

        if not any(active):
            best_ki = min(range(num_H), key=lambda ki: sc["risk"][hub_idx[ki]])
            active[best_ki] = True
            inventory[best_ki] = q[best_ki]

        # ── Step 3: Demand priority scores ─────────────────────────────────
        raw_urgency, raw_isolation, raw_dist = [], [], []
        for ii in range(num_I):
            i = demand_idx[ii]
            D = float(sc["demand"][str(i)])
            lam = lam_raw[f"{ii}_{si}"]
            raw_urgency.append(lam * D)

            n_reach = 0
            min_t = float("inf")
            for ki in range(num_H):
                if not active[ki]:
                    continue
                k = hub_idx[ki]
                reachable = False
                for m in range(num_M):
                    if sc["accessibility"][m][i][k]:
                        reachable = True
                        t = tr_time[m][i][k]
                        if t < min_t:
                            min_t = t
                if reachable:
                    n_reach += 1
            raw_isolation.append(1.0 / n_reach if n_reach > 0 else 1.0)
            raw_dist.append(min_t if min_t < 1e8 else 0.0)

        norm_urgency = norm_inplace(raw_urgency)
        norm_isolation = norm_inplace(raw_isolation)
        norm_dist = norm_inplace(raw_dist)
        demand_score = [
            W[0] * norm_urgency[ii] + W[3] * norm_isolation[ii] - W[1] * norm_dist[ii] + ii * 1e-6
            for ii in range(num_I)
        ]
        demand_order = sorted(range(num_I), key=lambda ii: -demand_score[ii])

        # ── Step 4: Tiered demand allocation ───────────────────────────────
        z_ik = [-1] * num_I
        hub_load = [0.0] * num_H
        assign_trace = []

        for ii in demand_order:
            i = demand_idx[ii]
            D = float(sc["demand"][str(i)])
            D_kg = gamma * D

            anchor = A[ii] % num_H
            trial_order = hao[anchor]
            K_window = max(int(math.floor(math.sqrt(num_H))), int(math.ceil(W[5] * num_H)))

            best_ki = -1
            best_score = -1e18
            chosen_pass = -1

            # Pass 1: first K_window candidates, best scoring
            for j in range(K_window):
                ki = trial_order[j]
                if not (active[ki] or y_react[ki]):
                    continue
                k = hub_idx[ki]
                b_m, best_t = best_mode_time(sc, tr_time, i, k, num_M)
                if b_m == -1:
                    continue
                residual = inventory[ki] - hub_load[ki]
                has_global_surplus = any(
                    (active[kj] or y_react[kj]) and (inventory[kj] - hub_load[kj] > EPS)
                    for kj in range(num_H)
                )
                if residual <= 0.0 and not has_global_surplus:
                    continue
                score = W[1] / (best_t + EPS) + W[2] * max(0.0, residual) + W[4] * (1.0 if X[ki] else 0.0)
                if score > best_score:
                    best_score = score
                    best_ki = ki
                    chosen_pass = 1

            # Pass 2: remaining candidates, first active+reachable
            if best_ki == -1:
                for j in range(K_window, num_H):
                    ki = trial_order[j]
                    if not (active[ki] or y_react[ki]):
                        continue
                    k = hub_idx[ki]
                    b_m, _ = best_mode_time(sc, tr_time, i, k, num_M)
                    if b_m == -1:
                        continue
                    best_ki = ki
                    chosen_pass = 2
                    break

            # Pass 3: open safe reactive hub
            if best_ki == -1:
                for ki in range(num_H):
                    if active[ki] or y_react[ki]:
                        continue
                    k = hub_idx[ki]
                    if sc["risk"][k] > chi:
                        continue
                    b_m, _ = best_mode_time(sc, tr_time, i, k, num_M)
                    if b_m == -1:
                        continue
                    y_react[ki] = True
                    inventory[ki] = 0.0
                    Z1_s += float(sc["hub_reactive_cost"][str(hub_idx[ki])])
                    best_ki = ki
                    chosen_pass = 3
                    break

            assign_trace.append({
                "ii": ii, "i_node": i, "D": D, "score": demand_score[ii],
                "anchor": anchor, "anchor_hub": hub_idx[anchor],
                "assigned_ki": best_ki,
                "assigned_hub": hub_idx[best_ki] if best_ki >= 0 else -1,
                "pass": chosen_pass
            })

            if best_ki == -1:
                CV += D_kg
                Z1_s += gp["big_M"]
                Z2_s = max(Z2_s, gp["big_M"])
            else:
                z_ik[ii] = best_ki
                hub_load[best_ki] += D_kg

                if not X[best_ki] and not y_react[best_ki]:
                    y_react[best_ki] = True
                    inventory[best_ki] = 0.0
                    Z1_s += float(sc["hub_reactive_cost"][str(hub_idx[best_ki])])

                Z1_s += theta[best_ki][ii][si]

                k_node = hub_idx[best_ki]
                min_t = min(
                    (tr_time[m][i][k_node] for m in range(num_M) if sc["accessibility"][m][i][k_node]),
                    default=0.0
                )
                proc_t = float(sc["hub_process_time"][str(k_node)])
                omega = proc_t + 2.0 * min_t
                lam = lam_raw[f"{ii}_{si}"]
                exp_arg = min(lam * omega, 20.0)
                depriv = D * (math.expm1(exp_arg))
                Z2_s = max(Z2_s, depriv)

        # ── Step 5+6: MCF supply balancing ─────────────────────────────────
        net_inv = [inventory[ki] - hub_load[ki] for ki in range(num_H)]
        Z1_supply, origin_hub_flow, h2h_flows = run_mcf(
            net_inv, inst, sc, tr_cost, alpha, num_H, num_J, active, y_react
        )
        Z1_s += Z1_supply

        Z1 += pi_s * Z1_s
        Z2 = max(Z2, Z2_s)

        per_sc.append({
            "si": si, "pi": pi_s,
            "Z1_s": Z1_s, "Z2_s": Z2_s,
            "active": list(active), "reactive": list(y_react),
            "inventory": list(inventory), "hub_load": list(hub_load),
            "net_inv": list(net_inv),
            "theta_total": sum(theta[z_ik[ii]][ii][si] for ii in range(num_I) if z_ik[ii] >= 0),
            "Z1_supply": Z1_supply,
            "assign_trace": assign_trace,
            "origin_hub_flow": {str(k): v for k, v in origin_hub_flow.items() if v > EPS},
            "h2h_flows": h2h_flows,
        })

        if verbose:
            hub_names = [inst["nodes"]["names"][k] for k in hub_idx]
            print(f"\n  Scenario {si} (π={pi_s:.3f}):")
            print(f"    Active: {[hub_names[ki] for ki in range(num_H) if active[ki]]}")
            print(f"    Reactive: {[hub_names[ki] for ki in range(num_H) if y_react[ki]]}")
            print(f"    Z1_s={Z1_s:,.0f}  (theta={per_sc[-1]['theta_total']:,.0f}  supply={Z1_supply:,.0f})")
            print(f"    Z2_s={Z2_s:,.0f}")
            print(f"    Demand assignments (sorted by priority):")
            for t in assign_trace:
                dname = inst["nodes"]["names"][t["i_node"]]
                hname = hub_names[t["assigned_ki"]] if t["assigned_ki"] >= 0 else "UNSERVED"
                anc = hub_names[t["anchor"]]
                print(f"      [{t['ii']:2d}] {dname[:28]:28s}  D={t['D']:7.0f}"
                      f"  score={t['score']:+.4f}  anchor={anc[:20]:20s}"
                      f"  → {hname[:22]:22s}  (pass {t['pass']})")

    return {"Z1": Z1, "Z2": Z2, "CV": CV, "per_sc": per_sc,
            "Z1_fixed": Z1_fixed, "K_window": K_window}


# ── CLI entry point ────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Decoder trace for MO-IHLNDP solutions")
    ap.add_argument("--instance", required=True)
    ap.add_argument("--nsga",     required=True, help="PB-NSGA result JSON")
    ap.add_argument("--milp",     required=True, help="MILP-AWS result JSON")
    ap.add_argument("--sol-idx",  type=int, default=3, help="Solution index (0-based)")
    args = ap.parse_args()

    with open(args.instance) as f:
        inst = json.load(f)
    with open(args.nsga) as f:
        nsga_res = json.load(f)
    with open(args.milp) as f:
        milp_res = json.load(f)

    hub_names = [inst["nodes"]["names"][k] for k in inst["nodes"]["hub_indices"]]
    num_H = inst["dimensions"]["num_H"]

    # ── Print NSGA PF summary ───────────────────────────────────────────────
    nsga_pf = nsga_res.get("pareto_front", nsga_res.get("solutions", []))
    milp_pf = milp_res.get("pareto_front", milp_res.get("solutions", []))

    print("=" * 70)
    print(f"PB-NSGA Pareto front ({len(nsga_pf)} solutions):")
    for idx, sol in enumerate(nsga_pf):
        mark = " ◄ target" if idx == args.sol_idx else ""
        print(f"  [{idx}] Z1={sol['Z1']:>12,.0f}  Z2={sol['Z2']:>8,.0f}  "
              f"X={sol['X']}  CV={sol.get('CV',0):.4f}{mark}")

    print(f"\nMILP Pareto front ({len(milp_pf)} solutions):")
    for idx, sol in enumerate(milp_pf):
        mark = " ◄ target" if idx == args.sol_idx else ""
        print(f"  [{idx}] Z1={sol['Z1']:>12,.0f}  Z2={sol['Z2']:>8,.0f}  "
              f"X={sol['X']}  CV={sol.get('CV',0):.4f}{mark}")

    # ── Select solutions ────────────────────────────────────────────────────
    nsga_sol = nsga_pf[args.sol_idx]
    milp_sol = milp_pf[args.sol_idx]

    print("\n" + "=" * 70)
    print(f"NSGA solution[{args.sol_idx}]: Z1={nsga_sol['Z1']:,.0f}  Z2={nsga_sol['Z2']:,.0f}")
    print(f"  X={nsga_sol['X']}  R={[round(r,3) for r in nsga_sol['R']]}")
    print(f"  A={nsga_sol['A']}  W={[round(w,4) for w in nsga_sol['W']]}")
    print(f"  K_window = max(1, ceil({nsga_sol['W'][5]:.4f}×{num_H})) = "
          f"{max(1, math.ceil(nsga_sol['W'][5]*num_H))}")

    print(f"\nMILP solution[{args.sol_idx}]: Z1={milp_sol['Z1']:,.0f}  Z2={milp_sol['Z2']:,.0f}")
    print(f"  X={milp_sol['X']}  R={[round(r,3) for r in milp_sol['R']]}")

    # ── Decode NSGA solution ────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print(f"DECODING NSGA solution[{args.sol_idx}]:")
    nsga_dec = decode_solution(inst, nsga_sol, verbose=True, label="NSGA")

    # ── MILP assignments (from LP solution) ────────────────────────────────
    print("\n" + "=" * 70)
    print(f"MILP solution[{args.sol_idx}] LP assignments (already solved):")
    milp_asgn = milp_sol.get("lp_assignments", {})
    dims = inst["dimensions"]
    demand_idx = inst["nodes"]["demand_indices"]
    for si in range(dims["num_S"]):
        sc_asgn = milp_asgn.get(str(si), {})
        print(f"  Scenario {si}:")
        for ii in range(dims["num_I"]):
            i = demand_idx[ii]
            entry = sc_asgn.get(str(ii), {})
            ki = entry.get("hub", entry.get("hub_ki", -1))  # JSON uses "hub" key
            mode = entry.get("mode", -1)
            hub_name = hub_names[ki] if 0 <= ki < num_H else "unserved"
            print(f"    [{ii:2d}] {inst['nodes']['names'][i][:28]:28s}  → hub{ki} ({hub_name[:22]:22s})  mode={mode}")

    # ── Z1 comparison summary ───────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("Z1 BREAKDOWN COMPARISON")
    print(f"{'Component':<28} {'NSGA decoded':>14}  {'MILP reported':>14}")
    print("-" * 60)
    print(f"{'Z1 (reported/decoded)':<28} {nsga_dec['Z1']:>14,.0f}  {milp_sol['Z1']:>14,.0f}")
    print(f"{'Z1_fixed (first-stage)':<28} {nsga_dec['Z1_fixed']:>14,.0f}  {'(in Z1)':>14}")
    for si, psc in enumerate(nsga_dec["per_sc"]):
        sc = inst["scenarios"][si]
        print(f"  sc{si} theta (π={sc['probability']:.3f})"
              f"         {psc['theta_total']:>14,.0f}")
        print(f"  sc{si} supply+trans"
              f"              {psc['Z1_supply']:>14,.0f}")
    print(f"{'Z2 (reported/decoded)':<28} {nsga_dec['Z2']:>14,.0f}  {milp_sol['Z2']:>14,.0f}")
    print(f"{'NSGA Z1 (solver JSON)':<28} {nsga_sol['Z1']:>14,.0f}")
    print(f"{'Decoder vs solver diff':<28} {nsga_dec['Z1'] - nsga_sol['Z1']:>+14,.0f}")


if __name__ == "__main__":
    main()
