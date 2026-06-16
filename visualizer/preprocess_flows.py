"""
preprocess_flows.py — Generate per-solution per-scenario flow JSONs.

For each solution in the Pareto front, derives second-stage flow decisions
using a heuristic decoder that faithfully mirrors decoder.hpp (v3):

  1. Hub activation: X[k]=1 AND risk[k] <= chi  (force-activate safest if none)
  2. Demand priority sort: W[0]*urgency + W[3]*isolation - W[1]*dist
  3. Hub trial order: hubs sorted by distance FROM anchor hub A[ii]
  4. Pass 1 (K=max(1,ceil(W[5]*|H|)) hubs): scored by W[1]/time + W[2]*residual + W[4]*planned
  5. Pass 2 (remaining hubs): first active+reachable (no capacity check)
  6. Mode selection: road/water by min C_time; air as last resort (mirrors best_mode_time)

Reactive hub opening (Pass 3) and MCF transshipment are omitted (visualization scope).
Outputs are labelled "postprocessor estimate" — not solver ground truth.

Run from project root:
    ./.venv/bin/python3 visualizer/preprocess_flows.py
    ./.venv/bin/python3 visualizer/preprocess_flows.py --result results/exp2/CV_large_seed0.json
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src" / "visualizer"))

from solution_loader import NodeInfo, Solution, load_instance, load_result

_DEFAULT_RESULT   = _ROOT / "results" / "exp2" / "CV_large_seed0.json"
_DEFAULT_INSTANCE = _ROOT / "data" / "cv" / "cv_large_drnd.json"
_OUT_DIR          = _ROOT / "results" / "exp2" / "flows"

_DEFAULT_CHI   = 0.7
_DEFAULT_GAMMA = 3.0
_BIG_M         = 1e8


# ── Geometry helpers ──────────────────────────────────────────────────────────

def _dist2(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    """Squared Euclidean distance (matches decoder's hub_anchor_order sort key)."""
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


def _dist(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


# ── Accessibility helper ──────────────────────────────────────────────────────

def _is_accessible(accessibility: List, mode: int, src: int, dst: int) -> bool:
    try:
        return bool(accessibility[mode][src][dst])
    except (IndexError, TypeError):
        return True


# ── Mode selector — mirrors decoder.hpp best_mode_time ───────────────────────

def _best_mode_time(
    accessibility: List,
    src: int,
    dst: int,
    c_time: Optional[List] = None,
) -> Tuple[int, float]:
    """
    Return (mode, time) for the fastest accessible road/water link;
    fall back to air if neither is reachable.  Returns (-1, BIG_M) if
    the pair is completely unreachable.

    Mirrors decoder.hpp lines 138–152 exactly:
      - Road (0) and water (1): requires acc=1 AND time < current best
      - Air (2): requires acc=1 only (last resort, no time gate vs current best)
    """
    best_mode = -1
    best_time = _BIG_M
    for m in (0, 1):
        if _is_accessible(accessibility, m, src, dst):
            t = float(c_time[m][src][dst]) if c_time else float(m)
            if t < best_time:
                best_time = t
                best_mode = m
    if best_mode == -1 and _is_accessible(accessibility, 2, src, dst):
        best_time = float(c_time[2][src][dst]) if c_time else 0.0
        best_mode = 2
    return best_mode, best_time


# ── Pre-computation: hub anchor order ────────────────────────────────────────

def _build_hub_anchor_order(node_info: NodeInfo) -> List[List[int]]:
    """
    hub_anchor_order[ki][j] = local hub index of the j-th closest hub to hub ki.
    Sorted by squared Euclidean (lat, lon) distance — matches decoder.hpp lines 98–117.
    hub_anchor_order[ki][0] == ki always (distance 0 to itself).
    """
    coords = node_info.coords
    num_H = len(node_info.hub_indices)
    order: List[List[int]] = []
    for ki in range(num_H):
        hi = node_info.hub_indices[ki]
        ranked = sorted(range(num_H),
                        key=lambda kj: _dist2(coords[hi], coords[node_info.hub_indices[kj]]))
        order.append(ranked)
    return order


# ── Demand priority scoring — mirrors decoder.hpp lines 200–246 ───────────────

def _normalise(v: List[float]) -> List[float]:
    if not v:
        return v
    mn, mx = min(v), max(v)
    rng = mx - mn
    if rng < 1e-9:
        return [0.5] * len(v)
    return [(x - mn) / rng for x in v]


def _demand_priority_order(
    solution: Solution,
    node_info: NodeInfo,
    is_active: List[bool],
    accessibility: List,
    c_time: Optional[List],
    scenario_raw: Dict[str, Any],
    lambda_table: Dict[str, float],
    si: int,
) -> List[int]:
    """
    Return demand LOCAL indices sorted by composite priority score (descending).

    score[ii] = W[0]*urgency[ii] + W[3]*isolation[ii] - W[1]*dist[ii] + ii*1e-9

    where:
      urgency[ii]   = lambda[ii][si] * demand[i]     (λ·D, normalized)
      isolation[ii] = 1 / num_active_reachable_hubs  (normalized)
      dist[ii]      = min C_time to any active hub    (normalized, negated in score)
    """
    W = solution.W if solution.W else [0.5] * 6
    demand_raw = scenario_raw.get("demand", {})
    num_I = len(node_info.demand_indices)
    active_hub_locals = [k for k, a in enumerate(is_active) if a]

    raw_urgency: List[float] = []
    raw_isolation: List[float] = []
    raw_dist: List[float] = []

    for ii, d_global in enumerate(node_info.demand_indices):
        D = float(demand_raw.get(str(d_global), 1.0))
        lam = float(lambda_table.get(f"{ii}_{si}", 1.0))
        raw_urgency.append(lam * D)

        n_reach = 0
        min_t = _BIG_M
        for ki in active_hub_locals:
            h_global = node_info.hub_indices[ki]
            reachable = False
            for m in range(3):
                if _is_accessible(accessibility, m, d_global, h_global):
                    reachable = True
                    if c_time:
                        t = float(c_time[m][d_global][h_global])
                        if t < min_t:
                            min_t = t
                    break  # count hub once
            if reachable:
                n_reach += 1

        raw_isolation.append(1.0 / n_reach if n_reach > 0 else 1.0)
        raw_dist.append(min_t if min_t < _BIG_M else 0.0)

    u_n = _normalise(raw_urgency)
    iso_n = _normalise(raw_isolation)
    dist_n = _normalise(raw_dist)

    scores = [
        W[0] * u_n[ii] + W[3] * iso_n[ii] - W[1] * dist_n[ii] + ii * 1e-9
        for ii in range(num_I)
    ]
    return sorted(range(num_I), key=lambda ii: scores[ii], reverse=True)


# ── Hub activation — mirrors decoder.hpp Step 2 ───────────────────────────────

def _derive_active_hubs(
    solution: Solution,
    node_info: NodeInfo,
    scenario_raw: Dict[str, Any],
    chi: float,
) -> List[bool]:
    """
    is_active[ki] = True if hub ki is a planned hub activated in this scenario.
    Mirrors decoder.hpp lines 170–197:
      active[ki] = X[ki]=1 AND risk[k] <= chi
    Force-activates the safest hub if nothing qualifies.
    """
    hub_risk_raw = scenario_raw.get("hub_risk", {})
    is_active = []
    for k, h_global in enumerate(node_info.hub_indices):
        established = solution.X[k] == 1 if k < len(solution.X) else False
        risk = float(hub_risk_raw.get(str(h_global), 0.0))
        is_active.append(established and risk <= chi)

    if not any(is_active):
        # Force-activate safest hub (min risk), regardless of X[k]
        risk_vals = [float(hub_risk_raw.get(str(node_info.hub_indices[k]), 1.0))
                     for k in range(len(node_info.hub_indices))]
        safest = min(range(len(node_info.hub_indices)), key=lambda k: risk_vals[k])
        is_active[safest] = True

    return is_active


# ── Hub scoring — mirrors decoder.hpp line 298 ────────────────────────────────

def _hub_score(W: List[float], time: float, residual: float, is_planned: bool) -> float:
    """Pass-1 hub score: W[1]/time + W[2]*residual + W[4]*planned_bonus."""
    return (W[1] * (1.0 / (time + 1e-9))
            + W[2] * max(0.0, residual)
            + W[4] * (1.0 if is_planned else 0.0))


# ── Main demand assignment — mirrors decoder.hpp Step 4 ──────────────────────

def _derive_demand_assignments(
    solution: Solution,
    node_info: NodeInfo,
    is_active: List[bool],
    scenario_raw: Dict[str, Any],
    c_time: Optional[List],
    hub_anchor_order: List[List[int]],
    lambda_table: Dict[str, float],
    si: int,
    kappa: Dict[str, float],
    gamma: float,
) -> List[Dict[str, Any]]:
    """
    Assign each demand node to an active hub, mirroring decoder.hpp Step 4.

    3-pass structure (reactive hub opening / Pass 3 omitted for visualization):
      Pass 1: K hubs in anchor-proximity order — scored, capacity-aware
      Pass 2: remaining hubs in anchor-proximity order — first reachable
      Fallback: nearest active hub by geometry
    """
    W = solution.W if solution.W else [0.5] * 6
    accessibility = scenario_raw.get("accessibility", [])
    demand_raw = scenario_raw.get("demand", {})
    num_H = len(node_info.hub_indices)
    coords = node_info.coords

    # K = max(1, ceil(W[5] * num_H))  — Pass-1 window depth
    K = max(1, math.ceil(W[5] * num_H))

    # Inventory per hub: R[k] * kappa[k] for established hubs
    inventory: List[float] = []
    for ki, h_global in enumerate(node_info.hub_indices):
        cap = kappa.get(str(h_global), 0.0)
        if is_active[ki] and solution.X[ki] == 1:
            inventory.append(float(solution.R[ki]) * float(cap) if ki < len(solution.R) else 0.0)
        else:
            inventory.append(0.0)
    hub_load: List[float] = [0.0] * num_H

    # Demand priority order
    priority_order = _demand_priority_order(
        solution, node_info, is_active, accessibility, c_time,
        scenario_raw, lambda_table, si
    )

    assignments: List[Optional[Dict[str, Any]]] = [None] * len(node_info.demand_indices)

    for ii in priority_order:
        d_global = node_info.demand_indices[ii]
        D = float(demand_raw.get(str(d_global), 1.0))
        D_kg = gamma * D

        # Anchor hub and trial order (decoder.hpp line 264)
        anchor_ki = (solution.A[ii] % num_H) if (solution.A and ii < len(solution.A)) else 0
        trial_order = hub_anchor_order[anchor_ki]

        best_ki = -1
        best_mode = -1
        best_score = -1e18

        # Global surplus check (transshipment-aware, decoder.hpp line 288)
        has_global_surplus = any(
            inventory[kj] - hub_load[kj] > 1e-6
            for kj in range(num_H) if is_active[kj]
        )

        # ── Pass 1: first K hubs in anchor-proximity order ────────────────
        for j in range(min(K, num_H)):
            ki = trial_order[j]
            if not is_active[ki]:
                continue
            h_global = node_info.hub_indices[ki]
            b_m, b_t = _best_mode_time(accessibility, d_global, h_global, c_time)
            if b_m == -1:
                continue
            residual = inventory[ki] - hub_load[ki]
            if residual <= 0.0 and not has_global_surplus:
                continue  # no local or global stock
            score = _hub_score(W, b_t, residual, solution.X[ki] == 1)
            if score > best_score:
                best_score = score
                best_ki = ki
                best_mode = b_m

        # ── Pass 2: hubs K..num_H-1 in anchor-proximity order ────────────
        if best_ki == -1:
            for j in range(K, num_H):
                ki = trial_order[j]
                if not is_active[ki]:
                    continue
                h_global = node_info.hub_indices[ki]
                b_m, _ = _best_mode_time(accessibility, d_global, h_global, c_time)
                if b_m != -1:
                    best_ki = ki
                    best_mode = b_m
                    break

        # ── Pass 3 omitted (no reactive hub opening in visualizer) ────────
        # In C++: would open nearest safe inactive hub here, add reactive cost

        # ── Geometry fallback (should rarely trigger) ─────────────────────
        if best_ki == -1:
            active_locals = [k for k in range(num_H) if is_active[k]]
            if active_locals:
                best_ki = min(active_locals,
                              key=lambda k: _dist(coords[d_global],
                                                  coords[node_info.hub_indices[k]]))
                best_mode = 0

        if best_ki >= 0:
            hub_load[best_ki] += D_kg
            assignments[ii] = {
                "demand_idx": d_global,
                "hub_idx": node_info.hub_indices[best_ki],
                "mode": best_mode,
            }
        else:
            assignments[ii] = {"demand_idx": d_global, "hub_idx": -1, "mode": 0}

    return [a for a in assignments if a is not None]


# ── Origin assignment — mirrors decoder.hpp Step 5 (greedy path) ──────────────

def _derive_origin_assignments(
    node_info: NodeInfo,
    is_active: List[bool],
    scenario_raw: Dict[str, Any],
    c_time: Optional[List],
) -> List[Dict[str, Any]]:
    """
    Assign each origin to the most-deficit active hub by cheapest mode.
    Mirrors decoder.hpp legacy greedy Step 5 (lines 544–589).
    Uses best_mode_time (time proxy for cost, since C_cost not in Python scope).
    """
    accessibility = scenario_raw.get("accessibility", [])
    num_H = len(node_info.hub_indices)
    active_locals = [k for k in range(num_H) if is_active[k]]

    if not active_locals:
        return [{"origin_idx": o, "hub_idx": -1, "mode": 0}
                for o in node_info.origin_indices]

    assignments = []
    for o_global in node_info.origin_indices:
        # Find fastest accessible active hub (time as cost proxy)
        best_ki = -1
        best_mode = -1
        best_time = _BIG_M
        for ki in active_locals:
            h_global = node_info.hub_indices[ki]
            b_m, b_t = _best_mode_time(accessibility, o_global, h_global, c_time)
            if b_m != -1 and b_t < best_time:
                best_time = b_t
                best_ki = ki
                best_mode = b_m

        if best_ki == -1 and active_locals:
            best_ki = active_locals[0]
            best_mode = 0

        assignments.append({
            "origin_idx": o_global,
            "hub_idx": node_info.hub_indices[best_ki] if best_ki >= 0 else -1,
            "mode": best_mode,
        })
    return assignments


# ── Inventory held — per-scenario (mirrors flow_out->inventory_held) ──────────

def _derive_inventory_held(
    solution: Solution,
    node_info: NodeInfo,
    is_active: List[bool],
    kappa: Dict[str, float],
) -> List[float]:
    """
    inventory_held[ki] = R[ki] * kappa[ki] for planned active hubs; 0 otherwise.
    Reactive hubs carry zero pre-positioned inventory (decoder.hpp line 341).
    """
    held = []
    for ki, h_global in enumerate(node_info.hub_indices):
        if is_active[ki] and solution.X[ki] == 1:
            cap = float(kappa.get(str(h_global), 0.0))
            r = float(solution.R[ki]) if ki < len(solution.R) else 0.0
            held.append(cap * r)
        else:
            held.append(0.0)
    return held


# ── Top-level solution processor ──────────────────────────────────────────────

def process_solution(
    sol_idx: int,
    solution: Solution,
    node_info: NodeInfo,
    instance_raw: Dict[str, Any],
) -> Dict[str, Any]:
    """Derive full flow data for one solution across all scenarios."""
    gp = instance_raw.get("global_params", {})
    chi   = float(gp.get("chi",   _DEFAULT_CHI))
    gamma = float(gp.get("gamma", _DEFAULT_GAMMA))
    c_time = instance_raw.get("transport", {}).get("time", None)
    kappa  = instance_raw.get("hub_params", {}).get("capacity", {})
    lambda_table: Dict[str, float] = instance_raw.get("lambda", {})

    hub_anchor_order = _build_hub_anchor_order(node_info)

    scenarios_out = []
    for si, sc_raw in enumerate(instance_raw.get("scenarios", [])):
        is_active = _derive_active_hubs(solution, node_info, sc_raw, chi)

        demand_asgn = _derive_demand_assignments(
            solution, node_info, is_active, sc_raw, c_time,
            hub_anchor_order, lambda_table, si, kappa, gamma,
        )
        origin_asgn = _derive_origin_assignments(
            node_info, is_active, sc_raw, c_time
        )
        inventory_held = _derive_inventory_held(solution, node_info, is_active, kappa)

        scenarios_out.append({
            "scenario": si,
            "y_ks": is_active,
            "demand_assignments": demand_asgn,
            "origin_assignments": origin_asgn,
            "transshipment": [],  # MCF omitted (visualization scope)
            "inventory_held": inventory_held,
        })

    return {
        "meta": {
            "Z1": solution.Z1,
            "Z2": solution.Z2,
            "CV": solution.CV,
            "X": solution.X,
            "R": solution.R,
            "W": solution.W,
            "solution_idx": sol_idx,
            "note": (
                "Postprocessor estimate — mirrors decoder.hpp v3 (anchor-based "
                "3-pass, W-weighted). Transshipment omitted. NOT solver ground truth."
            ),
        },
        "scenarios": scenarios_out,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Pre-generate flow JSONs for all Pareto solutions.")
    parser.add_argument("--result",   default=str(_DEFAULT_RESULT))
    parser.add_argument("--instance", default=str(_DEFAULT_INSTANCE))
    parser.add_argument("--out-dir",  default=str(_OUT_DIR))
    parser.add_argument("--force",    action="store_true")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading result  : {args.result}")
    result = load_result(args.result)
    print(f"Loading instance: {args.instance}")
    node_info = load_instance(args.instance)
    with open(args.instance, encoding="utf-8") as f:
        instance_raw = json.load(f)

    solutions = result.pareto_front or result.all_feasible
    print(f"Solutions to process: {len(solutions)}")

    for idx, sol in enumerate(solutions):
        out_path = out_dir / f"solution_{idx}.json"
        if out_path.exists() and not args.force:
            print(f"  [skip] solution_{idx}.json already exists")
            continue
        print(f"  Processing solution {idx} (Z1={sol.Z1:,.0f}  Z2={sol.Z2:,.0f})…")
        data = process_solution(idx, sol, node_info, instance_raw)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        print(f"    → saved {out_path}")

    print(f"\nDone. {len(solutions)} flow files in {out_dir}")


if __name__ == "__main__":
    main()
