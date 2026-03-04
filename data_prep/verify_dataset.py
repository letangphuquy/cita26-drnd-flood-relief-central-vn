"""
verify_dataset.py
=================
Sanity-check DRND instances produced by generate_drnd.py.
Checks dimensions, capacity coverage, risk structure, scenario logic,
transport matrices, and Theta / Lambda completeness.

Usage:
  python verify_dataset.py                  # checks both small and large
  python verify_dataset.py cv_small_drnd.json
"""

import sys
import os
import json
import math

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
GAMMA = 3.0
PASS = "[PASS]"
FAIL = "[FAIL]"
WARN = "[WARN]"


def check(cond, msg, fatal=False):
    tag = PASS if cond else (FAIL if fatal else WARN)
    print(f"  {tag}  {msg}")
    return cond


def verify(path):
    print(f"\n{'='*60}")
    print(f"Verifying: {os.path.basename(path)}")
    print("="*60)

    with open(path, "r", encoding="utf-8") as f:
        d = json.load(f)

    dims   = d["dimensions"]
    nodes  = d["nodes"]
    n_I    = dims["num_I"]
    n_H    = dims["num_H"]
    n_J    = dims["num_J"]
    n_S    = dims["num_S"]
    n_M    = dims["num_M"]
    n_tot  = n_I + n_H + n_J

    print(f"  Instance : {d['meta']['name']}")
    print(f"  Dims     : I={n_I}  H={n_H}  J={n_J}  S={n_S}  M={n_M}")

    errors = 0

    # -- Node structure --------------------------------------------------------
    print("\n[1] Node structure")
    check(len(nodes["coords"])  == n_tot, f"coords length = {len(nodes['coords'])} (expected {n_tot})", fatal=True)
    check(len(nodes["names"])   == n_tot, f"names  length = {len(nodes['names'])}")
    check(len(nodes["demand_indices"]) == n_I, f"demand_indices length = {n_I}")
    check(len(nodes["hub_indices"])    == n_H, f"hub_indices    length = {n_H}")
    check(len(nodes["origin_indices"]) == n_J, f"origin_indices length = {n_J}")

    # Auxiliary risk field
    aux_risk = nodes.get("aux_risk", None)
    if check(aux_risk is not None, "aux_risk present in nodes", fatal=True):
        check(len(aux_risk) == n_tot, f"aux_risk length = {len(aux_risk)}")
        r_d = [aux_risk[i] for i in nodes["demand_indices"]]
        r_h = [aux_risk[k] for k in nodes["hub_indices"]]
        r_j = [aux_risk[j] for j in nodes["origin_indices"]]
        print(f"         demand  r^a: min={min(r_d):.3f}  mean={sum(r_d)/len(r_d):.3f}  max={max(r_d):.3f}")
        print(f"         hub     r^a: min={min(r_h):.3f}  mean={sum(r_h)/len(r_h):.3f}  max={max(r_h):.3f}")
        print(f"         origin  r^a: min={min(r_j):.3f}  mean={sum(r_j)/len(r_j):.3f}  max={max(r_j):.3f}")
        check(all(0 <= r <= 1 for r in aux_risk), "all r^a_u in [0,1]", fatal=True)
        # Hubs should generally be safer than demand mean
        check(sum(r_h)/len(r_h) < sum(r_d)/len(r_d) + 0.15,
              f"hub mean risk ({sum(r_h)/len(r_h):.3f}) not dramatically higher than demand ({sum(r_d)/len(r_d):.3f})")

    # -- Coordinate bounds (Central Vietnam) -----------------------------------
    print("\n[2] Coordinate bounds")
    lats = [c[0] for c in nodes["coords"]]
    lons = [c[1] for c in nodes["coords"]]
    check(all(14.0 <= la <= 18.0 for la in lats), f"lat range [{min(lats):.3f}, {max(lats):.3f}]")
    check(all(106.5 <= lo <= 110.0 for lo in lons), f"lon range [{min(lons):.3f}, {max(lons):.3f}]")

    # -- Hub parameters --------------------------------------------------------
    print("\n[3] Hub parameters")
    hp = d["hub_params"]
    check(len(hp["capacity"])   == n_H, f"capacity   entries = {n_H}")
    check(len(hp["fixed_cost"]) == n_H, f"fixed_cost entries = {n_H}")
    check(len(hp["hold_cost"])  == n_H, f"hold_cost  entries = {n_H}")
    total_kappa = sum(float(v) for v in hp["capacity"].values())
    print(f"         total kappa = {total_kappa:,.0f} kg")

    # -- Scenarios -------------------------------------------------------------
    print("\n[4] Scenarios")
    probs  = [sc["probability"] for sc in d["scenarios"]]
    check(abs(sum(probs) - 1.0) < 1e-6, f"probabilities sum to {sum(probs):.6f}")
    check(len(d["scenarios"]) == n_S, f"scenario count = {n_S}")

    avg_risks   = []
    total_dems  = []
    total_sups  = []

    for si, sc in enumerate(d["scenarios"]):
        # risk must be a list of length n_tot
        risk = sc["risk"]
        check(isinstance(risk, list), f"s{si} risk is list (not dict)", fatal=True)
        check(len(risk) == n_tot, f"s{si} risk length = {len(risk)} (expected {n_tot})", fatal=True)
        check(all(0 <= r <= 1 for r in risk), f"s{si} all risk in [0,1]")

        # phi_circuity present
        check("phi_circuity" in sc, f"s{si} has phi_circuity field")

        # demand & supply
        total_d = sum(float(v) for v in sc["demand"].values())
        total_s = sum(float(v) for v in sc["supply"].values())
        total_d_kg = GAMMA * total_d
        ratio = total_s / max(total_d_kg, 1)
        avg_r = sum(risk[i] for i in nodes["demand_indices"]) / n_I
        avg_risks.append(avg_r)
        total_dems.append(total_d_kg)
        total_sups.append(total_s)

        check(ratio >= 1.5,
              f"s{si} [{sc['name']:8s}] supply/demand = {ratio:.2f}x  "
              f"(demand={total_d_kg:,.0f} kg, supply={total_s:,.0f} kg)")
        check(total_kappa >= total_d_kg,
              f"s{si} total_kappa ({total_kappa:,.0f}) >= demand ({total_d_kg:,.0f})")

        # accessibility diagonal
        a = sc["accessibility"]
        check(len(a) == n_M and len(a[0]) == n_tot and len(a[0][0]) == n_tot,
              f"s{si} accessibility shape [{n_M}][{n_tot}][{n_tot}]", fatal=True)
        diag_ok = all(a[m][u][u] == 0 for m in range(n_M) for u in range(n_tot))
        check(diag_ok, f"s{si} accessibility diagonal = 0")

        # hub_reactive_cost and hub_process_time keyed by hub abs index
        check(len(sc["hub_reactive_cost"]) == n_H,
              f"s{si} hub_reactive_cost entries = {n_H}")
        check(len(sc["hub_process_time"]) == n_H,
              f"s{si} hub_process_time  entries = {n_H}")

    # Risk escalation: mild < severe < extreme on average
    print(f"         avg demand risk per scenario: "
          + "  ".join(f"{d['scenarios'][si]['name']}={avg_risks[si]:.3f}"
                      for si in range(n_S)))
    check(avg_risks[0] < avg_risks[1] < avg_risks[2],
          "avg demand risk escalates mild < severe < extreme")
    check(total_dems[0] < total_dems[1] < total_dems[2],
          "total demand escalates mild < severe < extreme")

    # -- Transport matrices ----------------------------------------------------
    print("\n[5] Transport matrices")
    C = d["transport"]["cost"]
    T = d["transport"]["time"]
    check(len(C) == n_M and len(C[0]) == n_tot and len(C[0][0]) == n_tot,
          f"cost matrix shape [{n_M}][{n_tot}][{n_tot}]", fatal=True)
    check(len(T) == n_M and len(T[0]) == n_tot and len(T[0][0]) == n_tot,
          f"time matrix shape [{n_M}][{n_tot}][{n_tot}]", fatal=True)
    check(all(C[m][u][u] == 0 for m in range(n_M) for u in range(n_tot)),
          "cost diagonal = 0")
    check(all(T[m][u][u] == 0 for m in range(n_M) for u in range(n_tot)),
          "time diagonal = 0")
    check(all(C[m][u][v] >= 0 for m in range(n_M)
              for u in range(n_tot) for v in range(n_tot)),
          "all costs >= 0")
    # Air should be cheapest per-km for short trips (fast) but expensive per trip
    u0, v0 = nodes["demand_indices"][0], nodes["hub_indices"][0]
    print(f"         road/water/air cost [{u0}->{v0}]: "
          + " / ".join(f"{C[m][u0][v0]:.1f}" for m in range(n_M)))
    print(f"         road/water/air time [{u0}->{v0}]: "
          + " / ".join(f"{T[m][u0][v0]:.3f}h" for m in range(n_M)))

    # -- Theta matrix ----------------------------------------------------------
    print("\n[6] Daganzo Theta matrix")
    theta = d["theta"]
    check(len(theta) == n_H and len(theta[0]) == n_I and len(theta[0][0]) == n_S,
          f"theta shape [{n_H}][{n_I}][{n_S}]", fatal=True)
    finite = sum(1 for ki in range(n_H) for ii in range(n_I)
                 for si in range(n_S) if theta[ki][ii][si] < 1e8)
    total  = n_H * n_I * n_S
    check(finite > 0,
          f"{finite}/{total} theta entries reachable (not big-M)")

    # -- Lambda ----------------------------------------------------------------
    print("\n[7] Lambda")
    lam = d["lambda"]
    check(len(lam) == n_I * n_S,
          f"lambda entries = {len(lam)} (expected {n_I*n_S})")
    check(all(float(v) > 0 for v in lam.values()), "all lambda > 0")

    # -- Summary ---------------------------------------------------------------
    print(f"\n{'-'*60}")
    print(f"  Instance : {d['meta']['name']}")
    print(f"  Size     : {d['meta']['size']}")
    print(f"  Seed     : {d['meta']['seed']}")
    print(f"  Method   : {d['meta'].get('methodology', 'n/a')}")


if __name__ == "__main__":
    targets = sys.argv[1:] if len(sys.argv) > 1 else [
        os.path.join(SCRIPT_DIR, "cv_small_drnd.json"),
        os.path.join(SCRIPT_DIR, "cv_large_drnd.json"),
    ]
    for path in targets:
        if os.path.exists(path):
            verify(path)
        else:
            print(f"[skip] not found: {path}")
