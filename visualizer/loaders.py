"""
loaders.py — Cached data-loading helpers for the DRND visualiser.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT / "src" / "visualizer") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src" / "visualizer"))
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from solution_loader import (  # noqa: E402
    NodeInfo, Solution, SolverResult,
    load_instance, load_result, deduplicate_solutions,
    merged_pareto_front,
)
from visualizer.flow_loader import (  # noqa: E402
    load_solution_flow, load_fallback_flow, SolutionFlow,
)


@st.cache_data(show_spinner="Loading solver results…")
def cached_load_result(path: str, mtime: float) -> SolverResult:
    return load_result(path)


@st.cache_data(show_spinner="Loading solver results…")
def cached_load_merged_result(results_dir: str, dataset_name: str, max_mtime: float) -> SolverResult:
    """Load all seed JSONs from results_dir and return a single merged SolverResult.

    pareto_front = non-dominated set across all seeds.
    all_feasible = all CV=0 solutions from all seeds (for Solution tab navigation).
    filepath     = first seed file (used by flow preprocessing).
    """
    folder = Path(results_dir)
    if dataset_name == "CV Large":
        seed_files = sorted(
            f for f in folder.glob("CV_large_seed[0-9]*.json")
            if "_eval" not in f.name
        )
    else:
        seed_files = sorted(
            list(folder.glob("cv_small_pb_nsga_seed[0-9]*.json"))
            + ([folder / "cv_small_pb_nsga.json"]
               if (folder / "cv_small_pb_nsga.json").exists() else [])
        )

    if not seed_files:
        raise FileNotFoundError(f"No seed files in {results_dir}")

    results = []
    for sf in seed_files:
        try:
            results.append(load_result(str(sf)))
        except Exception as exc:
            print(f"[loader] Skipped {sf.name}: {exc}")

    if not results:
        raise ValueError(f"Could not load any seed files from {results_dir}")

    combined_pf = merged_pareto_front(results)
    all_cv0 = [s for r in results for s in r.all_feasible if s.CV == 0.0]

    return SolverResult(
        filepath=str(seed_files[0]),
        solver=results[0].solver,
        elapsed_s=sum(r.elapsed_s for r in results),
        seed=-1,
        pareto_front=combined_pf,
        all_feasible=all_cv0,
    )


@st.cache_data(show_spinner="Loading instance…")
def cached_load_instance(path: str, mtime: float) -> NodeInfo:
    return load_instance(path)


@st.cache_data(show_spinner="Loading instance JSON…")
def cached_load_instance_raw(path: str, mtime: float) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def get_solutions(result: SolverResult, pf_only: bool) -> List[Solution]:
    sols = result.pareto_front if pf_only else (result.all_feasible or result.pareto_front)
    deduped, _ = deduplicate_solutions([s for s in sols if s.CV == 0.0], mode="objective")
    return deduped


def pick_flow(
    sol_idx: int,
    solution: Solution,
    result: SolverResult,
    scenario_idx: int,
    num_hubs: int,
    flows_dir: Optional[Any] = None,
) -> Optional[Any]:
    def _hub_match(sf: Optional[SolutionFlow]) -> bool:
        return sf is not None and len(sf.X) == num_hubs

    sf = load_solution_flow(sol_idx, flows_dir=flows_dir)
    if not _hub_match(sf):
        sf = None
    if sf is None and sol_idx == 0:
        fb = load_fallback_flow()
        sf = fb if _hub_match(fb) else None
    if sf and scenario_idx < len(sf.scenarios):
        return sf.scenarios[scenario_idx]
    return None
