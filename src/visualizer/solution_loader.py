"""
solution_loader.py — Load instance JSON and solver output JSON for CITA/MO-IHLNDP.

Parses:
  - DRND instance JSON (data/benchmark/*.json):  nodes, transport, scenarios
  - Solver output JSON (results/exp1/*.json):     pareto_front / all_feasible

Provides dataclasses and helpers used by the GUI and CLI.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ════════════════════════════════════════════════════════════════════════════
# Dataclasses
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class NodeInfo:
    """Parsed node metadata from the instance."""
    num_nodes: int
    coords: List[Tuple[float, float]]  # (x, y) or (lat, lon) per node index
    names: List[str]
    demand_indices: List[int]           # global indices of demand nodes
    hub_indices: List[int]              # global indices of hub candidates
    origin_indices: List[int]           # global indices of origin/supply nodes


@dataclass
class Solution:
    """
    One solution from pareto_front or all_feasible.

    Attributes
    ----------
    Z1, Z2   : objective values  (both minimise)
    CV       : constraint violation (0 = feasible)
    rank     : NSGA-II non-domination rank
    crowding : crowding distance (inf on extremes)
    X        : int[num_H]  — hub establishment vector
    R        : float[num_H] — inventory pre-positioning ratio
    A        : int[num_I]   — transport mode assignment per demand node
    W        : float[6]     — internal decoder weight vector
    source   : 'pareto_front' | 'all_feasible'
    """
    Z1: float
    Z2: float
    CV: float
    rank: int
    crowding: float
    X: List[int]
    R: List[float]
    A: List[int]
    W: List[float]
    source: str = "pareto_front"

    @property
    def open_hubs(self) -> List[int]:
        """Local hub indices (0-based) that are open."""
        return [k for k, x in enumerate(self.X) if x == 1]

    @property
    def num_open_hubs(self) -> int:
        return sum(self.X)


@dataclass
class SolverResult:
    """Full output from one solver run JSON file."""
    filepath: str
    solver: str                    # meta.solver tag
    elapsed_s: float
    seed: int
    pareto_front: List[Solution]
    all_feasible: List[Solution]

    @property
    def basename(self) -> str:
        return os.path.basename(self.filepath)

    @property
    def all_solutions(self) -> List[Solution]:
        """Pareto-front first, then remaining all_feasible."""
        pf_ids = {id(s) for s in self.pareto_front}
        extra = [s for s in self.all_feasible if id(s) not in pf_ids]
        return self.pareto_front + extra


# ════════════════════════════════════════════════════════════════════════════
# Instance loader
# ════════════════════════════════════════════════════════════════════════════

def load_instance(path: str) -> NodeInfo:
    """
    Load a DRND instance JSON and return its node metadata.

    Parameters
    ----------
    path : str
        Path to the DRND JSON file (e.g., data/benchmark/AP10_seed42_drnd.json)
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    nodes = data["nodes"]
    n = len(nodes["coords"])

    coords: List[Tuple[float, float]] = [tuple(c) for c in nodes["coords"]]  # type: ignore
    names: List[str] = nodes.get("names", [f"Node_{i}" for i in range(n)])
    demand_indices: List[int] = nodes.get("demand_indices", [])
    hub_indices: List[int] = nodes.get("hub_indices", [])
    origin_indices: List[int] = nodes.get("origin_indices", [])

    return NodeInfo(
        num_nodes=n,
        coords=coords,
        names=names,
        demand_indices=demand_indices,
        hub_indices=hub_indices,
        origin_indices=origin_indices,
    )


# ════════════════════════════════════════════════════════════════════════════
# Solver output loader
# ════════════════════════════════════════════════════════════════════════════

def _parse_solution(raw: dict, source: str) -> Solution:
    # MILP outputs may be missing A, W, rank, crowding — default gracefully
    crowding_raw = raw.get("crowding", 0.0)
    try:
        crowding = float(crowding_raw)
    except (TypeError, ValueError):
        crowding = float("inf")

    return Solution(
        Z1=float(raw.get("Z1", 0.0)),
        Z2=float(raw.get("Z2", 0.0)),
        CV=float(raw.get("CV", 0.0)),
        rank=int(raw.get("rank", 1)),
        crowding=crowding,
        X=list(raw.get("X") or []),
        R=list(raw.get("R") or []),
        A=list(raw.get("A") or []),
        W=list(raw.get("W") or []),
        source=source,
    )


def load_result(path: str) -> SolverResult:
    """
    Load a solver output JSON file.

    Parameters
    ----------
    path : str
        E.g., results/exp1/AP10_seed0.json
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    meta = data.get("meta", {})
    solver = meta.get("solver", "Unknown")
    elapsed = float(meta.get("elapsed_s", meta.get("total_elapsed_s", 0.0)))
    seed = int(meta.get("seed", 0))

    pareto_front = [
        _parse_solution(s, "pareto_front")
        for s in data.get("pareto_front", [])
    ]
    all_feasible = [
        _parse_solution(s, "all_feasible")
        for s in data.get("all_feasible", [])
    ]

    # If pareto_front is missing but all_feasible has rank-1 solutions,
    # populate it automatically
    if not pareto_front and all_feasible:
        pareto_front = [s for s in all_feasible if s.rank == 1 and s.CV == 0.0]
        for s in pareto_front:
            s.source = "pareto_front"

    return SolverResult(
        filepath=path,
        solver=solver,
        elapsed_s=elapsed,
        seed=seed,
        pareto_front=pareto_front,
        all_feasible=all_feasible,
    )


# ════════════════════════════════════════════════════════════════════════════
# Multi-file / folder loader
# ════════════════════════════════════════════════════════════════════════════

def load_results_from_folder(folder: str, pattern: str = "*.json") -> List[SolverResult]:
    """
    Load all matching JSON files in a folder.

    Returns list of SolverResult sorted by filename.
    """
    folder_path = Path(folder)
    files = sorted(folder_path.glob(pattern))
    results = []
    for f in files:
        try:
            results.append(load_result(str(f)))
        except Exception as e:
            print(f"[loader] Skipped {f.name}: {e}")
    return results


def load_results_by_algorithm(folder: str) -> Dict[str, List[SolverResult]]:
    """
    Load all JSON files in a folder and group by meta.solver tag.

    Returns dict: {solver_name: [SolverResult, ...]}
    """
    results = load_results_from_folder(folder)
    grouped: Dict[str, List[SolverResult]] = {}
    for r in results:
        grouped.setdefault(r.solver, []).append(r)
    return grouped


# ════════════════════════════════════════════════════════════════════════════
# Pareto utilities
# ════════════════════════════════════════════════════════════════════════════

def merged_pareto_front(results: List[SolverResult]) -> List[Solution]:
    """
    Merge pareto_front across multiple results and return non-dominated set.
    """
    all_sols = []
    for r in results:
        all_sols.extend(r.pareto_front)

    if not all_sols:
        return []

    # Simple 2-objective dominance check
    dominated = [False] * len(all_sols)
    for i, a in enumerate(all_sols):
        if dominated[i]:
            continue
        for j, b in enumerate(all_sols):
            if i == j or dominated[j]:
                continue
            if b.Z1 <= a.Z1 and b.Z2 <= a.Z2 and (b.Z1 < a.Z1 or b.Z2 < a.Z2):
                dominated[i] = True
                break

    return [s for s, d in zip(all_sols, dominated) if not d]


def deduplicate_solutions(
    solutions: List[Solution],
    mode: str = "objective",
    tol: float = 1.0,
) -> Tuple[List[Solution], int]:
    """
    Remove duplicate solutions, preserving the first (best-ranked) occurrence.

    Parameters
    ----------
    solutions : list of Solution — should be sorted by rank / crowding first.
    mode      : 'objective' | 'decision' | 'exact'
                  objective — same rounded (Z1, Z2) objective pair
                  decision  — same hub-establishment vector X
                  exact     — same (Z1, Z2) *and* same X
    tol       : rounding unit applied to each objective value before comparison
                (default 1.0 rounds to nearest integer, filtering floating-point
                noise while keeping numerically different solutions distinct).

    Returns
    -------
    (deduped, n_removed)
    """
    seen: set = set()
    result: List[Solution] = []
    for s in solutions:
        if mode == "objective":
            key: object = (round(s.Z1 / tol), round(s.Z2 / tol))
        elif mode == "decision":
            key = tuple(s.X)
        else:  # exact
            key = (round(s.Z1 / tol), round(s.Z2 / tol), tuple(s.X))
        if key not in seen:
            seen.add(key)
            result.append(s)
    return result, len(solutions) - len(result)


def infer_hub_allocations(solution: Solution, node_info: NodeInfo
                          ) -> List[Tuple[int, int]]:
    """
    Infer (demand_node_index, hub_node_index) allocation pairs for visualization.

    Strategy: assign each demand node to the geometrically nearest open hub.
    """
    open_global = [node_info.hub_indices[k] for k in solution.open_hubs]
    if not open_global:
        return []

    import math

    def dist(a: Tuple[float, float], b: Tuple[float, float]) -> float:
        return math.hypot(a[0] - b[0], a[1] - b[1])

    pairs: List[Tuple[int, int]] = []
    for d_idx in node_info.demand_indices:
        d_coord = node_info.coords[d_idx]
        nearest = min(open_global, key=lambda h: dist(d_coord, node_info.coords[h]))
        pairs.append((d_idx, nearest))

    return pairs
