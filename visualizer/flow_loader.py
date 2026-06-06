"""
flow_loader.py — Load per-solution per-scenario flow detail JSONs.

Pre-generated files live in  results/exp2/flows/solution_{idx}.json
(created by preprocess_flows.py).  Falls back to the single
results/exp2/cv_large_flow.json when a per-solution file is absent.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

_ROOT = Path(__file__).resolve().parent.parent
FLOWS_DIR   = _ROOT / "results" / "exp2" / "flows"
FALLBACK_FLOW = _ROOT / "results" / "exp2" / "cv_large_flow.json"


# ── dataclasses ──────────────────────────────────────────────────────────────

@dataclass
class DemandAssignment:
    demand_idx: int
    hub_idx: int   # global node index; -1 = unassigned
    mode: int      # 0=road 1=water 2=air


@dataclass
class OriginAssignment:
    origin_idx: int
    hub_idx: int
    mode: int


@dataclass
class Transshipment:
    src_hub_idx: int
    dst_hub_idx: int
    mode: int
    flow: float


@dataclass
class ScenarioFlow:
    scenario_idx: int
    y_ks: List[bool]                          # bool[num_H]
    demand_assignments: List[DemandAssignment]
    origin_assignments: List[OriginAssignment]
    transshipment: List[Transshipment]
    inventory_held: List[float] = field(default_factory=list)


@dataclass
class SolutionFlow:
    Z1: float
    Z2: float
    X: List[int]
    scenarios: List[ScenarioFlow]   # length num_S


# ── parsers ───────────────────────────────────────────────────────────────────

def _parse_scenario(raw: dict) -> ScenarioFlow:
    return ScenarioFlow(
        scenario_idx=int(raw.get("scenario", 0)),
        y_ks=list(raw.get("y_ks", [])),
        demand_assignments=[DemandAssignment(**a) for a in raw.get("demand_assignments", [])],
        origin_assignments=[OriginAssignment(**a) for a in raw.get("origin_assignments", [])],
        transshipment=[Transshipment(**t) for t in raw.get("transshipment", [])],
        inventory_held=list(raw.get("inventory_held", [])),
    )


def _load_json(path: Path) -> SolutionFlow:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    meta = data.get("meta", {})
    return SolutionFlow(
        Z1=float(meta.get("Z1", 0.0)),
        Z2=float(meta.get("Z2", 0.0)),
        X=list(meta.get("X", [])),
        scenarios=[_parse_scenario(s) for s in data.get("scenarios", [])],
    )


# ── public API ────────────────────────────────────────────────────────────────

def load_solution_flow(solution_idx: int,
                       flows_dir: Optional[Path] = None) -> Optional[SolutionFlow]:
    """Load pre-generated flow for *solution_idx* from *flows_dir* (default FLOWS_DIR)."""
    d = flows_dir if flows_dir is not None else FLOWS_DIR
    candidate = d / f"solution_{solution_idx}.json"
    if candidate.exists():
        return _load_json(candidate)
    return None


def load_fallback_flow() -> Optional[SolutionFlow]:
    """Load the single cv_large_flow.json (median-Z1 solution)."""
    if FALLBACK_FLOW.exists():
        return _load_json(FALLBACK_FLOW)
    return None


def flows_available(flows_dir: Optional[Path] = None) -> List[int]:
    """Return sorted list of solution indices that have pre-generated flow files."""
    d = flows_dir if flows_dir is not None else FLOWS_DIR
    if not d.exists():
        return []
    return sorted(
        int(p.stem.split("_")[1])
        for p in d.glob("solution_*.json")
        if p.stem.split("_")[1].isdigit()
    )
