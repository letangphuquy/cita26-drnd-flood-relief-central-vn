"""
preprocess_flows.py — Generate per-solution per-scenario flow JSONs.

For each solution in the Pareto front, derives second-stage flow decisions
using a greedy heuristic and saves to results/exp2/flows/solution_{idx}.json.

Run once from the project root:
    python visualizer/preprocess_flows.py
    python visualizer/preprocess_flows.py --result results/exp2/CV_large_seed0.json
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

# Hub risk threshold: hubs with risk > this are NOT reactively activated.
# Falls back to this default if global_params.chi is absent from the instance.
_RISK_THRESHOLD = 0.6


def _dist(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _is_accessible(accessibility: List, mode: int, src: int, dst: int) -> bool:
    try:
        return bool(accessibility[mode][src][dst])
    except (IndexError, TypeError):
        return True


def _best_mode(accessibility: List, src: int, dst: int,
               c_time: Optional[List] = None) -> Optional[int]:
    """Mirror the decoder's best_mode_time: fastest of road/water; air as last resort.

    Tries modes 0 (road) and 1 (water) and returns the one with lower C_time
    if both are accessible, or whichever is accessible if only one is.
    Falls back to mode 2 (air) only when neither road nor water is reachable.
    Returns None if the pair is unreachable by any mode.
    """
    best_mode = -1
    best_time = float("inf")
    for m in (0, 1):
        if _is_accessible(accessibility, m, src, dst):
            t = float(c_time[m][src][dst]) if c_time else float(m)
            if t < best_time:
                best_time = t
                best_mode = m
    if best_mode == -1 and _is_accessible(accessibility, 2, src, dst):
        best_mode = 2
    return best_mode if best_mode != -1 else None


def _derive_y_ks(
    solution: Solution,
    node_info: NodeInfo,
    scenario: Dict[str, Any],
    risk_threshold: float = _RISK_THRESHOLD,
) -> List[bool]:
    """
    Determine which hubs are reactively activated in this scenario.

    A hub is activated if:
      - It is established in the first stage (X[k] = 1)
      - Its risk score is below the threshold (not severely damaged)
    """
    hub_risk_raw = scenario.get("hub_risk", {})
    y_ks: List[bool] = []
    for k, h_global in enumerate(node_info.hub_indices):
        established = solution.X[k] == 1 if k < len(solution.X) else False
        risk = float(hub_risk_raw.get(str(h_global), 0.0))
        y_ks.append(established and risk < risk_threshold)
    return y_ks


def _derive_demand_assignments(
    solution: Solution,
    node_info: NodeInfo,
    y_ks: List[bool],
    scenario: Dict[str, Any],
    c_time: Optional[List] = None,
) -> List[Dict[str, Any]]:
    """
    Assign each demand node to the fastest-reachable active hub, mirroring
    the decoder's best_mode_time logic: fastest of road/water (by C_time);
    air only as last resort when no road/water hub is reachable.

    Hub selection uses minimum C_time (not geometric distance) so that a
    farther road-accessible hub is preferred over a nearer air-only hub —
    matching the decoder's cost-based priority.
    """
    coords = node_info.coords
    accessibility = scenario.get("accessibility", [])
    active_hubs_global = [
        node_info.hub_indices[k]
        for k, active in enumerate(y_ks)
        if active
    ]

    BIG_M = 1e8  # C_time sentinel for unreachable pairs

    assignments = []
    for d_idx in node_info.demand_indices:
        if not active_hubs_global:
            assignments.append({"demand_idx": d_idx, "hub_idx": -1, "mode": 0})
            continue

        # Pass 1: best road or water hub by minimum C_time (preferred over air)
        best_rw_hub = -1
        best_rw_mode = 0
        best_rw_time = float("inf")
        for h_global in active_hubs_global:
            for m in (0, 1):
                if not _is_accessible(accessibility, m, d_idx, h_global):
                    continue
                t = float(c_time[m][d_idx][h_global]) if c_time else float(m)
                if t < best_rw_time and t < BIG_M:
                    best_rw_time = t
                    best_rw_hub = h_global
                    best_rw_mode = m

        if best_rw_hub >= 0:
            assignments.append({"demand_idx": d_idx, "hub_idx": best_rw_hub, "mode": best_rw_mode})
            continue

        # Pass 2: air fallback — fastest air-accessible hub by C_time
        best_air_hub = -1
        best_air_time = float("inf")
        for h_global in active_hubs_global:
            if not _is_accessible(accessibility, 2, d_idx, h_global):
                continue
            t = float(c_time[2][d_idx][h_global]) if c_time else 0.0
            if t < best_air_time and t < BIG_M:
                best_air_time = t
                best_air_hub = h_global

        if best_air_hub >= 0:
            assignments.append({"demand_idx": d_idx, "hub_idx": best_air_hub, "mode": 2})
            continue

        # Complete fallback: nearest hub by geometry (should rarely trigger)
        best_hub = min(active_hubs_global,
                       key=lambda h: _dist(coords[d_idx], coords[h]))
        assignments.append({"demand_idx": d_idx, "hub_idx": best_hub, "mode": 0})

    return assignments


def _derive_origin_assignments(
    node_info: NodeInfo,
    y_ks: List[bool],
    scenario: Dict[str, Any],
    c_time: Optional[List] = None,
) -> List[Dict[str, Any]]:
    """Assign each origin to the fastest active hub using decoder mode logic."""
    coords = node_info.coords
    accessibility = scenario.get("accessibility", [])
    active_hubs_global = [
        node_info.hub_indices[k]
        for k, active in enumerate(y_ks)
        if active
    ]
    if not active_hubs_global:
        return [{"origin_idx": o, "hub_idx": -1, "mode": 0}
                for o in node_info.origin_indices]

    BIG_M = 1e8

    assignments = []
    for o_idx in node_info.origin_indices:
        best_rw_hub = -1
        best_rw_mode = 0
        best_rw_time = float("inf")
        for h_global in active_hubs_global:
            for m in (0, 1):
                if not _is_accessible(accessibility, m, o_idx, h_global):
                    continue
                t = float(c_time[m][o_idx][h_global]) if c_time else float(m)
                if t < best_rw_time and t < BIG_M:
                    best_rw_time = t
                    best_rw_hub = h_global
                    best_rw_mode = m

        if best_rw_hub >= 0:
            assignments.append({"origin_idx": o_idx, "hub_idx": best_rw_hub, "mode": best_rw_mode})
            continue

        best_air_hub = -1
        best_air_time = float("inf")
        for h_global in active_hubs_global:
            if not _is_accessible(accessibility, 2, o_idx, h_global):
                continue
            t = float(c_time[2][o_idx][h_global]) if c_time else 0.0
            if t < best_air_time and t < BIG_M:
                best_air_time = t
                best_air_hub = h_global

        if best_air_hub >= 0:
            assignments.append({"origin_idx": o_idx, "hub_idx": best_air_hub, "mode": 2})
            continue

        best_hub = min(active_hubs_global,
                       key=lambda h: _dist(coords[o_idx], coords[h]))
        assignments.append({"origin_idx": o_idx, "hub_idx": best_hub, "mode": 0})

    return assignments


def _derive_inventory_held(
    solution: Solution,
    node_info: NodeInfo,
    instance_raw: Dict[str, Any],
) -> List[float]:
    """Compute inventory pre-positioned at each hub (R * capacity)."""
    hub_params = instance_raw.get("hub_params", {})
    capacities = hub_params.get("capacity", {})
    held = []
    for k, h_global in enumerate(node_info.hub_indices):
        cap = float(capacities.get(str(h_global), 0.0))
        r = float(solution.R[k]) if k < len(solution.R) else 0.0
        held.append(cap * r if solution.X[k] == 1 else 0.0)
    return held


def process_solution(
    sol_idx: int,
    solution: Solution,
    node_info: NodeInfo,
    instance_raw: Dict[str, Any],
) -> Dict[str, Any]:
    """Derive full flow data for one solution across all scenarios."""
    scenarios_raw = instance_raw.get("scenarios", [])
    inventory_held = _derive_inventory_held(solution, node_info, instance_raw)
    risk_threshold = float(instance_raw.get("global_params", {}).get("chi", _RISK_THRESHOLD))
    c_time = instance_raw.get("transport", {}).get("time", None)

    scenarios_out = []
    for s_idx, sc_raw in enumerate(scenarios_raw):
        y_ks = _derive_y_ks(solution, node_info, sc_raw, risk_threshold)
        demand_asgn = _derive_demand_assignments(solution, node_info, y_ks, sc_raw, c_time)
        origin_asgn = _derive_origin_assignments(node_info, y_ks, sc_raw, c_time)

        scenarios_out.append({
            "scenario": s_idx,
            "y_ks": y_ks,
            "demand_assignments": demand_asgn,
            "origin_assignments": origin_asgn,
            "transshipment": [],  # simplified: no transshipment in heuristic
            "inventory_held": inventory_held,
        })

    return {
        "meta": {
            "Z1": solution.Z1,
            "Z2": solution.Z2,
            "CV": solution.CV,
            "X": solution.X,
            "R": solution.R,
            "solution_idx": sol_idx,
            "note": "Derived by preprocess_flows.py heuristic (greedy, no transshipment)",
        },
        "scenarios": scenarios_out,
    }


def main():
    parser = argparse.ArgumentParser(description="Pre-generate flow JSONs for all Pareto solutions.")
    parser.add_argument("--result",   default=str(_DEFAULT_RESULT),   help="Solver output JSON")
    parser.add_argument("--instance", default=str(_DEFAULT_INSTANCE), help="DRND instance JSON")
    parser.add_argument("--out-dir",  default=str(_OUT_DIR),          help="Output directory")
    parser.add_argument("--force",    action="store_true",            help="Overwrite existing files")
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
