"""
narrative_data.py — Extract all Block 1–10 narrative query keys to JSON.

Usage:
    .venv/bin/python3 visualizer/narrative_data.py \\
        --results  results/exp2/v2 \\
        --flows    results/exp2/v2/flows \\
        --instance data/cv/v2/cv_large_drnd.json \\
        --out      narrative_data.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "src" / "visualizer"))

from solution_loader import Solution, SolverResult, NodeInfo, load_result, load_instance, deduplicate_solutions  # noqa: E402
from visualizer.flow_loader import load_solution_flow, ScenarioFlow  # noqa: E402

_SC_KEYS = ["mild", "severe", "extreme"]


# ── helpers ──────────────────────────────────────────────────────────────────

def _nd_filter(solutions: List[Solution]) -> List[Solution]:
    """Return non-dominated (Pareto) subset by (Z1, Z2)."""
    nd = []
    for s in solutions:
        dominated = any(
            o.Z1 <= s.Z1 and o.Z2 <= s.Z2 and (o.Z1 < s.Z1 or o.Z2 < s.Z2)
            for o in solutions
        )
        if not dominated:
            nd.append(s)
    return nd


def _compute_knee(solutions: List[Solution]) -> int:
    """Tchebycheff knee index on normalised combined ND front."""
    z1s = [s.Z1 for s in solutions]
    z2s = [s.Z2 for s in solutions]
    z1_min, z1r = min(z1s), (max(z1s) - min(z1s)) or 1.0
    z2_min, z2r = min(z2s), (max(z2s) - min(z2s)) or 1.0
    return min(
        range(len(solutions)),
        key=lambda i: max(
            (solutions[i].Z1 - z1_min) / z1r,
            (solutions[i].Z2 - z2_min) / z2r,
        ),
    )


def _load_seeds(results_dir: Path) -> List[Tuple[int, Solution]]:
    """
    Glob CV_large_seed*.json, load each, return (seed_num, solution) pairs
    for all CV=0 solutions across all seeds.
    """
    pairs: List[Tuple[int, Solution]] = []
    pattern = re.compile(r"(?i)^cv_large_seed(\d+)\.json$")
    for p in sorted(results_dir.glob("CV_large_seed*.json")):
        m = pattern.match(p.name)
        if not m:
            continue
        seed_num = int(m.group(1))
        try:
            result: SolverResult = load_result(str(p))
        except Exception as e:
            print(f"  [warn] Could not load {p.name}: {e}", file=sys.stderr)
            continue
        for sol in (result.pareto_front or []):
            if sol.CV == 0.0:
                pairs.append((seed_num, sol))
    return pairs


def _hub_name(node_info: NodeInfo, k: int) -> str:
    """Return display name for hub k (local index)."""
    g = node_info.hub_indices[k]
    return node_info.names[g] if g < len(node_info.names) else f"H{k}"


def _capacity(inst_raw: Dict[str, Any], hub_global: int) -> float:
    cap = inst_raw.get("hub_params", {}).get("capacity", {})
    return float(cap.get(str(hub_global), 0.0))


def _hub_risk(inst_raw: Dict[str, Any], sc_idx: int, hub_global: int) -> float:
    scs = inst_raw.get("scenarios", [])
    if sc_idx >= len(scs):
        return 0.0
    return float(scs[sc_idx].get("hub_risk", {}).get(str(hub_global), 0.0))


def _mode_counts(sc_flow: Optional[ScenarioFlow]) -> Tuple[int, int, int]:
    """Return (road, water, air) assignment counts from a ScenarioFlow."""
    if sc_flow is None:
        return 0, 0, 0
    road = water = air = 0
    for da in sc_flow.demand_assignments:
        if da.mode == 0:
            road += 1
        elif da.mode == 1:
            water += 1
        elif da.mode == 2:
            air += 1
    return road, water, air


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="Extract narrative query keys from 20-seed CV-Large results")
    # All path args required — no defaults.
    # Legacy invocation (do not restore as defaults):
    #   --results  results/exp2/v2
    #   --flows    results/exp2/v2/flows
    #   --instance data/cv/v2/cv_large_drnd.json
    #   --out      narrative_data.json
    ap.add_argument("--results",  required=True, help="Results directory (contains CV_large_seed*.json)")
    ap.add_argument("--flows",    required=True, help="Flows directory (contains solution_*.json)")
    ap.add_argument("--instance", required=True, help="Instance JSON path")
    ap.add_argument("--out",      required=True, help="Output JSON path")
    args = ap.parse_args()

    results_dir = Path(args.results)
    flows_dir   = Path(args.flows)
    inst_path   = Path(args.instance)
    out_path    = Path(args.out)

    print(f"[narrative_data] instance: {inst_path}")
    print(f"[narrative_data] results:  {results_dir}")
    print(f"[narrative_data] flows:    {flows_dir}")

    # ── Load instance ────────────────────────────────────────────────────────
    with open(inst_path, encoding="utf-8") as f:
        inst_raw: Dict[str, Any] = json.load(f)

    node_info: NodeInfo = load_instance(str(inst_path))
    chi: float = float(inst_raw.get("global_params", {}).get("chi", 0.70))
    hub_globals = node_info.hub_indices
    num_H = len(hub_globals)
    num_I = len(node_info.demand_indices)

    # ── Load all seeds ───────────────────────────────────────────────────────
    print("[narrative_data] Loading seed files…")
    seed_sol_pairs = _load_seeds(results_dir)
    if not seed_sol_pairs:
        print("[Error] No CV_large_seed*.json found in results dir.", file=sys.stderr)
        sys.exit(1)

    seeds_found = sorted({s for s, _ in seed_sol_pairs})
    all_solutions = [sol for _, sol in seed_sol_pairs]
    print(f"  Seeds found: {seeds_found}  ({len(all_solutions)} total CV=0 solutions)")

    # ── Build combined ND front ──────────────────────────────────────────────
    deduped, _ = deduplicate_solutions(all_solutions, mode="objective")
    combined_nd = _nd_filter(deduped)
    print(f"  Combined ND front: {len(combined_nd)} solutions")

    # ── Knee ─────────────────────────────────────────────────────────────────
    knee_idx = _compute_knee(combined_nd)
    knee_sol = combined_nd[knee_idx]
    # Find which seed the knee came from
    knee_seed = next(
        (s for s, sol in seed_sol_pairs
         if abs(sol.Z1 - knee_sol.Z1) < 1.0 and abs(sol.Z2 - knee_sol.Z2) < 1.0),
        -1,
    )
    print(f"  Knee: Z1={knee_sol.Z1:,.0f}  Z2={knee_sol.Z2:,.0f}  seed={knee_seed}")

    # ── Best Z1 / Z2 references ──────────────────────────────────────────────
    best_z1_sol = min(combined_nd, key=lambda s: s.Z1)
    best_z2_sol = min(combined_nd, key=lambda s: s.Z2)

    deprivation_reduction_pct = (
        (best_z1_sol.Z2 - knee_sol.Z2) / best_z1_sol.Z2 * 100
        if best_z1_sol.Z2 > 0 else 0.0
    )
    cost_premium_pct = (
        (knee_sol.Z1 - best_z1_sol.Z1) / best_z1_sol.Z1 * 100
        if best_z1_sol.Z1 > 0 else 0.0
    )

    # ── Hub selection frequency (across all solutions pooled) ─────────────────
    total_pooled = len(deduped)
    hub_selection_freq: Dict[str, float] = {}
    for k in range(num_H):
        name = _hub_name(node_info, k)
        count = sum(1 for sol in deduped if k < len(sol.X) and sol.X[k] == 1)
        hub_selection_freq[name] = round(count / total_pooled, 4) if total_pooled > 0 else 0.0

    # ── Open hubs for knee solution ───────────────────────────────────────────
    open_hub_indices = [k for k in range(num_H) if k < len(knee_sol.X) and knee_sol.X[k] == 1]
    open_hub_count = len(open_hub_indices)
    open_hub_list = [_hub_name(node_info, k) for k in open_hub_indices]

    # ── Per-scenario hub risk analysis ───────────────────────────────────────
    active_hub_count:   Dict[str, int]       = {}
    inactive_hub_names: Dict[str, List[str]] = {}
    hub_risk_values:    Dict[str, Dict[str, float]] = {}
    reactive_hub_count: Dict[str, int]       = {}
    lateral_link_count: Dict[str, int]       = {}

    for sc_idx, sc_key in enumerate(_SC_KEYS):
        active = 0
        inactive_names: List[str] = []
        risks: Dict[str, float] = {}
        for k in open_hub_indices:
            g = hub_globals[k]
            r = _hub_risk(inst_raw, sc_idx, g)
            name = _hub_name(node_info, k)
            risks[name] = round(r, 4)
            if r <= chi:
                active += 1
            else:
                inactive_names.append(f"{name} (r={r:.2f})")
        active_hub_count[sc_key]   = active
        inactive_hub_names[sc_key] = inactive_names
        hub_risk_values[sc_key]    = risks
        reactive_hub_count[sc_key] = 0  # proactive-only model; no reactive hubs
        lateral_link_count[sc_key] = 0  # MCF not implemented; transshipment always 0

    # ── Flow-derived fields: mode counts, inv fill, air hubs ─────────────────
    modal_road:    Dict[str, int] = {}
    modal_water:   Dict[str, int] = {}
    modal_air:     Dict[str, int] = {}
    air_serving_hubs: Dict[str, List[Dict[str, Any]]] = {}
    inv_fill_pct:  Dict[str, float] = {}

    # Find knee solution's index in the combined ND (for flow file lookup)
    knee_sol_idx = 0  # flow files indexed by solution position in original PF
    # Try to load flow files for knee solution (sol_idx 0 = most common available)
    knee_flow = load_solution_flow(knee_sol_idx, flows_dir=flows_dir)

    for sc_idx, sc_key in enumerate(_SC_KEYS):
        sc_flow = knee_flow.scenarios[sc_idx] if (knee_flow and sc_idx < len(knee_flow.scenarios)) else None
        road, water, air = _mode_counts(sc_flow)
        modal_road[sc_key]  = road
        modal_water[sc_key] = water
        modal_air[sc_key]   = air

        # Air-serving hubs
        air_hubs: Dict[int, int] = {}
        if sc_flow:
            for da in sc_flow.demand_assignments:
                if da.mode == 2:
                    air_hubs[da.hub_idx] = air_hubs.get(da.hub_idx, 0) + 1
        air_serving_hubs[sc_key] = [
            {"name": node_info.names[g] if g < len(node_info.names) else str(g),
             "hub_global": g,
             "count": cnt}
            for g, cnt in sorted(air_hubs.items(), key=lambda x: -x[1])
        ]

    # Inventory fill % (from mild scenario flow if available)
    sc0_flow = knee_flow.scenarios[0] if (knee_flow and knee_flow.scenarios) else None
    for k in open_hub_indices:
        g = hub_globals[k]
        name = _hub_name(node_info, k)
        cap = _capacity(inst_raw, g)
        if sc0_flow and k < len(sc0_flow.inventory_held) and cap > 0:
            fill = sc0_flow.inventory_held[k] / cap * 100
        elif k < len(knee_sol.R) and cap > 0:
            fill = knee_sol.R[k] * 100
        else:
            fill = 0.0
        inv_fill_pct[name] = round(fill, 2)

    # ── Validate ─────────────────────────────────────────────────────────────
    assert knee_sol.CV == 0.0, f"knee_CV must be 0.0, got {knee_sol.CV}"
    if knee_flow:
        for sc_idx, sc_key in enumerate(_SC_KEYS):
            total_modes = modal_road[sc_key] + modal_water[sc_key] + modal_air[sc_key]
            if total_modes > 0:
                assert total_modes == num_I, (
                    f"Mode counts for {sc_key} sum to {total_modes}, expected {num_I}"
                )
    print("  ✅ Assertions passed")

    # ── Assemble output ───────────────────────────────────────────────────────
    output: Dict[str, Any] = {
        "Z2_cost_extreme_20seed":   round(best_z2_sol.Z1, 2),
        "Z2_equity_extreme_20seed": round(best_z2_sol.Z2, 2),
        "deprivation_reduction_pct": round(deprivation_reduction_pct, 2),
        "cost_premium_pct":         round(cost_premium_pct, 2),
        "knee_Z1":                  round(knee_sol.Z1, 2),
        "knee_Z1_millions":         round(knee_sol.Z1 / 1e6, 4),
        "knee_Z2":                  round(knee_sol.Z2, 2),
        "knee_seed":                knee_seed,
        "knee_CV":                  0.0,
        "open_hub_count":           open_hub_count,
        "open_hub_list":            open_hub_list,
        "reactive_hub_count":       reactive_hub_count,
        "lateral_link_count":       lateral_link_count,
        "active_hub_count":         active_hub_count,
        "inactive_hub_names":       inactive_hub_names,
        "hub_risk_values":          hub_risk_values,
        "modal_road":               modal_road,
        "modal_water":              modal_water,
        "modal_air":                modal_air,
        "total_demand_nodes":       num_I,
        "air_serving_hubs":         air_serving_hubs,
        "inv_fill_pct":             inv_fill_pct,
        "chi":                      chi,
        "hub_selection_frequency":  hub_selection_freq,
        "total_solutions_pooled":   total_pooled,
        "seeds_included":           seeds_found,
        "dataset_version":          "v2" if "v2" in str(inst_path) else "v1",
        "generated_at":             datetime.now(timezone.utc).isoformat(),
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"✅ Written to {out_path}")


if __name__ == "__main__":
    main()
